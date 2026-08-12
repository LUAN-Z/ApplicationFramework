#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间日志 UI — 仿日报/工作日志,左侧日期桶 + 右侧时间线。"""

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont, QTextOption
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon as FIF,
    FlowLayout,
    IconWidget,
    InfoBadge,
    InfoBar,
    InfoBarPosition,
    LargeTitleLabel,
    LineEdit,
    ListWidget,
    PillPushButton,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SimpleCardWidget,
    SmoothScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TextEdit,
    TransparentToolButton,
    isDarkTheme,
    qconfig,
    themeColor,
)

try:
    from .storage import TimeLogStore, extract_tags
except ImportError:
    from storage import TimeLogStore, extract_tags


WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _muted_color() -> str:
    return "#9DA3A8" if isDarkTheme() else "#666"


def _subtle_color() -> str:
    return "#6E7378" if isDarkTheme() else "#888"


def _embed_lineedit_style() -> str:
    """主题感知的 LineEdit 透明嵌入样式;包含 color 以避免在深色主题下退回到默认黑色。"""
    color = "#F2F2F2" if isDarkTheme() else "#202020"
    return f"LineEdit {{ border: 0; background: transparent; color: {color}; }}"


def _format_day_label(d: date) -> str:
    today = date.today()
    delta = (today - d).days
    wd = WEEKDAY_CN[d.weekday()]
    if delta == 0:
        return f"今天 · {wd}"
    if delta == 1:
        return f"昨天 · {wd}"
    if 2 <= delta <= 6:
        return f"{d.strftime('%m-%d')} · {wd}"
    return f"{d.isoformat()} · {wd}"


def _format_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return ts or ""
    today = date.today()
    delta = (today - dt.date()).days
    hm = dt.strftime("%H:%M")
    if delta == 0:
        return f"今天 {hm}"
    if delta == 1:
        return f"昨天 {hm}"
    if 1 < delta <= 6:
        return f"{WEEKDAY_CN[dt.weekday()]} {hm}"
    return dt.strftime("%Y-%m-%d %H:%M")


# ── 桶 / 日期栏 ───────────────────────────────────────────

class BucketsPane(QWidget):
    """左栏:系统桶 + 每日列表(均通过 ListWidget 呈现)。"""

    bucketSelected = pyqtSignal(str, object)  # (bucket_key, date|None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setObjectName("TimeLogBucketsPane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(8)

        # 标题
        title_row = QHBoxLayout()
        title_row.setContentsMargins(6, 0, 6, 0)
        title_row.addWidget(SubtitleLabel("时间日志", self))
        title_row.addStretch(1)
        layout.addLayout(title_row)

        self.list_widget = ListWidget(self)
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setSpacing(2)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.list_widget, 1)

    def populate(
        self,
        stats: Dict[str, int],
        date_counts: Dict[date, int],
        all_dates: List[date],
        current_key: str,
        current_date: Optional[date],
    ):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        SYS = [
            ("today", FIF.BRIGHTNESS, "今天", stats.get("today", 0)),
            (
                "yesterday",
                FIF.HISTORY,
                "昨天",
                date_counts.get(date.today() - timedelta(days=1), 0),
            ),
            ("this_week", FIF.CALENDAR, "本周", stats.get("this_week", 0)),
            ("all", FIF.LIBRARY, "全部", stats.get("total", 0)),
        ]

        for key, icon, name, count in SYS:
            label = name if count == 0 else f"{name}  ·  {count}"
            it = QListWidgetItem(icon.icon(), label)
            it.setData(Qt.UserRole, ("bucket", key))
            self.list_widget.addItem(it)

        # 「按日期」标题(不可选)
        if all_dates:
            header = QListWidgetItem("按日期")
            header.setFlags(Qt.NoItemFlags)
            f = header.font()
            f.setBold(True)
            f.setPointSize(max(8, f.pointSize() - 1))
            header.setFont(f)
            header.setForeground(
                self.palette().color(self.palette().Disabled,
                                     self.palette().WindowText)
            )
            self.list_widget.addItem(header)

            for d in all_dates:
                count = date_counts.get(d, 0)
                label = f"{_format_day_label(d)}  ·  {count}"
                it = QListWidgetItem(FIF.DATE_TIME.icon(), label)
                it.setData(Qt.UserRole, ("date", d.isoformat()))
                self.list_widget.addItem(it)

        # 还原选中
        target = ("bucket", current_key) if current_key != "date" else (
            "date", current_date.isoformat() if current_date else ""
        )
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.UserRole) == target:
                self.list_widget.setCurrentItem(it)
                break
        else:
            # 默认选第一项 (today)
            if self.list_widget.count():
                self.list_widget.setCurrentRow(0)

        self.list_widget.blockSignals(False)

    def _on_current_changed(self, cur, _prev):
        if not cur:
            return
        data = cur.data(Qt.UserRole)
        if not data:
            return
        kind, val = data
        if kind == "bucket":
            self.bucketSelected.emit(val, None)
        elif kind == "date":
            try:
                d = date.fromisoformat(val)
            except ValueError:
                return
            self.bucketSelected.emit("date", d)


# ── 单条日志卡片 ───────────────────────────────────────────

class EntryRow(CardWidget):

    editRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    tagClicked = pyqtSignal(str)

    def __init__(self, entry: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setMinimumHeight(60)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 10, 10, 10)
        outer.setSpacing(10)

        # 左侧时间戳列
        ts_box = QVBoxLayout()
        ts_box.setContentsMargins(0, 2, 0, 0)
        ts_box.setSpacing(2)
        try:
            dt = datetime.fromisoformat(entry["ts"])
            time_text = dt.strftime("%H:%M")
            date_text = dt.strftime("%m-%d")
        except (KeyError, ValueError):
            time_text, date_text = "--:--", ""

        time_label = StrongBodyLabel(time_text, self)
        ts_box.addWidget(time_label)

        date_label = CaptionLabel(date_text, self)
        ts_box.addWidget(date_label)
        ts_box.addStretch(1)

        self._time_label = time_label
        self._date_label = date_label
        self.refresh_theme_styles()

        ts_widget = QWidget(self)
        ts_widget.setLayout(ts_box)
        ts_widget.setFixedWidth(56)
        outer.addWidget(ts_widget, 0, Qt.AlignTop)

        # 中间正文 + 标签
        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        self.text_label = BodyLabel(entry.get("text", ""), self)
        self.text_label.setWordWrap(True)
        self.text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.text_label)

        tags = entry.get("tags") or []
        if tags:
            # 用 QHBoxLayout 而非 FlowLayout — FlowLayout 的 heightForWidth
            # 不会被父 QVBoxLayout 主动查询,导致卡片首次布局时高度被算少。
            # 标签通常不多 (1-5 个),单行排布完全够用。
            tag_row = QHBoxLayout()
            tag_row.setContentsMargins(0, 0, 0, 0)
            tag_row.setSpacing(4)
            for t in tags:
                chip = self._make_tag_chip(t)
                tag_row.addWidget(chip)
            tag_row.addStretch(1)
            body.addLayout(tag_row)

        outer.addLayout(body, 1)

        # 右侧操作
        actions = QVBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(2)

        self.edit_btn = TransparentToolButton(FIF.EDIT, self)
        self.edit_btn.setFixedSize(28, 28)
        self.edit_btn.setToolTip("编辑")
        self.edit_btn.clicked.connect(
            lambda: self.editRequested.emit(self.entry["id"])
        )
        actions.addWidget(self.edit_btn)

        self.del_btn = TransparentToolButton(FIF.DELETE, self)
        self.del_btn.setFixedSize(28, 28)
        self.del_btn.setToolTip("删除")
        self.del_btn.clicked.connect(
            lambda: self.deleteRequested.emit(self.entry["id"])
        )
        actions.addWidget(self.del_btn)
        actions.addStretch(1)

        actions_widget = QWidget(self)
        actions_widget.setLayout(actions)
        outer.addWidget(actions_widget, 0, Qt.AlignTop)

    def refresh_theme_styles(self):
        """主题切换后刷新依赖 themeColor()/isDarkTheme() 的颜色。"""
        if hasattr(self, "_time_label"):
            self._time_label.setStyleSheet(
                f"color: {themeColor().name()};"
            )
        if hasattr(self, "_date_label"):
            self._date_label.setStyleSheet(
                f"color: {_subtle_color()};"
            )

    def _make_tag_chip(self, tag: str) -> QWidget:
        chip = PillPushButton(self)
        chip.setText(f"#{tag}")
        chip.setCheckable(False)
        chip.setFixedHeight(24)
        font = chip.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        chip.setFont(font)
        chip.clicked.connect(lambda _c=False, t=tag: self.tagClicked.emit(t))
        return chip


# ── 编辑对话框 ────────────────────────────────────────────

from qfluentwidgets import MessageBoxBase


class EntryEditDialog(MessageBoxBase):
    """新增/编辑条目对话框。"""

    def __init__(self, parent=None, title: str = "编辑条目", initial: str = ""):
        super().__init__(parent)

        self.titleLabel = SubtitleLabel(title, self)
        self.text_edit = TextEdit(self)
        self.text_edit.setPlaceholderText(
            "记录内容…\n支持 #标签 标记,如 #开发 #会议"
        )
        self.text_edit.setMinimumHeight(160)
        if initial:
            self.text_edit.setPlainText(initial)

        hint = CaptionLabel("提示:在文本中加入 #标签 即可自动归类", self)
        hint.setStyleSheet(f"color: {_subtle_color()};")

        self.warningLabel = CaptionLabel("内容不能为空", self)
        self.warningLabel.setTextColor("#cf1010", QColor(255, 28, 32))
        self.warningLabel.hide()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.text_edit)
        self.viewLayout.addWidget(hint)
        self.viewLayout.addWidget(self.warningLabel)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(420)

    def validate(self) -> bool:
        if not self.text_edit.toPlainText().strip():
            self.warningLabel.show()
            return False
        self.warningLabel.hide()
        return True

    def value(self) -> str:
        return self.text_edit.toPlainText().strip()


# ── 时间线主面板 ───────────────────────────────────────────

class TimelinePane(QWidget):

    addRequested = pyqtSignal(str)
    editRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    searchChanged = pyqtSignal(str)
    tagFilterChanged = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(12)

        # 标题区
        head_row = QHBoxLayout()
        head_row.setSpacing(12)

        self.head_icon = IconWidget(FIF.BRIGHTNESS, self)
        self.head_icon.setFixedSize(36, 36)
        head_row.addWidget(self.head_icon, 0, Qt.AlignVCenter)

        head_text = QVBoxLayout()
        head_text.setContentsMargins(0, 0, 0, 0)
        head_text.setSpacing(2)
        self.title = LargeTitleLabel("今天", self)
        self.subtitle = CaptionLabel("", self)
        head_text.addWidget(self.title)
        head_text.addWidget(self.subtitle)
        head_row.addLayout(head_text, 1)

        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText("搜索内容或标签…")
        self.search.setFixedWidth(240)
        self.search.searchSignal.connect(self.searchChanged.emit)
        self.search.clearSignal.connect(lambda: self.searchChanged.emit(""))
        self.search.returnPressed.connect(
            lambda: self.search.search() if self.search.text().strip()
            else self.search.clearSignal.emit()
        )
        head_row.addWidget(self.search, 0, Qt.AlignVCenter)

        # 操作菜单
        more_btn = TransparentToolButton(FIF.MORE, self)
        more_btn.setToolTip("更多操作")
        more_btn.setFixedSize(36, 36)
        self._more_btn = more_btn
        head_row.addWidget(more_btn, 0, Qt.AlignVCenter)
        layout.addLayout(head_row)

        # 标签筛选条
        tag_card = SimpleCardWidget(self)
        tag_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        tag_card.setMinimumHeight(44)
        tag_layout = QHBoxLayout(tag_card)
        tag_layout.setContentsMargins(12, 8, 12, 8)
        tag_layout.setSpacing(8)

        tag_icon = IconWidget(FIF.TAG, self)
        tag_icon.setFixedSize(14, 14)
        tag_layout.addWidget(tag_icon, 0, Qt.AlignVCenter)

        tag_label = CaptionLabel("标签", self)
        tag_layout.addWidget(tag_label, 0, Qt.AlignVCenter)
        self._tag_label = tag_label

        self._tag_pills_holder = QWidget(self)
        self._tag_pills_holder.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        self._tag_pills_layout = FlowLayout(
            self._tag_pills_holder, needAni=False, isTight=False
        )
        self._tag_pills_layout.setContentsMargins(0, 0, 0, 0)
        self._tag_pills_layout.setVerticalSpacing(6)
        self._tag_pills_layout.setHorizontalSpacing(6)
        tag_layout.addWidget(self._tag_pills_holder, 1)

        self.tag_clear_btn = TransparentToolButton(FIF.CLOSE, self)
        self.tag_clear_btn.setToolTip("清除标签筛选")
        self.tag_clear_btn.setFixedSize(28, 28)
        self.tag_clear_btn.clicked.connect(self._clear_tag_filter)
        self.tag_clear_btn.hide()
        tag_layout.addWidget(self.tag_clear_btn, 0, Qt.AlignVCenter)

        self._tag_card = tag_card
        # 默认隐藏 — 仅当有标签时再显示
        self._tag_card.hide()
        layout.addWidget(tag_card)

        # 滚动区
        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: 0; }"
        )
        self.scroll_inner = QWidget()
        self.scroll_inner.setStyleSheet("background: transparent;")
        self.rows_layout = QVBoxLayout(self.scroll_inner)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(8)

        self.empty_widget = self._build_empty()
        self.rows_layout.addWidget(self.empty_widget)
        self.rows_layout.addStretch(1)

        self.scroll.setWidget(self.scroll_inner)
        layout.addWidget(self.scroll, 1)

        # 输入区
        input_card = SimpleCardWidget(self)
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(8)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)

        plus = IconWidget(FIF.ADD, self)
        plus.setFixedSize(16, 16)
        edit_row.addWidget(plus, 0, Qt.AlignVCenter)

        self.input_edit = LineEdit(self)
        self.input_edit.setPlaceholderText("记录一条 (回车提交,可用 #标签)")
        self.input_edit.setStyleSheet(_embed_lineedit_style())
        self.input_edit.returnPressed.connect(self._on_quick_add)
        edit_row.addWidget(self.input_edit, 1)

        submit = PrimaryPushButton("记录", self)
        submit.setIcon(FIF.SEND)
        submit.clicked.connect(self._on_quick_add)
        edit_row.addWidget(submit, 0, Qt.AlignVCenter)

        input_layout.addLayout(edit_row)
        layout.addWidget(input_card)

        # 统计栏
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(2, 0, 2, 0)
        stats_row.setSpacing(12)
        self.stats_label = CaptionLabel("", self)
        stats_row.addWidget(self.stats_label)
        stats_row.addStretch(1)
        layout.addLayout(stats_row)

        # 内部状态
        self._active_tags: List[str] = []
        self._tag_buttons: Dict[str, PillPushButton] = {}

        # 初次应用主题相关样式
        self.refresh_theme_styles()

    def _build_empty(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 80, 0, 60)
        v.setSpacing(10)
        ic = IconWidget(FIF.QUICK_NOTE, w)
        ic.setFixedSize(48, 48)
        v.addWidget(ic, 0, Qt.AlignCenter)
        msg = SubtitleLabel("还没有日志", w)
        msg.setAlignment(Qt.AlignCenter)
        v.addWidget(msg)
        sub = BodyLabel("从下方输入框开始记录,加入 #标签 自动归类", w)
        sub.setAlignment(Qt.AlignCenter)
        v.addWidget(sub)
        self._empty_sub = sub
        return w

    # ── 公共 ──

    def refresh_theme_styles(self):
        """主题切换后重新喂入依赖 isDarkTheme() 的颜色。"""
        subtle = _subtle_color()
        for label in (
            self.subtitle,
            getattr(self, "_tag_label", None),
            self.stats_label,
            getattr(self, "_empty_sub", None),
        ):
            if label is not None:
                label.setStyleSheet(f"color: {subtle};")
        # 透明嵌入式输入框的文字色也要跟主题刷新
        if hasattr(self, "input_edit"):
            self.input_edit.setStyleSheet(_embed_lineedit_style())
        # 时间戳主题色 — 重新刷一遍
        for row in self.findChildren(EntryRow):
            row.refresh_theme_styles()

    def set_more_menu(self, menu: RoundMenu):
        self._more_btn.clicked.connect(
            lambda: menu.exec_(
                self._more_btn.mapToGlobal(
                    self._more_btn.rect().bottomRight()
                )
            )
        )

    def set_header(self, icon, name: str, count: int, hint: str = ""):
        self.head_icon.setIcon(icon)
        self.title.setText(name)
        if count == 0:
            base = "还没有日志"
        else:
            base = f"{count} 条记录"
        if hint:
            base = f"{base} · {hint}"
        self.subtitle.setText(base)

    def set_stats(self, stats: Dict[str, int]):
        self.stats_label.setText(
            f"今天 {stats.get('today', 0)} · 本周 {stats.get('this_week', 0)} · "
            f"全部 {stats.get('total', 0)} · 标签 {stats.get('tags', 0)}"
        )

    def populate_tags(self, tag_counts: Dict[str, int]):
        # 清旧 — qfluentwidgets 的 FlowLayout.takeAllWidgets 内部已 deleteLater
        try:
            self._tag_pills_layout.takeAllWidgets()
        except AttributeError:
            while self._tag_pills_layout.count():
                w = self._tag_pills_layout.takeAt(0)
                if w is None:
                    continue
                if hasattr(w, "widget"):
                    w = w.widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
        self._tag_buttons.clear()

        # 没有标签时整条筛选区直接隐藏,避免出现空的占位框
        if not tag_counts:
            self._tag_card.hide()
            return

        self._tag_card.show()

        # 按次数降序
        sorted_tags = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        for tag, cnt in sorted_tags:
            btn = PillPushButton(self)
            btn.setText(f"#{tag}  {cnt}")
            btn.setCheckable(True)
            btn.setChecked(tag in self._active_tags)
            btn.toggled.connect(
                lambda checked, t=tag: self._on_tag_toggled(t, checked)
            )
            self._tag_pills_layout.addWidget(btn)
            self._tag_buttons[tag] = btn

        self.tag_clear_btn.setVisible(bool(self._active_tags))

    def show_entries(self, entries: List[Dict[str, Any]]):
        # 清旧
        for i in reversed(range(self.rows_layout.count())):
            item = self.rows_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, EntryRow):
                self.rows_layout.takeAt(i)
                w.deleteLater()

        if not entries:
            self.empty_widget.show()
            return

        self.empty_widget.hide()
        for e in entries:
            row = EntryRow(e, self)
            row.editRequested.connect(self.editRequested.emit)
            row.deleteRequested.connect(self.deleteRequested.emit)
            row.tagClicked.connect(self._on_tag_chip_clicked)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)

    def set_active_tags(self, tags: List[str]):
        self._active_tags = list(tags)
        for tag, btn in self._tag_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(tag in self._active_tags)
            btn.blockSignals(False)
        self.tag_clear_btn.setVisible(bool(self._active_tags))

    # ── 事件 ──

    def _on_quick_add(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self.addRequested.emit(text)

    def _on_tag_toggled(self, tag: str, checked: bool):
        if checked and tag not in self._active_tags:
            self._active_tags.append(tag)
        elif not checked and tag in self._active_tags:
            self._active_tags.remove(tag)
        self.tag_clear_btn.setVisible(bool(self._active_tags))
        self.tagFilterChanged.emit(list(self._active_tags))

    def _on_tag_chip_clicked(self, tag: str):
        if tag in self._active_tags:
            return
        self._active_tags.append(tag)
        if tag in self._tag_buttons:
            btn = self._tag_buttons[tag]
            btn.blockSignals(True)
            btn.setChecked(True)
            btn.blockSignals(False)
        self.tag_clear_btn.setVisible(True)
        self.tagFilterChanged.emit(list(self._active_tags))

    def _clear_tag_filter(self):
        self._active_tags.clear()
        for btn in self._tag_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self.tag_clear_btn.hide()
        self.tagFilterChanged.emit([])


# ── 主页面 ────────────────────────────────────────────────

class TimeLogPage(QWidget):
    """两栏布局根。"""

    BUCKET_LABELS = {
        "today": ("今天", FIF.BRIGHTNESS),
        "yesterday": ("昨天", FIF.HISTORY),
        "this_week": ("本周", FIF.CALENDAR),
        "last_week": ("上周", FIF.CALENDAR),
        "all": ("全部", FIF.LIBRARY),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TimeLogPage")

        data_dir = Path.home() / ".application_framework" / "time_log"
        self.store = TimeLogStore(data_dir / "data.json")

        self.current_bucket = "today"
        self.current_date: Optional[date] = None
        self._search_keyword = ""
        self._active_tags: List[str] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.buckets_pane = BucketsPane(self)
        self.buckets_pane.setAutoFillBackground(True)
        root.addWidget(self.buckets_pane)

        self.timeline_pane = TimelinePane(self)
        root.addWidget(self.timeline_pane, 1)

        self._apply_theme_styles()
        # 监听主题切换,实时刷新依赖 isDarkTheme() 计算的样式
        qconfig.themeChanged.connect(self._apply_theme_styles)

        self._build_more_menu()
        self._wire()
        self._refresh_all()

    def _apply_theme_styles(self):
        """主题切换时重新计算所有依赖 isDarkTheme() 的内联样式。"""
        dark = isDarkTheme()
        self.buckets_pane.setStyleSheet(
            f"QWidget#TimeLogBucketsPane {{ "
            f"background: {'#1a1a1a' if dark else '#f3f3f3'}; "
            f"border-right: 1px solid "
            f"{'#2c2c2c' if dark else '#e5e5e5'}; "
            f"}}"
        )
        # 把 _subtle_color 重新喂给所有用到的子标签
        self.timeline_pane.refresh_theme_styles()
        # 主题切换时强制重建列表项,刷新 QListWidgetItem 缓存的图标 pixmap
        # (FluentIconEngine 本身随主题变色,但 QListWidgetItem 不会自动重绘)
        try:
            self._refresh_all()
        except AttributeError:
            # __init__ 还未跑完 _wire 之前的早期调用,store 还没就绪
            pass

    # ── 信号 ──

    def _wire(self):
        self.buckets_pane.bucketSelected.connect(self._on_bucket_selected)

        T = self.timeline_pane
        T.addRequested.connect(self._on_add)
        T.editRequested.connect(self._on_edit)
        T.deleteRequested.connect(self._on_delete)
        T.searchChanged.connect(self._on_search_changed)
        T.tagFilterChanged.connect(self._on_tag_filter_changed)

    def _build_more_menu(self):
        menu = RoundMenu("", self)
        act_export_md = QAction(FIF.SAVE.icon(), "导出为 Markdown", self)
        act_export_md.triggered.connect(self._export_markdown)
        menu.addAction(act_export_md)

        act_export_json = QAction(FIF.CODE.icon(), "导出为 JSON", self)
        act_export_json.triggered.connect(self._export_json)
        menu.addAction(act_export_json)

        menu.addSeparator()

        act_import_json = QAction(FIF.FOLDER.icon(), "从 JSON 导入…", self)
        act_import_json.triggered.connect(self._import_json)
        menu.addAction(act_import_json)

        menu.addSeparator()
        act_clear_all = QAction(FIF.DELETE.icon(), "清空所有日志…", self)
        act_clear_all.triggered.connect(self._clear_all)
        menu.addAction(act_clear_all)

        self._more_menu = menu  # 保持引用
        self.timeline_pane.set_more_menu(menu)

    # ── 视图刷新 ──

    def _filtered_entries(self) -> List[Dict[str, Any]]:
        return self.store.filter_entries(
            bucket=self.current_bucket,
            single_date=self.current_date,
            keyword=self._search_keyword,
            tags=self._active_tags,
        )

    def _refresh_all(self):
        # 左栏
        self.buckets_pane.populate(
            self.store.stats(),
            self.store.date_counts(),
            self.store.all_dates(),
            self.current_bucket,
            self.current_date,
        )
        # 标签
        self.timeline_pane.populate_tags(self.store.tag_counts())
        self.timeline_pane.set_active_tags(self._active_tags)
        # 内容
        self._refresh_timeline()

    def _refresh_timeline(self):
        entries = self._filtered_entries()

        if self.current_bucket == "date" and self.current_date is not None:
            name = _format_day_label(self.current_date)
            icon = FIF.DATE_TIME
        else:
            name, icon = self.BUCKET_LABELS.get(
                self.current_bucket, ("日志", FIF.LIBRARY)
            )

        hint_parts = []
        if self._search_keyword:
            hint_parts.append(f"搜索: {self._search_keyword}")
        if self._active_tags:
            hint_parts.append(
                "标签: " + " ".join(f"#{t}" for t in self._active_tags)
            )
        self.timeline_pane.set_header(
            icon, name, len(entries), " · ".join(hint_parts)
        )
        self.timeline_pane.show_entries(entries)
        self.timeline_pane.set_stats(self.store.stats())

    # ── 桶 / 搜索 / 标签 ──

    def _on_bucket_selected(self, bucket_key: str, single_date):
        self.current_bucket = bucket_key
        self.current_date = single_date if isinstance(single_date, date) else None
        self._refresh_timeline()

    def _on_search_changed(self, keyword: str):
        self._search_keyword = (keyword or "").strip()
        self._refresh_timeline()

    def _on_tag_filter_changed(self, tags: List[str]):
        self._active_tags = list(tags)
        self._refresh_timeline()

    # ── CRUD ──

    def _on_add(self, text: str):
        entry = self.store.add_entry(text)
        InfoBar.success(
            title="已记录",
            content=text if len(text) <= 30 else text[:30] + "…",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
        )
        # 添加后跳到「今天」更直观
        self.current_bucket = "today"
        self.current_date = None
        self._refresh_all()

    def _on_edit(self, entry_id: str):
        entry = self.store.get_entry(entry_id)
        if not entry:
            return
        dlg = EntryEditDialog(
            parent=self.window(),
            title="编辑条目",
            initial=entry.get("text", ""),
        )
        if dlg.exec():
            new_text = dlg.value()
            if new_text and new_text != entry.get("text"):
                self.store.update_entry(entry_id, text=new_text)
                self._refresh_all()

    def _on_delete(self, entry_id: str):
        from customWidget import MessageConfirmBox

        entry = self.store.get_entry(entry_id)
        if not entry:
            return
        preview = entry.get("text", "")
        if len(preview) > 40:
            preview = preview[:40] + "…"
        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="删除条目",
            content=f"确定删除以下记录?\n\n{preview}",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return
        self.store.remove_entry(entry_id)
        self._refresh_all()

    # ── 导入 / 导出 ──

    def _export_markdown(self):
        if not self.store.entries:
            InfoBar.warning(
                title="无数据",
                content="还没有任何日志可导出",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出为 Markdown",
            f"time_log_{date.today().isoformat()}.md",
            "Markdown (*.md);;所有文件 (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self.store.export_markdown(), encoding="utf-8")
            InfoBar.success(
                title="已导出",
                content=os.path.basename(path),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
        except Exception as e:
            InfoBar.error(
                title="导出失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )

    def _export_json(self):
        if not self.store.entries:
            InfoBar.warning(
                title="无数据",
                content="还没有任何日志可导出",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出为 JSON",
            f"time_log_{date.today().isoformat()}.json",
            "JSON (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            Path(path).write_text(self.store.export_json(), encoding="utf-8")
            InfoBar.success(
                title="已导出",
                content=os.path.basename(path),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
        except Exception as e:
            InfoBar.error(
                title="导出失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "从 JSON 导入", "",
            "JSON (*.json);;所有文件 (*)",
        )
        if not path:
            return
        try:
            raw = Path(path).read_text(encoding="utf-8")
            added = self.store.import_json(raw)
            self._refresh_all()
            InfoBar.success(
                title="已导入",
                content=f"新增 {added} 条记录",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
        except Exception as e:
            InfoBar.error(
                title="导入失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )

    def _clear_all(self):
        if not self.store.entries:
            InfoBar.info(
                title="提示",
                content="日志已经为空",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return
        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="清空所有日志",
            content=f"将删除全部 {len(self.store.entries)} 条记录,此操作不可撤销。继续吗?",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return
        self.store.clear_all()
        self._active_tags.clear()
        self._search_keyword = ""
        self.current_bucket = "today"
        self.current_date = None
        self._refresh_all()