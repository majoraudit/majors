import argparse
import logging
import os
import re
import subprocess
import sys
import importlib.metadata as md
from pathlib import Path
import json

PKG = "pylibmql"
NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
MIN_VERSION = (0, 3, 0)
INSTITUTION_FILE = "yale-institution.json"
# Canonical course IDs: subject + number, e.g. CPSC2010, CHEM1340L, or the
# Summer Session form PSYCS1390 (PSYC S1390).
CODE_RES = (
    re.compile(r"([A-Z&]{2,5})([0-9]{3,4}[A-Z]?)"),
    re.compile(r"([A-Z&]{2,5})S([0-9]{3,4}[A-Z]?)"),
)


def installed_version():
    try:
        return md.version(PKG)
    except md.PackageNotFoundError:
        return None


def upgrade_to_latest():
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", PKG], check=True)


def ensure_pylibmql():
    before = installed_version()
    upgrade_to_latest()
    after = installed_version()
    print(f"{PKG}: {before} -> {after}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Compile MQL 0.2 files in ./majors")
    ap.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="print every visited file and its compiled semantic IR",
    )
    return ap.parse_args(argv)


def load_institution(year_dir):
    """Return (source text, parsed schema) for a catalog year's institution schema."""
    path = year_dir / INSTITUTION_FILE
    with open(path, "r") as f:
        text = f.read()
    return text, json.loads(text)


def load_ssot(dirpath, filenames):
    """Return (path, data) for the directory's JSON file, or (None, None) if it has none."""
    jsons = [
        f for f in filenames
        if f.endswith(".json") and not f.startswith("README") and f not in ("manifest.json", INSTITUTION_FILE)
    ]
    if not jsons:
        return None, None
    # prefer <dirname>.json, e.g. psychology/psychology.json
    preferred = f"{Path(dirpath).name}.json"
    name = preferred if preferred in jsons else jsons[0]
    if len(jsons) > 1 and name != preferred:
        raise ValueError(f"{dirpath}: multiple JSON files and none named {preferred}")
    path = Path(dirpath) / name
    with open(path, "r") as f:
        return path, json.load(f)


def compile_mql(path, institution_text):
    with open(path, "r") as f:
        result = pylibmql.compile_program(f.read(), str(path), institution_text)
    program = json.loads(result.json())
    if not program.get("requirements"):
        raise ValueError(f"no compiled requirements: {path}")
    return result, program


def walk(node):
    """Yield every dict nested anywhere in a JSON value."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def check_vocabulary(path, program, institution):
    """Return errors for literals the compiler cannot type-check itself.

    The compiler checks enum and grade literals. Course attributes and
    distributionals are SET fields, and course codes are free-form, so their
    values are checked here against the institution schema.
    """
    errors = []
    subjects = set(institution["enums"]["subject"]) | set(institution.get("department_aliases", {}))
    sets = {
        "attributes": set(institution.get("tag_values", [])),
        "distributionals": set(institution["enums"]["distributional"]),
    }
    if program.get("program_id") != path.stem:
        errors.append(f"{path}: program id {program.get('program_id')!r} must match file name {path.stem!r}")

    def check_code(code):
        matches = (r.fullmatch(code) for r in CODE_RES)
        if not any(m and m.group(1) in subjects for m in matches):
            errors.append(f"{path}: unknown course code {code!r}")

    for node in walk(program):
        if node.get("kind") == "COURSE_LIST":
            for code in node["canonical_course_ids"]:
                check_code(code)
        if node.get("kind") != "COMPARE":
            continue
        field = node["field"]["field"]
        values = node["value"] if isinstance(node["value"], list) else [node["value"]]
        if field == "code":
            for code in values:
                check_code(code)
        elif node["field"]["target"] == "CATALOG_COURSE" and field in sets:
            for value in values:
                if value not in sets[field]:
                    errors.append(f"{path}: {value!r} is not a declared course {field} value")
    return errors


def validate_manifest(path):
    """Return errors for a catalog-year coverage manifest."""
    errors = []
    try:
        with open(path, "r") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [f"{path}: {e}"]

    majors = manifest.get("majors")
    if not isinstance(majors, list) or not majors:
        return [f"{path}: 'majors' missing or empty"]

    expected_count = manifest.get("inventoryCount")
    if expected_count != len(majors):
        errors.append(
            f"{path}: inventoryCount is {expected_count!r}, but manifest has {len(majors)} majors"
        )

    year_dir = path.parent
    ids = []
    for major in majors:
        if not isinstance(major, dict):
            errors.append(f"{path}: major entry is not an object: {major!r}")
            continue
        major_id = major.get("id")
        if not isinstance(major_id, str) or not NAME_RE.fullmatch(major_id):
            errors.append(f"{path}: invalid major id {major_id!r}")
            continue
        ids.append(major_id)

        programs = major.get("programs")
        if not isinstance(programs, list) or not programs:
            errors.append(f"{path}: {major_id!r} has no programs")
            continue
        if len(programs) != len(set(programs)):
            errors.append(f"{path}: {major_id!r} has duplicate program ids")

        for program_id in programs:
            if not isinstance(program_id, str) or not NAME_RE.fullmatch(program_id):
                errors.append(
                    f"{path}: {major_id!r} has invalid program id {program_id!r}"
                )

        major_json_path = year_dir / major_id / f"{major_id}.json"
        try:
            with open(major_json_path, "r") as f:
                major_json = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{major_json_path}: {e}")
            continue
        specializations = major_json.get("specializations")
        if not isinstance(specializations, list):
            errors.append(f"{major_json_path}: 'specializations' is not a list")
        elif len(specializations) != len(programs):
            errors.append(
                f"{major_json_path}: has {len(specializations)} specialization files, "
                f"but manifest declares {len(programs)} programs"
            )
        elif len(specializations) != len(set(specializations)):
            errors.append(f"{major_json_path}: duplicate specialization files")

    duplicate_ids = sorted({major_id for major_id in ids if ids.count(major_id) > 1})
    for major_id in duplicate_ids:
        errors.append(f"{path}: duplicate major id {major_id!r}")

    expected_dirs = set(ids)
    actual_dirs = {p.name for p in year_dir.iterdir() if p.is_dir()}
    for major_id in sorted(expected_dirs - actual_dirs):
        errors.append(f"{path}: major directory does not exist: {major_id}")
    for major_id in sorted(actual_dirs - expected_dirs):
        errors.append(f"{path}: directory is not a catalog major: {major_id}")

    return errors


def main():
    global pylibmql
    ensure_pylibmql()
    import pylibmql

    version = tuple(int(part) for part in re.findall(r"\d+", pylibmql.__version__)[:3])
    if version < MIN_VERSION:
        raise SystemExit(f"error: {PKG} {pylibmql.__version__} cannot compile MQL 0.2; need 0.3.0+")

    args = parse_args()

    target_dir = Path(__file__).resolve().parent / "majors"
    errors = []
    checked_mql = 0

    manifests = sorted(target_dir.glob("*/manifest.json"))
    if not manifests:
        errors.append(f"{target_dir}: no catalog-year manifest found")
    institutions = {}
    for manifest_path in manifests:
        errors.extend(validate_manifest(manifest_path))
        try:
            institutions[manifest_path.parent] = load_institution(manifest_path.parent)
        except (OSError, json.JSONDecodeError) as e:
            errors.append(f"{manifest_path.parent / INSTITUTION_FILE}: {e}")

    for dirpath, _dirnames, filenames in os.walk(target_dir):
        try:
            ssot_path, ssot = load_ssot(dirpath, filenames)
        except (ValueError, json.JSONDecodeError) as e:
            errors.append(str(e))
            continue
        if ssot is None:
            continue  # not a "meaningful" directory

        if args.verbose:
            print(ssot_path)
        specs = ssot.get("specializations")
        if not isinstance(specs, list) or not specs:
            errors.append(f"{ssot_path}: 'specializations' missing or empty")
            continue
        institution = institutions.get(Path(dirpath).parent)
        if institution is None:
            errors.append(f"{ssot_path}: no {INSTITUTION_FILE} for this catalog year")
            continue
        institution_text, institution_data = institution

        for spec in specs:
            spec_path = Path(dirpath) / spec
            if spec_path.suffix != ".mql":
                errors.append(f"{ssot_path}: {spec!r} is not an .mql file")
            elif not spec_path.is_file():
                errors.append(f"{ssot_path}: specialization {spec!r} does not exist")
            else:
                if args.verbose:
                    print(spec_path)
                try:
                    result, program = compile_mql(spec_path, institution_text)
                    errors.extend(check_vocabulary(spec_path, program, institution_data))
                    checked_mql += 1
                    if args.verbose:
                        print(result.json())
                except Exception as e:
                    errors.append(f"{spec_path}: {e}")

        # optional: catch .mql files that exist but aren't listed
        unlisted = {f for f in filenames if f.endswith(".mql")} - set(specs)
        for f in sorted(unlisted):
            logging.warning("%s: %s not listed in specializations", ssot_path, f)

    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print(
            f"validation failed: {len(errors)} error(s), {checked_mql} MQL file(s) compiled",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"validation passed: {checked_mql} MQL file(s) compiled")

if __name__ == "__main__":
    main()
