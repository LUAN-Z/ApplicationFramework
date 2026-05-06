#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command executor plugin runtime logic."""

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal


@dataclass(frozen=True)
class CommandTask:
    input_path: str
    output_path: str = ""
    args: str = ""


def build_command(
    template: str,
    tool: str,
    input_path: str,
    output_path: str,
    args: str,
) -> str:
    """Build a command line from the configured template."""

    return (
        template.replace("{tool}", tool)
        .replace("{input}", input_path)
        .replace("{output}", output_path)
        .replace("{args}", args)
    )


def default_output_path(input_path: str) -> str:
    """Return the default output path for a file input."""

    base, ext = os.path.splitext(input_path)
    return f"{base}_out{ext}"


def output_path_in_directory(input_path: str, output_dir: str) -> str:
    """Return the batch output path for a file or directory input."""

    basename = os.path.basename(input_path)
    name, ext = os.path.splitext(basename)
    if os.path.isdir(input_path):
        return os.path.join(output_dir, f"{basename}_out")
    return os.path.join(output_dir, f"{name}_out{ext}")


def ensure_output_directory(output_path: str) -> None:
    """Create the output directory when an output path contains one."""

    if not output_path:
        return

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)


def windows_startupinfo():
    """Hide the subprocess window on Windows."""

    if sys.platform != "win32":
        return None

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def get_tool_help(tool_path: str, timeout: int = 10) -> str:
    """Fetch command line help text using --help first, then -h."""

    if not tool_path or not os.path.exists(tool_path):
        raise FileNotFoundError("请先选择有效的命令行工具")

    last_error = None
    for flag in ("--help", "-h"):
        try:
            result = subprocess.run(
                [tool_path, flag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=windows_startupinfo(),
                timeout=timeout,
            )
            output = result.stdout or result.stderr
            if output:
                return output
        except subprocess.TimeoutExpired:
            return f"获取帮助超时，该工具可能不支持 {flag} 参数"
        except Exception as exc:
            last_error = exc

    if last_error:
        return f"获取帮助失败: {last_error}"
    return "该工具没有返回帮助信息"


class CommandExecutor(QThread):
    """Run one command in a worker thread."""

    finished = pyqtSignal(int, str, str)
    output = pyqtSignal(int, str)

    def __init__(self, row: int, cmd: str, cwd: Optional[str] = None):
        super().__init__()
        self.row = row
        self.cmd = cmd
        self.cwd = cwd
        self._is_running = True
        self._process = None

    def run(self):
        try:
            if not self._is_running:
                return

            self._process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.cwd,
                startupinfo=windows_startupinfo(),
                shell=True,
            )

            output_lines = []
            for line in iter(self._process.stdout.readline, ""):
                if not self._is_running:
                    self._process.terminate()
                    break
                if line:
                    output_lines.append(line)
                    self.output.emit(self.row, line)

            self._process.stdout.close()
            return_code = self._process.wait()
            status = "成功" if return_code == 0 else f"失败 (code:{return_code})"
            self.finished.emit(self.row, status, "".join(output_lines))
        except Exception as exc:
            self.finished.emit(self.row, "错误", str(exc))
        finally:
            self._process = None

    def stop(self):
        self._is_running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
