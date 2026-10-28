import argparse
import logging
import os
import re
import subprocess
import sys
import importlib.metadata as md
from pathlib import Path

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


ensure_pylibmql()
import pylibmql


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Parse MQL files in ./majors")
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


def main():
    args = parse_args()
    extern = parse_extern(args.defines)
    print(extern)

    target_dir = Path(__file__).resolve().parent / "majors"

    for dirpath, _dirnames, filenames in os.walk(target_dir):
        print(f"Current Folder: {dirpath}")
        for filename in filenames:
            if filename.startswith("README"): 
                continue
            full_path = os.path.join(dirpath, filename)
            
            if full_path.endswith('json'):
                continue
            
            with open(full_path, "r") as file:
                pylibmql.parse_with_externals(file.read(), extern)


if __name__ == "__main__":
    main()