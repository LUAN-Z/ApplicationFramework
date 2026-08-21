#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install third-party dependencies into a plugin-local vendor directory."""

import argparse
import subprocess
import sys
from pathlib import Path


def _plugin_dir(raw_plugin: str) -> Path:
    path = Path(raw_plugin).expanduser()
    if path.is_file() and path.name == "requirements.txt":
        return path.parent.resolve()
    if path.is_file() and path.suffix == ".py":
        return path.parent.resolve()
    if path.name == "__init__.py":
        return path.parent.resolve()
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vendor a plugin's requirements into plugins/<plugin>/vendor."
    )
    parser.add_argument(
        "plugin",
        help="Plugin directory, plugin __init__.py, or plugin requirements.txt path.",
    )
    parser.add_argument(
        "--shared",
        action="store_true",
        help="Install into the parent plugins/vendor directory instead of plugin/vendor.",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Pass --upgrade to pip.",
    )
    args = parser.parse_args()

    plugin_dir = _plugin_dir(args.plugin)
    requirements = plugin_dir / "requirements.txt"
    if not requirements.exists():
        parser.error(f"requirements.txt not found: {requirements}")

    target = plugin_dir.parent / "vendor" if args.shared else plugin_dir / "vendor"
    target.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(requirements),
        "-t",
        str(target),
    ]
    if args.upgrade:
        command.append("--upgrade")

    print(f"Installing {requirements} -> {target}")
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
