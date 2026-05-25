#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todo 数据持久层 — JSON 文件读写 + 列表/任务的 CRUD。"""

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today_iso() -> str:
    return date.today().isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


# 系统视图（不可删）：我的一天 / 重要 / 已计划 / 任务
SYSTEM_LISTS: List[Dict[str, Any]] = [
    {"id": "sys:my_day", "name": "我的一天", "system": True, "kind": "my_day"},
    {"id": "sys:important", "name": "重要", "system": True, "kind": "important"},
    {"id": "sys:planned", "name": "已计划", "system": True, "kind": "planned"},
    {"id": "sys:tasks", "name": "任务", "system": True, "kind": "tasks"},
]


class TodoStore:
    """JSON 文件持久化的列表/任务存储。"""

    def __init__(self, path: Path):
        self.path = path
        self.lists: List[Dict[str, Any]] = []
        self.tasks: List[Dict[str, Any]] = []
        self.load()

    # ── IO ──────────────────────────────────────────────

    def load(self) -> None:
        if not self.path.exists():
            self.lists, self.tasks = [], []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.lists = data.get("lists", [])
            self.tasks = data.get("tasks", [])
        except Exception:
            self.lists, self.tasks = [], []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"lists": self.lists, "tasks": self.tasks}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 列表 ────────────────────────────────────────────

    def all_lists(self) -> List[Dict[str, Any]]:
        return list(SYSTEM_LISTS) + list(self.lists)

    def get_list(self, list_id: str) -> Optional[Dict[str, Any]]:
        return next((l for l in self.all_lists() if l["id"] == list_id), None)

    def add_list(self, name: str) -> Dict[str, Any]:
        item = {"id": _new_id("u"), "name": name, "system": False}
        self.lists.append(item)
        self.save()
        return item

    def rename_list(self, list_id: str, new_name: str) -> None:
        for l in self.lists:
            if l["id"] == list_id:
                l["name"] = new_name
                break
        self.save()

    def remove_list(self, list_id: str) -> None:
        if list_id.startswith("sys:"):
            return
        self.lists = [l for l in self.lists if l["id"] != list_id]
        # 该列表下的任务回流到「任务」
        for t in self.tasks:
            if t.get("list_id") == list_id:
                t["list_id"] = "sys:tasks"
        self.save()

    # ── 任务 ────────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def add_task(self, title: str, list_id: str) -> Dict[str, Any]:
        """在所选列表下新增任务。系统视图选中时落到「任务」并继承标记。"""
        sys_view = next((l for l in SYSTEM_LISTS if l["id"] == list_id), None)
        target_list = list_id
        my_day = None
        important = False
        if sys_view:
            kind = sys_view["kind"]
            target_list = "sys:tasks"
            if kind == "my_day":
                my_day = _today_iso()
            elif kind == "important":
                important = True
            # planned 没有默认日期，留给用户在详情面板设置

        task = {
            "id": _new_id("t"),
            "list_id": target_list,
            "title": title,
            "completed": False,
            "important": important,
            "my_day_date": my_day,
            "due_date": None,
            "notes": "",
            "steps": [],
            "created_at": _now_iso(),
            "completed_at": None,
        }
        self.tasks.append(task)
        self.save()
        return task

    def update_task(self, task_id: str, **changes) -> None:
        for t in self.tasks:
            if t["id"] != task_id:
                continue
            if "completed" in changes:
                if changes["completed"] and not t.get("completed"):
                    changes["completed_at"] = _now_iso()
                elif not changes["completed"]:
                    changes["completed_at"] = None
            t.update(changes)
            break
        self.save()

    def remove_task(self, task_id: str) -> None:
        self.tasks = [t for t in self.tasks if t["id"] != task_id]
        self.save()

    def tasks_for_list(self, list_id: str) -> List[Dict[str, Any]]:
        sys_view = next((l for l in SYSTEM_LISTS if l["id"] == list_id), None)
        if sys_view:
            kind = sys_view["kind"]
            today = _today_iso()
            if kind == "my_day":
                return [t for t in self.tasks if t.get("my_day_date") == today]
            if kind == "important":
                return [t for t in self.tasks if t.get("important")]
            if kind == "planned":
                return [t for t in self.tasks if t.get("due_date")]
            if kind == "tasks":
                return [t for t in self.tasks if t["list_id"] == "sys:tasks"]
        return [t for t in self.tasks if t["list_id"] == list_id]

    # ── 步骤 ────────────────────────────────────────────

    def add_step(self, task_id: str, title: str) -> Optional[Dict[str, Any]]:
        task = self.get_task(task_id)
        if not task:
            return None
        step = {
            "id": _new_id("s"),
            "title": title,
            "completed": False,
        }
        task.setdefault("steps", []).append(step)
        self.save()
        return step

    def update_step(self, task_id: str, step_id: str, **changes) -> None:
        task = self.get_task(task_id)
        if not task:
            return
        for s in task.get("steps", []):
            if s["id"] == step_id:
                s.update(changes)
                break
        self.save()

    def remove_step(self, task_id: str, step_id: str) -> None:
        task = self.get_task(task_id)
        if not task:
            return
        task["steps"] = [s for s in task.get("steps", []) if s["id"] != step_id]
        self.save()