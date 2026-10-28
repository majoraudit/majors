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
    ap = argparse.ArgumentParser(description="Parse MQL files in ./majors")
    ap.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="print every visited file and its parsed MQL JSON",
    )
    ap.add_argument(
        "-D", "--define",
        dest="defines",
        action="append",
        default=[],
        metavar="NAME[=VALUE]",
        help="define an external value, like the C compiler's -D "
             "(-DNAME, -DNAME=VALUE, -D NAME=VALUE). "
             "Without =VALUE the value is '1'. May be repeated.",
    )
    return ap.parse_args(argv)


def parse_extern(defines):
    """Build the externals dict from -D style definitions (last one wins)."""
    result = {}
    for item in defines:
        name, sep, value = item.partition("=")
        if not NAME_RE.match(name):
            raise SystemExit(f"error: invalid name in -D {item!r}")
        if not sep:
            raise SystemExit(f"error: missing value in -D {item!r}")
        key = "$" + name
        if key in result:
            logging.warning("overriding %s, duplicate", key)
        result[key] = value #pylibmql.parse_extern_value(value)

    return result


def load_ssot(dirpath, filenames):
    """Return (path, data) for the directory's JSON file, or (None, None) if it has none."""
    jsons = [
        f for f in filenames
        if f.endswith(".json") and not f.startswith("README") and f != "manifest.json"
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


def parse_mql(path, extern):
    with open(path, "r") as f:
        result = pylibmql.parse_with_externals(f.read(), extern)
    jresult = json.loads(result.json())
    requirements = jresult.get("requirements") if isinstance(jresult, dict) else None
    if not isinstance(requirements, list) or not requirements:
        raise ValueError(f"no parsed requirements: {path}")
    return result


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

    args = parse_args()
    extern = parse_extern(args.defines)
    if args.verbose:
        print(f"externals: {extern}")

    target_dir = Path(__file__).resolve().parent / "majors"
    errors = []
    checked_mql = 0

    manifests = sorted(target_dir.glob("*/manifest.json"))
    if not manifests:
        errors.append(f"{target_dir}: no catalog-year manifest found")
    for manifest_path in manifests:
        errors.extend(validate_manifest(manifest_path))

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
                    result = parse_mql(spec_path, extern)
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
            f"validation failed: {len(errors)} error(s), {checked_mql} MQL file(s) parsed",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"validation passed: {checked_mql} MQL file(s) parsed")

if __name__ == "__main__":
    main()
