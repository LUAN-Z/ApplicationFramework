#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间日志数据持久层 — JSON 文件读写 + CRUD + 标签解析。"""

import json
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


# 形如 #tag / #中文标签 / #tag-1
_TAG_RE = re.compile(r"#([\w一-龥][\w一-龥\-]*)", re.UNICODE)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return f"e:{uuid.uuid4().hex[:12]}"


def extract_tags(text: str) -> List[str]:
    """从文本中抽取 #tag,保持出现顺序去重。"""
    seen, out = set(), []
    for m in _TAG_RE.finditer(text or ""):
        tag = m.group(1)
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


class TimeLogStore:
    """JSON 文件持久化的时间日志存储。"""

    def __init__(self, path: Path):
        self.path = path
        self.entries: List[Dict[str, Any]] = []
        self.load()

    # ── IO ──────────────────────────────────────────────

    def load(self) -> None:
        if not self.path.exists():
            self.entries = []
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = data.get("entries", [])
        except Exception:
            self.entries = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": self.entries}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── CRUD ────────────────────────────────────────────

    def add_entry(self, text: str, ts: Optional[str] = None) -> Dict[str, Any]:
        entry = {
            "id": _new_id(),
            "ts": ts or _now_iso(),
            "text": text,
            "tags": extract_tags(text),
        }
        self.entries.append(entry)
        self.save()
        return entry

    def update_entry(self, entry_id: str, **changes) -> Optional[Dict[str, Any]]:
        for e in self.entries:
            if e["id"] != entry_id:
                continue
            if "text" in changes:
                changes["tags"] = extract_tags(changes["text"])
            e.update(changes)
            self.save()
            return e
        return None

    def remove_entry(self, entry_id: str) -> None:
        self.entries = [e for e in self.entries if e["id"] != entry_id]
        self.save()

    def get_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        return next((e for e in self.entries if e["id"] == entry_id), None)

    def clear_all(self) -> None:
        self.entries = []
        self.save()

    # ── 查询 ────────────────────────────────────────────

    @staticmethod
    def _entry_date(entry: Dict[str, Any]) -> Optional[date]:
        try:
            return datetime.fromisoformat(entry["ts"]).date()
        except (KeyError, ValueError):
            return None

    def all_dates(self) -> List[date]:
        """返回所有出现过的日期(降序)。"""
        seen = set()
        for e in self.entries:
            d = self._entry_date(e)
            if d:
                seen.add(d)
        return sorted(seen, reverse=True)

    def date_counts(self) -> Dict[date, int]:
        c: Counter = Counter()
        for e in self.entries:
            d = self._entry_date(e)
            if d:
                c[d] += 1
        return dict(c)

    def all_tags(self) -> List[str]:
        seen, out = set(), []
        for e in self.entries:
            for t in e.get("tags", []):
                if t not in seen:
                    seen.add(t)
                    out.append(t)
        return out

    def tag_counts(self) -> Dict[str, int]:
        c: Counter = Counter()
        for e in self.entries:
            for t in e.get("tags", []):
                c[t] += 1
        return dict(c)

    def filter_entries(
        self,
        *,
        bucket: str = "all",
        single_date: Optional[date] = None,
        keyword: str = "",
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """按桶 / 日期 / 关键字 / 标签过滤。返回按时间倒序的列表。"""
        today = date.today()
        kw = (keyword or "").lower().strip()
        tag_set = set(tags or [])

        def in_bucket(d: Optional[date]) -> bool:
            if d is None:
                return False
            if bucket == "all":
                return True
            if bucket == "today":
                return d == today
            if bucket == "yesterday":
                return d == today - timedelta(days=1)
            if bucket == "this_week":
                start = today - timedelta(days=today.weekday())
                return start <= d <= today
            if bucket == "last_week":
                this_start = today - timedelta(days=today.weekday())
                last_start = this_start - timedelta(days=7)
                last_end = this_start - timedelta(days=1)
                return last_start <= d <= last_end
            if bucket == "date" and single_date is not None:
                return d == single_date
            return True

        out: List[Dict[str, Any]] = []
        for e in self.entries:
            d = self._entry_date(e)
            if not in_bucket(d):
                continue
            if kw:
                hay = (e.get("text") or "").lower()
                if kw not in hay and not any(kw in t.lower() for t in e.get("tags", [])):
                    continue
            if tag_set and not tag_set.issubset(set(e.get("tags", []))):
                continue
            out.append(e)

        out.sort(key=lambda e: e.get("ts") or "", reverse=True)
        return out

    # ── 统计 ────────────────────────────────────────────

    def stats(self) -> Dict[str, int]:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        c_today = c_week = 0
        for e in self.entries:
            d = self._entry_date(e)
            if d == today:
                c_today += 1
            if d and week_start <= d <= today:
                c_week += 1
        return {
            "total": len(self.entries),
            "today": c_today,
            "this_week": c_week,
            "tags": len(self.all_tags()),
        }

    # ── 导入 / 导出 ──────────────────────────────────────

    def export_markdown(self) -> str:
        """按日期分组导出为 Markdown。"""
        groups: Dict[date, List[Dict[str, Any]]] = {}
        for e in self.entries:
            d = self._entry_date(e) or date.today()
            groups.setdefault(d, []).append(e)

        lines: List[str] = ["# 时间日志", ""]
        for d in sorted(groups.keys(), reverse=True):
            lines.append(f"## {d.isoformat()}")
            for e in sorted(groups[d], key=lambda x: x.get("ts") or ""):
                try:
                    hm = datetime.fromisoformat(e["ts"]).strftime("%H:%M")
                except (KeyError, ValueError):
                    hm = "--:--"
                text = (e.get("text") or "").replace("\n", "  \n")
                lines.append(f"- **{hm}** {text}")
            lines.append("")
        return "\n".join(lines)

    def export_json(self) -> str:
        return json.dumps(
            {"entries": self.entries}, ensure_ascii=False, indent=2
        )

    def import_json(self, raw: str, *, replace: bool = False) -> int:
        """导入 JSON 字符串。返回新增条数。"""
        data = json.loads(raw)
        new_entries = data.get("entries", []) if isinstance(data, dict) else data
        if not isinstance(new_entries, list):
            raise ValueError("JSON 格式不符合预期 (需要 list 或 {entries: [...]} )")

        existing_ids = {e["id"] for e in self.entries if "id" in e}
        added = 0
        for raw_e in new_entries:
            if not isinstance(raw_e, dict) or "text" not in raw_e:
                continue
            entry = {
                "id": raw_e.get("id") or _new_id(),
                "ts": raw_e.get("ts") or _now_iso(),
                "text": raw_e.get("text") or "",
                "tags": raw_e.get("tags") or extract_tags(raw_e.get("text") or ""),
            }
            if not replace and entry["id"] in existing_ids:
                # 自动换 id 避免冲突
                entry["id"] = _new_id()
            self.entries.append(entry)
            added += 1

        if replace:
            self.entries = self.entries[-added:] if added else []
        self.save()
        return added