#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todo 三栏式 UI — 仿 Microsoft To Do，使用 qfluentwidgets 主题化组件。

布局:
  ┌─────────┬───────────────────┬───────────┐
  │ 列表栏   │ 任务列表           │ 任务详情   │
  │ (固定宽) │ (主区域)           │ (按需显示)│
  └─────────┴───────────────────┴───────────┘
"""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QDate, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAction,
    QFrame,
    QHBoxLayout,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CalendarPicker,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ElevatedCardWidget,
    FluentIcon as FIF,
    IconWidget,
    InfoBadge,
    InfoBar,
    InfoBarPosition,
    LargeTitleLabel,
    LineEdit,
    ListWidget,
    MessageBoxBase,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SimpleCardWidget,
    StrongBodyLabel,
    SubtitleLabel,
    SmoothScrollArea,
    TextEdit,
    TitleLabel,
    TransparentToolButton,
    TransparentTogglePushButton,
    TransparentToggleToolButton,
    isDarkTheme,
    themeColor,
)

try:
    from .storage import SYSTEM_LISTS, TodoStore
except ImportError:
    from storage import SYSTEM_LISTS, TodoStore


# 系统视图 → 图标
SYSTEM_LIST_ICONS = {
    "my_day": FIF.BRIGHTNESS,
    "important": FIF.PIN,
    "planned": FIF.CALENDAR,
    "tasks": FIF.HOME,
}


def _format_due(due_iso: Optional[str]) -> str:
    if not due_iso:
        return ""
    try:
        d = date.fromisoformat(due_iso)
    except ValueError:
        return due_iso
    today = date.today()
    delta = (d - today).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    if delta == -1:
        return "昨天"
    if 1 < delta <= 7:
        return f"{delta} 天后"
    if delta < -1:
        return f"逾期 {-delta} 天"
    return d.strftime("%Y-%m-%d")


def _muted_color() -> str:
    return "#9DA3A8" if isDarkTheme() else "#666"


def _subtle_color() -> str:
    return "#6E7378" if isDarkTheme() else "#888"


# ── 列表名输入对话框 ───────────────────────────────────────

class ListNameDialog(MessageBoxBase):
    """新建 / 重命名列表的输入对话框（参考官方 CustomMessageBox 样式）。"""

    def __init__(
        self,
        parent=None,
        title: str = "新建列表",
        placeholder: str = "输入列表名称…",
        initial: str = "",
        existing_names: Optional[List[str]] = None,
    ):
        super().__init__(parent)
        self._existing = {n for n in (existing_names or [])}
        # 允许保留原名（用于重命名场景）
        self._self_name = initial

        self.titleLabel = SubtitleLabel(title, self)

        self.nameLineEdit = LineEdit(self)
        self.nameLineEdit.setPlaceholderText(placeholder)
        self.nameLineEdit.setClearButtonEnabled(True)
        if initial:
            self.nameLineEdit.setText(initial)
            self.nameLineEdit.selectAll()

        self.warningLabel = CaptionLabel("名称不能为空", self)
        self.warningLabel.setTextColor("#cf1010", QColor(255, 28, 32))
        self.warningLabel.hide()

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.nameLineEdit)
        self.viewLayout.addWidget(self.warningLabel)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(360)

        self.nameLineEdit.textChanged.connect(self._on_text_changed)
        self.nameLineEdit.returnPressed.connect(self.yesButton.click)

    def _on_text_changed(self, _text: str):
        # 输入时清掉错误提示，等下一次 validate 再判
        if not self.warningLabel.isHidden():
            self.warningLabel.hide()

    def validate(self) -> bool:
        name = self.nameLineEdit.text().strip()
        if not name:
            self.warningLabel.setText("名称不能为空")
            self.warningLabel.show()
            return False
        if name != self._self_name and name in self._existing:
            self.warningLabel.setText(f"已存在同名列表「{name}」")
            self.warningLabel.show()
            return False
        self.warningLabel.hide()
        return True

    def value(self) -> str:
        return self.nameLineEdit.text().strip()


# ── 列表栏 ────────────────────────────────────────────────

class ListsPane(QWidget):
    """左侧列表栏：系统视图 + 用户列表 + 新建按钮（使用 qfluentwidgets ListWidget）。"""

    listSelected = pyqtSignal(str)
    addListRequested = pyqtSignal()
    renameListRequested = pyqtSignal(str)
    removeListRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setObjectName("TodoListsPane")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        # 头部
        header = QHBoxLayout()
        header.setContentsMargins(6, 0, 6, 0)
        title = SubtitleLabel("任务", self)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        # 列表（使用 fluent 化的 ListWidget）
        self.list_widget = ListWidget(self)
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setIconSize(self.list_widget.iconSize())  # touch property
        self.list_widget.setSpacing(2)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.list_widget, 1)

        # 新建列表
        add_btn = PushButton("新建列表", self, FIF.ADD)
        add_btn.clicked.connect(self.addListRequested.emit)
        layout.addWidget(add_btn)

    def populate(
        self,
        lists: List[Dict[str, Any]],
        counts: Dict[str, int],
        current_id: Optional[str],
    ):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        sys_count = 0
        sample_size = None
        has_user_lists = any(not l.get("system") for l in lists)
        user_header_inserted = False

        for lst in lists:
            if lst.get("system"):
                sys_count += 1
                icon = SYSTEM_LIST_ICONS.get(lst.get("kind"), FIF.APPLICATION)
            else:
                # 在第一个用户列表之前插入「我的列表」小标题
                if not user_header_inserted and has_user_lists:
                    header_item = QListWidgetItem("我的列表")
                    header_item.setFlags(Qt.NoItemFlags)  # 不可选、不可点
                    header_item.setForeground(
                        self.palette().color(self.palette().Disabled,
                                             self.palette().WindowText)
                    )
                    f = header_item.font()
                    f.setBold(True)
                    f.setPointSize(max(8, f.pointSize() - 1))
                    header_item.setFont(f)
                    # 高一点的间距感
                    if sample_size is not None:
                        header_item.setSizeHint(sample_size)
                    self.list_widget.addItem(header_item)
                    user_header_inserted = True
                icon = FIF.LABEL

            count = counts.get(lst["id"], 0)
            label = lst["name"] if count == 0 else f"{lst['name']}  ·  {count}"
            item = QListWidgetItem(icon.icon(), label)
            item.setData(Qt.UserRole, lst["id"])
            self.list_widget.addItem(item)
            if sample_size is None:
                sample_size = item.sizeHint()

        self.list_widget.blockSignals(False)

        # 选中当前
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.UserRole) == current_id:
                self.list_widget.setCurrentItem(it)
                break

    def _on_current_changed(self, cur, _prev):
        if cur and cur.data(Qt.UserRole):
            self.listSelected.emit(cur.data(Qt.UserRole))

    def _on_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        list_id = item.data(Qt.UserRole)
        if not list_id or list_id.startswith("sys:"):
            return
        menu = RoundMenu("", self)
        act_rename = QAction(FIF.EDIT.icon(), "重命名", self)
        act_rename.triggered.connect(lambda: self.renameListRequested.emit(list_id))
        menu.addAction(act_rename)
        act_remove = QAction(FIF.DELETE.icon(), "删除列表", self)
        act_remove.triggered.connect(lambda: self.removeListRequested.emit(list_id))
        menu.addAction(act_remove)
        menu.exec_(self.list_widget.viewport().mapToGlobal(pos))


# ── 任务行 ────────────────────────────────────────────────

class TaskRow(CardWidget):
    """单条任务卡片：复选框 · 标题/元信息 · 重要标记。"""

    toggled = pyqtSignal(str, bool)
    starred = pyqtSignal(str, bool)
    selected = pyqtSignal(str)

    def __init__(self, task: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.task = task
        self.setMinimumHeight(64)
        self.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(12)

        # 复选框
        self.check = CheckBox(self)
        self.check.setChecked(bool(task.get("completed")))
        self.check.stateChanged.connect(self._on_check)
        layout.addWidget(self.check, 0, Qt.AlignVCenter)

        # 文本块
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)

        self.title_label = BodyLabel(task["title"], self)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        text_box.addWidget(self.title_label)

        meta_layout = QHBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(8)
        self._meta_widgets: List[QWidget] = []
        self._build_meta(meta_layout)
        meta_layout.addStretch(1)
        text_box.addLayout(meta_layout)

        layout.addLayout(text_box, 1)

        # 重要标记（toggle，使用 ToolButton 变体避免按钮文字区域占位）
        self.star_btn = TransparentToggleToolButton(FIF.PIN, self)
        self.star_btn.setFixedSize(36, 36)
        self.star_btn.setToolTip("标记为重要")
        self.star_btn.setChecked(bool(task.get("important")))
        self.star_btn.toggled.connect(self._on_star)
        layout.addWidget(self.star_btn, 0, Qt.AlignVCenter)

        self._apply_completion_style()

    def _make_chip(self, icon: FIF, text: str) -> QWidget:
        """构造一个「图标 + 文字」的小标签。"""
        chip = QWidget(self)
        h = QHBoxLayout(chip)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        ic = IconWidget(icon, chip)
        ic.setFixedSize(12, 12)
        h.addWidget(ic)
        lbl = CaptionLabel(text, chip)
        lbl.setStyleSheet(f"color: {_subtle_color()};")
        h.addWidget(lbl)
        return chip

    def _build_meta(self, parent_layout: QHBoxLayout):
        task = self.task
        if task.get("my_day_date") == date.today().isoformat():
            chip = self._make_chip(FIF.BRIGHTNESS, "我的一天")
            parent_layout.addWidget(chip)
            self._meta_widgets.append(chip)

        due = _format_due(task.get("due_date"))
        if due:
            chip = self._make_chip(FIF.CALENDAR, due)
            parent_layout.addWidget(chip)
            self._meta_widgets.append(chip)

        steps = task.get("steps") or []
        if steps:
            done = sum(1 for s in steps if s.get("completed"))
            chip = self._make_chip(FIF.CHECKBOX, f"步骤 {done}/{len(steps)}")
            parent_layout.addWidget(chip)
            self._meta_widgets.append(chip)

        if task.get("notes"):
            chip = self._make_chip(FIF.QUICK_NOTE, "备注")
            parent_layout.addWidget(chip)
            self._meta_widgets.append(chip)

    def _apply_completion_style(self):
        font: QFont = self.title_label.font()
        font.setStrikeOut(bool(self.task.get("completed")))
        self.title_label.setFont(font)
        if self.task.get("completed"):
            self.title_label.setStyleSheet(f"color: {_muted_color()};")
        else:
            self.title_label.setStyleSheet("")

    def _on_check(self, _state):
        completed = self.check.isChecked()
        self.task["completed"] = completed
        self._apply_completion_style()
        self.toggled.emit(self.task["id"], completed)

    def _on_star(self, checked: bool):
        self.task["important"] = checked
        self.starred.emit(self.task["id"], checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            # 点击非控件区域 → 选中
            if child not in (self.check, self.star_btn):
                # 判断是否点在内部子控件之外
                if not (self.check.geometry().contains(event.pos())
                        or self.star_btn.geometry().contains(event.pos())):
                    self.selected.emit(self.task["id"])
        super().mousePressEvent(event)


# ── 任务列表面板 ───────────────────────────────────────────

class TasksPane(QWidget):
    addTaskRequested = pyqtSignal(str)
    taskToggled = pyqtSignal(str, bool)
    taskStarred = pyqtSignal(str, bool)
    taskSelected = pyqtSignal(str)
    searchChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        # 标题区
        head_row = QHBoxLayout()
        head_row.setSpacing(10)

        self.head_icon = IconWidget(FIF.BRIGHTNESS, self)
        self.head_icon.setFixedSize(28, 28)
        head_row.addWidget(self.head_icon, 0, Qt.AlignVCenter)

        head_text = QVBoxLayout()
        head_text.setContentsMargins(0, 0, 0, 0)
        head_text.setSpacing(0)
        self.title = LargeTitleLabel("我的一天", self)
        self.subtitle = CaptionLabel("", self)
        self.subtitle.setStyleSheet(f"color: {_subtle_color()};")
        head_text.addWidget(self.title)
        head_text.addWidget(self.subtitle)
        head_row.addLayout(head_text, 1)

        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText("搜索任务…")
        self.search.setFixedWidth(240)
        self.search.searchSignal.connect(self.searchChanged.emit)
        self.search.clearSignal.connect(lambda: self.searchChanged.emit(""))
        self.search.returnPressed.connect(
            lambda: self.search.search() if self.search.text().strip()
            else self.search.clearSignal.emit()
        )
        head_row.addWidget(self.search, 0, Qt.AlignVCenter)
        layout.addLayout(head_row)

        # 任务滚动区
        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        self.scroll_inner = QWidget()
        self.scroll_inner.setStyleSheet("background: transparent;")
        self.rows_layout = QVBoxLayout(self.scroll_inner)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(8)

        # 空状态
        self.empty_widget = self._build_empty()
        self.rows_layout.addWidget(self.empty_widget)
        self.rows_layout.addStretch(1)

        self.scroll.setWidget(self.scroll_inner)
        layout.addWidget(self.scroll, 1)

        # 快速添加（简洁卡片）
        add_card = SimpleCardWidget(self)
        add_layout = QHBoxLayout(add_card)
        add_layout.setContentsMargins(14, 8, 8, 8)
        add_layout.setSpacing(10)

        add_icon = IconWidget(FIF.ADD, self)
        add_icon.setFixedSize(16, 16)
        add_layout.addWidget(add_icon)

        self.add_edit = LineEdit(self)
        self.add_edit.setPlaceholderText("添加任务（回车提交）")
        self.add_edit.setClearButtonEnabled(True)
        self.add_edit.setStyleSheet(
            "LineEdit { border: 0; background: transparent; }"
        )
        self.add_edit.returnPressed.connect(self._on_add)
        add_layout.addWidget(self.add_edit, 1)

        layout.addWidget(add_card)

    def _build_empty(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 80, 0, 60)
        v.setSpacing(10)
        ic = IconWidget(FIF.COMPLETED, w)
        ic.setFixedSize(48, 48)
        v.addWidget(ic, 0, Qt.AlignCenter)
        msg = SubtitleLabel("还没有任务", w)
        msg.setAlignment(Qt.AlignCenter)
        v.addWidget(msg)
        sub = BodyLabel("从下方输入框开始添加，或试试拖拽到「我的一天」", w)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color: {_subtle_color()};")
        v.addWidget(sub)
        return w

    def set_header(self, name: str, kind: Optional[str], done: int, total: int):
        icon = SYSTEM_LIST_ICONS.get(kind, FIF.LABEL)
        self.head_icon.setIcon(icon)
        self.title.setText(name)
        if total == 0:
            self.subtitle.setText("还没有任务")
        elif done == 0:
            self.subtitle.setText(f"{total} 项")
        else:
            self.subtitle.setText(f"已完成 {done} / {total}")

    def show_tasks(self, tasks: List[Dict[str, Any]]):
        # 移除旧任务行（保留 empty + stretch）
        for i in reversed(range(self.rows_layout.count())):
            item = self.rows_layout.itemAt(i)
            w = item.widget()
            if isinstance(w, TaskRow):
                self.rows_layout.takeAt(i)
                w.deleteLater()

        # 排序
        def sort_key(t):
            return (
                bool(t.get("completed")),
                not bool(t.get("important")),
                t.get("due_date") or "9999",
                t.get("created_at") or "",
            )

        tasks_sorted = sorted(tasks, key=sort_key)

        if not tasks_sorted:
            self.empty_widget.show()
        else:
            self.empty_widget.hide()
            for t in tasks_sorted:
                row = TaskRow(t, self)
                row.toggled.connect(self.taskToggled.emit)
                row.starred.connect(self.taskStarred.emit)
                row.selected.connect(self.taskSelected.emit)
                # 插在最后的 stretch 之前
                self.rows_layout.insertWidget(
                    self.rows_layout.count() - 1, row
                )

    def _on_add(self):
        text = self.add_edit.text().strip()
        if not text:
            return
        self.add_edit.clear()
        self.addTaskRequested.emit(text)


# ── 步骤行 ────────────────────────────────────────────────

class StepRow(QWidget):
    toggled = pyqtSignal(str, bool)
    titleChanged = pyqtSignal(str, str)
    removeRequested = pyqtSignal(str)

    def __init__(self, step: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.step = step
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        self.check = CheckBox(self)
        self.check.setChecked(bool(step.get("completed")))
        self.check.stateChanged.connect(self._on_check)
        layout.addWidget(self.check)

        self.edit = LineEdit(self)
        self.edit.setText(step["title"])
        self.edit.setStyleSheet(
            "LineEdit { border: 0; background: transparent; }"
        )
        self.edit.editingFinished.connect(self._on_edit)
        layout.addWidget(self.edit, 1)

        self.del_btn = TransparentToolButton(FIF.CLOSE, self)
        self.del_btn.setToolTip("删除步骤")
        self.del_btn.clicked.connect(lambda: self.removeRequested.emit(step["id"]))
        layout.addWidget(self.del_btn)

        self._apply_style()

    def _apply_style(self):
        font = self.edit.font()
        font.setStrikeOut(bool(self.step.get("completed")))
        self.edit.setFont(font)

    def _on_check(self, _state):
        done = self.check.isChecked()
        self.step["completed"] = done
        self._apply_style()
        self.toggled.emit(self.step["id"], done)

    def _on_edit(self):
        new = self.edit.text().strip()
        if new and new != self.step["title"]:
            self.step["title"] = new
            self.titleChanged.emit(self.step["id"], new)


# ── 任务详情面板 ───────────────────────────────────────────

class DetailPane(QWidget):
    titleChanged = pyqtSignal(str, str)
    completedChanged = pyqtSignal(str, bool)
    importantChanged = pyqtSignal(str, bool)
    myDayChanged = pyqtSignal(str, bool)
    dueDateChanged = pyqtSignal(str, object)
    notesChanged = pyqtSignal(str, str)
    deleteRequested = pyqtSignal(str)
    closeRequested = pyqtSignal()

    addStepRequested = pyqtSignal(str, str)
    updateStepRequested = pyqtSignal(str, str, dict)
    removeStepRequested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(360)
        self.setObjectName("TodoDetailPane")
        self.task: Optional[Dict[str, Any]] = None

        # 整体放在滚动区里以适应小屏
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = SmoothScrollArea(self)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 顶部：关闭
        head = QHBoxLayout()
        self.head_label = StrongBodyLabel("任务详情", self)
        head.addWidget(self.head_label)
        head.addStretch(1)
        close_btn = TransparentToolButton(FIF.CLOSE, self)
        close_btn.setToolTip("关闭详情")
        close_btn.clicked.connect(self.closeRequested.emit)
        head.addWidget(close_btn)
        layout.addLayout(head)

        # 标题卡：完成 / 标题 / 重要
        title_card = SimpleCardWidget(self)
        tc_layout = QHBoxLayout(title_card)
        tc_layout.setContentsMargins(12, 10, 8, 10)
        tc_layout.setSpacing(10)

        self.check = CheckBox(self)
        self.check.stateChanged.connect(self._on_check)
        tc_layout.addWidget(self.check)

        self.title_edit = LineEdit(self)
        self.title_edit.setStyleSheet(
            "LineEdit { border: 0; background: transparent; }"
        )
        self.title_edit.editingFinished.connect(self._on_title)
        tc_layout.addWidget(self.title_edit, 1)

        self.star_btn = TransparentToggleToolButton(FIF.PIN, self)
        self.star_btn.setFixedSize(36, 36)
        self.star_btn.setToolTip("标记为重要")
        self.star_btn.toggled.connect(self._on_star)
        tc_layout.addWidget(self.star_btn)

        layout.addWidget(title_card)

        # 我的一天（toggle 按钮）
        self.my_day_btn = TransparentTogglePushButton(FIF.BRIGHTNESS, "添加到「我的一天」", self)
        self.my_day_btn.setMinimumHeight(36)
        self.my_day_btn.toggled.connect(self._on_my_day)
        layout.addWidget(self.my_day_btn)

        # 截止日期：CalendarPicker + 清除
        due_card = SimpleCardWidget(self)
        due_layout = QHBoxLayout(due_card)
        due_layout.setContentsMargins(12, 8, 8, 8)
        due_layout.setSpacing(10)
        due_icon = IconWidget(FIF.CALENDAR, self)
        due_icon.setFixedSize(16, 16)
        due_layout.addWidget(due_icon)
        due_label = BodyLabel("截止日期", self)
        due_layout.addWidget(due_label)
        due_layout.addStretch(1)
        self.due_picker = CalendarPicker(self)
        self.due_picker.dateChanged.connect(self._on_due_changed)
        due_layout.addWidget(self.due_picker)
        self.due_clear = TransparentToolButton(FIF.CLOSE, self)
        self.due_clear.setToolTip("清除截止日期")
        self.due_clear.clicked.connect(self._on_due_clear)
        due_layout.addWidget(self.due_clear)
        layout.addWidget(due_card)

        # 步骤
        steps_header = QHBoxLayout()
        steps_header.addWidget(StrongBodyLabel("步骤", self))
        steps_header.addStretch(1)
        layout.addLayout(steps_header)

        self.steps_card = SimpleCardWidget(self)
        steps_layout = QVBoxLayout(self.steps_card)
        steps_layout.setContentsMargins(8, 6, 8, 6)
        steps_layout.setSpacing(2)
        self.steps_box = steps_layout

        # 添加步骤行
        self.add_step_row = QWidget(self)
        ass_l = QHBoxLayout(self.add_step_row)
        ass_l.setContentsMargins(0, 2, 0, 2)
        ass_l.setSpacing(8)
        plus_icon = IconWidget(FIF.ADD, self)
        plus_icon.setFixedSize(14, 14)
        ass_l.addWidget(plus_icon)
        self.add_step_edit = LineEdit(self)
        self.add_step_edit.setPlaceholderText("添加步骤")
        self.add_step_edit.setStyleSheet(
            "LineEdit { border: 0; background: transparent; }"
        )
        self.add_step_edit.returnPressed.connect(self._on_add_step)
        ass_l.addWidget(self.add_step_edit, 1)
        steps_layout.addWidget(self.add_step_row)

        layout.addWidget(self.steps_card)

        # 备注
        layout.addWidget(StrongBodyLabel("备注", self))
        self.notes_edit = TextEdit(self)
        self.notes_edit.setPlaceholderText("添加备注…")
        self.notes_edit.setFixedHeight(120)
        self.notes_edit.focusOutEvent = self._wrap_focus_out(self.notes_edit.focusOutEvent)
        layout.addWidget(self.notes_edit)

        layout.addStretch(1)

        # 底部
        foot = QHBoxLayout()
        self.foot_label = CaptionLabel("", self)
        self.foot_label.setStyleSheet(f"color: {_subtle_color()};")
        foot.addWidget(self.foot_label)
        foot.addStretch(1)
        self.delete_btn = TransparentToolButton(FIF.DELETE, self)
        self.delete_btn.setToolTip("删除任务")
        self.delete_btn.clicked.connect(self._on_delete)
        foot.addWidget(self.delete_btn)
        layout.addLayout(foot)

        scroll.setWidget(body)
        outer.addWidget(scroll)

        # 背景轻微区分
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"QWidget#TodoDetailPane {{ "
            f"background: {'#1e1e1e' if isDarkTheme() else '#f8f8f8'}; "
            f"border-left: 1px solid {'#2c2c2c' if isDarkTheme() else '#e5e5e5'}; "
            f"}}"
        )

    # ── 工具 ──

    def _wrap_focus_out(self, original):
        def handler(event):
            self._on_notes_committed()
            original(event)
        return handler

    def _clear_steps(self):
        # 把 add_step_row 之外的子项移除
        for i in reversed(range(self.steps_box.count())):
            item = self.steps_box.itemAt(i)
            w = item.widget()
            if w is None:
                continue
            if w is self.add_step_row:
                continue
            self.steps_box.takeAt(i)
            w.deleteLater()

    # ── 公共 ──

    def show_task(self, task: Optional[Dict[str, Any]]):
        self.task = task
        if task is None:
            self.hide()
            return

        # 阻塞信号
        for w in (self.check, self.title_edit, self.notes_edit,
                  self.star_btn, self.my_day_btn, self.due_picker):
            w.blockSignals(True)

        self.title_edit.setText(task["title"])
        self.check.setChecked(bool(task.get("completed")))
        self.star_btn.setChecked(bool(task.get("important")))

        today = date.today().isoformat()
        in_my_day = task.get("my_day_date") == today
        self.my_day_btn.setChecked(in_my_day)
        self.my_day_btn.setText(
            "已添加到「我的一天」" if in_my_day else "添加到「我的一天」"
        )

        if task.get("due_date"):
            try:
                self.due_picker.setDate(QDate.fromString(task["due_date"], "yyyy-MM-dd"))
            except Exception:
                pass
        else:
            # 重置 picker（CalendarPicker 没有公开的 reset，新建 QDate(1900,1,1) 触发重绘）
            self.due_picker.setDate(QDate())

        self.notes_edit.setPlainText(task.get("notes") or "")

        # 步骤
        self._clear_steps()
        steps = task.get("steps") or []
        # 把 add_step_row 暂时移除，重新插入到末尾以保持顺序
        self.steps_box.removeWidget(self.add_step_row)
        for step in steps:
            row = StepRow(step, self)
            row.toggled.connect(
                lambda sid, done, t=task: self.updateStepRequested.emit(
                    t["id"], sid, {"completed": done}
                )
            )
            row.titleChanged.connect(
                lambda sid, ttl, t=task: self.updateStepRequested.emit(
                    t["id"], sid, {"title": ttl}
                )
            )
            row.removeRequested.connect(
                lambda sid, t=task: self.removeStepRequested.emit(t["id"], sid)
            )
            self.steps_box.addWidget(row)
        self.steps_box.addWidget(self.add_step_row)

        # 创建/完成时间
        created = task.get("created_at", "")
        if task.get("completed_at"):
            self.foot_label.setText(
                f"创建于 {created} · 已完成 {task['completed_at']}"
            )
        else:
            self.foot_label.setText(f"创建于 {created}")

        for w in (self.check, self.title_edit, self.notes_edit,
                  self.star_btn, self.my_day_btn, self.due_picker):
            w.blockSignals(False)

        self.show()

    # ── 事件 ──

    def _on_check(self, _state):
        if not self.task:
            return
        done = self.check.isChecked()
        self.task["completed"] = done
        self.completedChanged.emit(self.task["id"], done)

    def _on_title(self):
        if not self.task:
            return
        new = self.title_edit.text().strip()
        if new and new != self.task["title"]:
            self.task["title"] = new
            self.titleChanged.emit(self.task["id"], new)

    def _on_star(self, checked: bool):
        if not self.task:
            return
        self.task["important"] = checked
        self.importantChanged.emit(self.task["id"], checked)

    def _on_my_day(self, checked: bool):
        if not self.task:
            return
        today = date.today().isoformat()
        self.task["my_day_date"] = today if checked else None
        self.my_day_btn.setText(
            "已添加到「我的一天」" if checked else "添加到「我的一天」"
        )
        self.myDayChanged.emit(self.task["id"], checked)

    def _on_due_changed(self, qdate: QDate):
        if not self.task:
            return
        if not qdate.isValid():
            return
        iso = qdate.toString("yyyy-MM-dd")
        if self.task.get("due_date") != iso:
            self.task["due_date"] = iso
            self.dueDateChanged.emit(self.task["id"], iso)

    def _on_due_clear(self):
        if not self.task:
            return
        self.task["due_date"] = None
        self.due_picker.blockSignals(True)
        self.due_picker.setDate(QDate())
        self.due_picker.blockSignals(False)
        self.dueDateChanged.emit(self.task["id"], None)

    def _on_notes_committed(self):
        if not self.task:
            return
        new = self.notes_edit.toPlainText()
        if new != (self.task.get("notes") or ""):
            self.task["notes"] = new
            self.notesChanged.emit(self.task["id"], new)

    def _on_add_step(self):
        if not self.task:
            return
        text = self.add_step_edit.text().strip()
        if not text:
            return
        self.add_step_edit.clear()
        self.addStepRequested.emit(self.task["id"], text)

    def _on_delete(self):
        if not self.task:
            return
        self.deleteRequested.emit(self.task["id"])


# ── 主页面 ────────────────────────────────────────────────

class TodoPage(QWidget):
    """三栏布局根。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TodoPage")

        # 数据
        data_dir = Path.home() / ".application_framework" / "todo"
        self.store = TodoStore(data_dir / "data.json")

        self.current_list_id = "sys:my_day"
        self.current_task_id: Optional[str] = None
        self._search_keyword = ""

        # 三栏
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.lists_pane = ListsPane(self)
        # 给左栏一点底色
        self.lists_pane.setAutoFillBackground(True)
        self.lists_pane.setStyleSheet(
            f"QWidget#TodoListsPane {{ "
            f"background: {'#1a1a1a' if isDarkTheme() else '#f3f3f3'}; "
            f"border-right: 1px solid "
            f"{'#2c2c2c' if isDarkTheme() else '#e5e5e5'}; "
            f"}}"
        )
        root.addWidget(self.lists_pane)

        self.tasks_pane = TasksPane(self)
        root.addWidget(self.tasks_pane, 1)

        self.detail_pane = DetailPane(self)
        self.detail_pane.hide()
        root.addWidget(self.detail_pane)

        self._wire()
        self._refresh_lists()
        self._refresh_tasks()

    # ── 信号 ──

    def _wire(self):
        L = self.lists_pane
        L.listSelected.connect(self._on_list_selected)
        L.addListRequested.connect(self._on_add_list)
        L.renameListRequested.connect(self._on_rename_list)
        L.removeListRequested.connect(self._on_remove_list)

        T = self.tasks_pane
        T.addTaskRequested.connect(self._on_add_task)
        T.taskToggled.connect(self._on_task_toggled)
        T.taskStarred.connect(self._on_task_starred)
        T.taskSelected.connect(self._on_task_selected)
        T.searchChanged.connect(self._on_search_changed)

        D = self.detail_pane
        D.titleChanged.connect(lambda tid, v: self._update_task(tid, title=v))
        D.completedChanged.connect(lambda tid, v: self._update_task(tid, completed=v))
        D.importantChanged.connect(lambda tid, v: self._update_task(tid, important=v))
        D.dueDateChanged.connect(lambda tid, v: self._update_task(tid, due_date=v))
        D.notesChanged.connect(lambda tid, v: self._update_task(tid, notes=v))
        D.myDayChanged.connect(self._on_my_day_changed)
        D.deleteRequested.connect(self._on_delete_task)
        D.closeRequested.connect(self._on_detail_close)

        D.addStepRequested.connect(self._on_add_step)
        D.updateStepRequested.connect(self._on_update_step)
        D.removeStepRequested.connect(self._on_remove_step)

    # ── 列表 ──

    def _list_counts(self) -> Dict[str, int]:
        """每个列表的「未完成」任务数。"""
        counts: Dict[str, int] = {}
        for lst in self.store.all_lists():
            tasks = self.store.tasks_for_list(lst["id"])
            counts[lst["id"]] = sum(1 for t in tasks if not t.get("completed"))
        return counts

    def _refresh_lists(self):
        self.lists_pane.populate(
            self.store.all_lists(), self._list_counts(), self.current_list_id
        )

    def _on_list_selected(self, list_id: str):
        if list_id == self.current_list_id:
            return
        self.current_list_id = list_id
        self.current_task_id = None
        self.detail_pane.hide()
        self._refresh_tasks()

    def _on_add_list(self):
        existing = [l["name"] for l in self.store.lists]
        dlg = ListNameDialog(
            parent=self.window(),
            title="新建列表",
            placeholder="输入列表名称…",
            existing_names=existing,
        )
        if dlg.exec():
            new = self.store.add_list(dlg.value())
            self.current_list_id = new["id"]
            self._refresh_lists()
            self._refresh_tasks()

    def _on_rename_list(self, list_id: str):
        cur = next((l for l in self.store.lists if l["id"] == list_id), None)
        if not cur:
            return
        existing = [l["name"] for l in self.store.lists if l["id"] != list_id]
        dlg = ListNameDialog(
            parent=self.window(),
            title="重命名列表",
            placeholder="输入新的列表名称…",
            initial=cur["name"],
            existing_names=existing,
        )
        if dlg.exec():
            new_name = dlg.value()
            if new_name and new_name != cur["name"]:
                self.store.rename_list(list_id, new_name)
                self._refresh_lists()

    def _on_remove_list(self, list_id: str):
        from customWidget import MessageConfirmBox

        cur = next((l for l in self.store.lists if l["id"] == list_id), None)
        if not cur:
            return
        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="删除列表",
            content=f"删除列表「{cur['name']}」？该列表下的任务将移至「任务」。",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return
        self.store.remove_list(list_id)
        if self.current_list_id == list_id:
            self.current_list_id = "sys:tasks"
        self._refresh_lists()
        self._refresh_tasks()

    # ── 任务 ──

    def _filtered_tasks(self) -> List[Dict[str, Any]]:
        tasks = self.store.tasks_for_list(self.current_list_id)
        if self._search_keyword:
            kw = self._search_keyword.lower()
            tasks = [
                t for t in tasks
                if kw in t["title"].lower()
                or kw in (t.get("notes") or "").lower()
            ]
        return tasks

    def _refresh_tasks(self):
        cur_list = self.store.get_list(self.current_list_id) or {"name": "任务"}
        tasks = self._filtered_tasks()
        done = sum(1 for t in tasks if t.get("completed"))
        kind = cur_list.get("kind") if cur_list.get("system") else None
        self.tasks_pane.set_header(cur_list["name"], kind, done, len(tasks))
        self.tasks_pane.show_tasks(tasks)
        # 列表角标也要更新
        self._refresh_lists()

    def _on_add_task(self, title: str):
        task = self.store.add_task(title, self.current_list_id)
        self._refresh_tasks()
        InfoBar.success(
            title="已添加",
            content=task["title"],
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=1500,
        )

    def _update_task(self, task_id: str, **changes):
        self.store.update_task(task_id, **changes)
        self._refresh_tasks()
        if self.current_task_id == task_id:
            self.detail_pane.show_task(self.store.get_task(task_id))

    def _on_task_toggled(self, task_id: str, done: bool):
        self.store.update_task(task_id, completed=done)
        self._refresh_tasks()
        if self.current_task_id == task_id:
            self.detail_pane.show_task(self.store.get_task(task_id))

    def _on_task_starred(self, task_id: str, important: bool):
        self.store.update_task(task_id, important=important)
        self._refresh_tasks()
        if self.current_task_id == task_id:
            self.detail_pane.show_task(self.store.get_task(task_id))

    def _on_task_selected(self, task_id: str):
        self.current_task_id = task_id
        self.detail_pane.show_task(self.store.get_task(task_id))

    def _on_my_day_changed(self, task_id: str, in_my_day: bool):
        today = date.today().isoformat()
        self.store.update_task(task_id, my_day_date=today if in_my_day else None)
        self._refresh_tasks()

    def _on_delete_task(self, task_id: str):
        from customWidget import MessageConfirmBox

        task = self.store.get_task(task_id)
        if not task:
            return
        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="删除任务",
            content=f"确定删除任务「{task['title']}」？",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return
        self.store.remove_task(task_id)
        self.current_task_id = None
        self.detail_pane.hide()
        self._refresh_tasks()

    def _on_detail_close(self):
        self.current_task_id = None
        self.detail_pane.hide()

    def _on_search_changed(self, keyword: str):
        self._search_keyword = keyword.strip()
        self._refresh_tasks()

    # ── 步骤 ──

    def _on_add_step(self, task_id: str, title: str):
        self.store.add_step(task_id, title)
        if self.current_task_id == task_id:
            self.detail_pane.show_task(self.store.get_task(task_id))
        self._refresh_tasks()

    def _on_update_step(self, task_id: str, step_id: str, changes: dict):
        self.store.update_step(task_id, step_id, **changes)
        self._refresh_tasks()

    def _on_remove_step(self, task_id: str, step_id: str):
        self.store.remove_step(task_id, step_id)
        if self.current_task_id == task_id:
            self.detail_pane.show_task(self.store.get_task(task_id))
        self._refresh_tasks()