#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插件私有依赖路径引导。"""

import sys
from pathlib import Path


def add_plugin_dependency_paths() -> None:
    plugin_dir = Path(__file__).resolve().parent
    for dependency_path in (plugin_dir, plugin_dir / "vendor", plugin_dir / "deps"):
        if dependency_path.exists():
            raw_path = str(dependency_path)
            if raw_path not in sys.path:
                sys.path.insert(0, raw_path)
