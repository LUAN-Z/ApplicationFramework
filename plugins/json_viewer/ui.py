#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON 文件查看器 UI — 树形浏览、搜索、类型着色、拖拽加载。"""

import json
import os
import re
from typing import Any

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PushButton,
    PrimaryPushButton,
    PrimarySplitPushButton,
    SplitPushButton,
    SearchLineEdit,
    StrongBodyLabel,
    TreeWidget,
    RoundMenu,
    isDarkTheme,
    qconfig,
)

# ── 类型着色 ──────────────────────────────────────────────
# 这些十六进制色在浅色 / 深色主题下都有足够对比度
COLOR_STRING = QColor("#4CAF50")
COLOR_NUMBER = QColor("#42A5F5")
COLOR_BOOL = QColor("#FFA726")
COLOR_NULL = QColor("#9E9E9E")
COLOR_EDITED = QColor("#FF5722")


def _default_color() -> QColor:
    """未知类型的回退颜色,跟随主题 — 浅色用深灰,深色用近白。"""
    return QColor("#E6E6E6") if isDarkTheme() else QColor("#202020")


def _value_color(value: Any) -> QColor:
    if value is None:
        return COLOR_NULL
    if isinstance(value, bool):
        return COLOR_BOOL
    if isinstance(value, (int, float)):
        return COLOR_NUMBER
    if isinstance(value, str):
        return COLOR_STRING
    return _default_color()


def _value_label(value: Any, max_len: int = 100) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        text = value.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        if len(text) > max_len:
            return f"{text[:max_len]}…"
        return text
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def _count_nodes(data: Any) -> int:
    """递归统计 JSON 树中的节点总数。"""
    count = 1
    if isinstance(data, dict):
        for v in data.values():
            count += _count_nodes(v)
    elif isinstance(data, list):
        for v in data:
            count += _count_nodes(v)
    return count


def _max_depth(data: Any, depth: int = 0) -> int:
    """递归计算 JSON 树的最大深度。"""
    if not isinstance(data, (dict, list)):
        return depth
    values = data.values() if isinstance(data, dict) else data
    child_depths = [_max_depth(v, depth + 1) for v in values]
    return max(child_depths) if child_depths else depth + 1


def _format_file_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _is_url(text: str) -> bool:
    """判断字符串是否为有效的 http/https URL。"""
    return bool(re.match(r"^https?://", text))


def _is_json_string(text: str) -> bool:
    """判断字符串是否可解析为 JSON（对象或数组）。"""
    stripped = text.strip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return False
    try:
        json.loads(stripped)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


# ── 树组件 ────────────────────────────────────────────────

class JsonTreeWidget(TreeWidget):
    """支持拖拽和右键菜单的 JSON 树。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setHeaderLabels(["键", "值", "类型"])
        self.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.header().setSectionResizeMode(1, QHeaderView.Interactive)
        self.header().setSectionResizeMode(2, QHeaderView.Interactive)
        # self.setColumnWidth(2, 50)
        self.setAlternatingRowColors(True)
        self.setAnimated(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        # Qt 默认的 AlternateBase 是接近白色的浅灰,深色主题下显得格外刺眼
        self._refresh_alt_palette()
        qconfig.themeChanged.connect(self._refresh_alt_palette)

    def _refresh_alt_palette(self):
        pal = self.palette()
        if isDarkTheme():
            pal.setColor(QPalette.AlternateBase, QColor(255, 255, 255, 12))
            pal.setColor(QPalette.Base, QColor(0, 0, 0, 0))
        else:
            pal.setColor(QPalette.AlternateBase, QColor(0, 0, 0, 10))
            pal.setColor(QPalette.Base, QColor(0, 0, 0, 0))
        self.setPalette(pal)
        # 视图本身也需要同步,viewport() 才是真正绘制行背景的部件
        if self.viewport() is not None:
            self.viewport().setPalette(pal)

    # 拖拽 ──

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".json"):
                # 向上冒泡到 page 层加载
                self._find_page().load_json_file(path)
                return
        event.ignore()

    def _find_page(self):
        p = self.parent()
        while p and not isinstance(p, JsonViewerPage):
            p = p.parent()
        return p

    # 右键菜单 ──

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return

        raw = item.data(0, Qt.UserRole)
        page = self._find_page()

        menu = RoundMenu("", self)

        act_copy_val = QAction("复制值", self)
        act_copy_val.triggered.connect(lambda: self._copy_value(item))
        menu.addAction(act_copy_val)

        act_copy_path = QAction("复制键路径", self)
        act_copy_path.triggered.connect(lambda: self._copy_path(item))
        menu.addAction(act_copy_path)

        # 如果被编辑过 → 还原
        if item.data(0, Qt.UserRole + 1) is not None:
            menu.addSeparator()
            act_restore = QAction("还原", self)
            act_restore.triggered.connect(
                lambda _checked, it=item: page._restore_value(it)
            )
            menu.addAction(act_restore)

        # 如果是 URL → 打开链接
        if isinstance(raw, str) and _is_url(raw):
            menu.addSeparator()
            act_open = QAction("打开链接", self)
            act_open.triggered.connect(lambda _checked, v=raw: page._open_url(v))
            menu.addAction(act_open)

        # 如果是可解析 JSON 字符串 → 解析
        if isinstance(raw, str) and _is_json_string(raw):
            menu.addSeparator()
            act_parse = QAction("解析为 JSON", self)
            act_parse.triggered.connect(lambda _checked, v=raw: page._parse_json_value(v))
            menu.addAction(act_parse)

        menu.exec_(self.viewport().mapToGlobal(pos))

    def _copy_value(self, item: QTreeWidgetItem):
        text = item.text(1) or item.text(0)
        QApplication.clipboard().setText(text)

    def _copy_path(self, item: QTreeWidgetItem):
        parts = []
        cur = item
        while cur:
            parts.append(cur.text(0))
            cur = cur.parent()
        QApplication.clipboard().setText(".".join(reversed(parts)))


# ── 主页面 ────────────────────────────────────────────────

class JsonViewerPage(QWidget):
    """JSON 文件查看器主页面。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("JsonViewerPage")
        self.current_file_path = ""
        self.json_data: Any = None
        self._init_ui()
        # 主题切换时重建树,刷新 setForeground 的缓存颜色
        qconfig.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        """主题变化时重建树,让 _value_color 的回退色重新计算。"""
        if self.json_data is not None:
            self._build_tree()

    # ── UI 构建 ──────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # ===== 文件选择区 =====
        file_card = CardWidget(self)
        fc_layout = QVBoxLayout(file_card)
        fc_layout.setContentsMargins(15, 15, 15, 15)

        fc_title = StrongBodyLabel("JSON 文件", self)
        fc_layout.addWidget(fc_title)

        path_row = QHBoxLayout()
        self.path_edit = LineEdit(self)
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setPlaceholderText("拖入 .json 文件到窗口，或点击浏览选择…")
        self.path_edit.setReadOnly(True)
        self.path_edit.clearButton.clicked.disconnect()
        self.path_edit.clearButton.clicked.connect(self._on_clear_requested)

        browse_btn = PrimaryPushButton("浏览", self)
        browse_btn.setIcon(FIF.FOLDER)
        browse_btn.clicked.connect(self.browse_file)

        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)
        
         # save button
        save_btn = SplitPushButton("保存", self)
        save_btn.setIcon(FIF.SAVE)
        save_btn.setFixedWidth(108)
        save_btn.clicked.connect(self._save_to_file)
        path_row.addWidget(save_btn)
        save_btn_action_menu = RoundMenu(title="另存为", parent=self)
        save_as_action = QAction(FIF.SAVE_AS.icon(), "另存为")
        save_btn_action_menu.addAction(save_as_action)
        save_as_action.triggered.connect(self._save_as)
        
        save_btn.setFlyout(save_btn_action_menu)
        
        fc_layout.addLayout(path_row)

        # 文件信息行
        info_row = QHBoxLayout()
        self.file_info = BodyLabel("", self)
        self.file_size = BodyLabel("", self)
        info_row.addWidget(self.file_info)
        info_row.addStretch(1)
        info_row.addWidget(self.file_size)
        fc_layout.addLayout(info_row)

        # # 保存按钮行
        # save_row = QHBoxLayout()
        # save_btn = PushButton("保存", self)
        # save_btn.setIcon(FIF.SAVE)
        # save_btn.clicked.connect(self._save_to_file)
        # save_as_btn = PushButton("另存为", self)
        # save_as_btn.setIcon(FIF.SAVE_AS)
        # save_as_btn.clicked.connect(self._save_as)
        # save_row.addStretch(1)
        # save_row.addWidget(save_btn)
        # save_row.addWidget(save_as_btn)
        # fc_layout.addLayout(save_row)

        layout.addWidget(file_card)

        # ===== 工具栏 =====
        tool_card = CardWidget(self)
        tool_row = QHBoxLayout(tool_card)
        tool_row.setContentsMargins(15, 10, 15, 10)

        expand_btn = PushButton("全部展开", self)
        expand_btn.setIcon(FIF.ZOOM_IN)
        expand_btn.clicked.connect(self.expand_all)

        collapse_btn = PushButton("全部折叠", self)
        collapse_btn.setIcon(FIF.ZOOM_OUT)
        collapse_btn.clicked.connect(self.collapse_all)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索节点…")
        self.search_edit.setMaximumWidth(300)
        self.search_edit.searchSignal.connect(self._on_search)
        self.search_edit.clearSignal.connect(lambda: self._on_search(""))
        self.search_edit.returnPressed.connect(
            lambda: self.search_edit.search() if self.search_edit.text().strip()
            else self.search_edit.clearSignal.emit()
        )

        tool_row.addWidget(expand_btn)
        tool_row.addWidget(collapse_btn)
        tool_row.addStretch(1)
        tool_row.addWidget(self.search_edit)

        layout.addWidget(tool_card)

        # ===== 树 =====
        self.tree = JsonTreeWidget(self)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        layout.addWidget(self.tree, 1)

        # ===== 状态栏 =====
        status_card = CardWidget(self)
        s_row = QHBoxLayout(status_card)
        s_row.setContentsMargins(15, 8, 15, 8)

        self.status_label = BodyLabel("就绪 — 请打开一个 JSON 文件", self)
        s_row.addWidget(self.status_label)
        s_row.addStretch(1)

        layout.addWidget(status_card)

    # ── 文件操作 ─────────────────────────────────────────

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 JSON 文件", "",
            "JSON 文件 (*.json);;所有文件 (*)",
        )
        if path:
            self.load_json_file(path)

    def load_json_file(self, file_path: str):
        """读取并解析 JSON 文件，构建树。"""
        if not os.path.exists(file_path):
            InfoBar.error(
                title="文件不存在",
                content=file_path,
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                self.json_data = json.loads(content)
        except json.JSONDecodeError as e:
            InfoBar.error(
                title="JSON 解析错误",
                content=f"行 {e.lineno} 列 {e.colno}: {e.msg}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            self.json_data = None
            return
        except Exception as e:
            InfoBar.error(
                title="读取失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            self.json_data = None
            return

        # 记录路径 & 显示
        self.current_file_path = file_path
        self.path_edit.setText(file_path)
        fsize = os.path.getsize(file_path)
        self.file_info.setText(f"文件: {os.path.basename(file_path)}")
        self.file_size.setText(_format_file_size(fsize))

        # 构建树
        self._build_tree()

        InfoBar.success(
            title="加载成功",
            content=os.path.basename(file_path),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=2000,
        )

    # ── 树构建 ───────────────────────────────────────────

    def _build_tree(self):
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        was_animated = self.tree.isAnimated()
        self.tree.setAnimated(False)
        try:
            self.tree.clear()
            if self.json_data is None:
                self.status_label.setText("无数据")
                return

            # 先以分离方式构建 root，待子节点全部就绪后一次性挂入并展开，
            # 避免 Qt 在每次插入时对已展开/已挂载的节点做布局与重绘。
            root = QTreeWidgetItem()
            root.setData(0, Qt.UserRole, self.json_data)
            root.setData(0, Qt.UserRole + 3, True)
            root.setText(0, "root")
            root.setText(2, type(self.json_data).__name__)
            font = root.font(0)
            font.setBold(True)
            root.setFont(0, font)

            self._populate_children(self.json_data, root)

            self.tree.addTopLevelItem(root)
            root.setExpanded(True)
            self.tree.setColumnWidth(2, 50)
        finally:
            self.tree.setAnimated(was_animated)
            self.tree.setUpdatesEnabled(True)
            self.tree.blockSignals(False)

        self.status_label.setText(
            f"根类型: {type(self.json_data).__name__}  |  "
            f"文件: {os.path.basename(self.current_file_path)}"
        )

    def _populate_children(self, data: Any, parent: QTreeWidgetItem):
        """填充容器节点的直接子节点（惰性加载用）。

        先把所有子节点构建为分离 item，再用 addChildren 批量挂载——
        相比逐个 QTreeWidgetItem(parent)，能将 N 次模型变更通知缩减为 1 次，
        在数千节点的容器上是数量级的差距。
        """
        items = []
        if isinstance(data, dict):
            for key, value in data.items():
                item = QTreeWidgetItem()
                item.setText(0, str(key))
                item.setData(0, Qt.UserRole + 2, key)
                self._set_cell(item, value)
                items.append(item)
        elif isinstance(data, list):
            for idx, value in enumerate(data):
                item = QTreeWidgetItem()
                item.setText(0, f"[{idx}]")
                item.setData(0, Qt.UserRole + 2, idx)
                self._set_cell(item, value)
                items.append(item)
        if items:
            parent.addChildren(items)

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """展开节点时惰性加载子节点。"""
        if item.data(0, Qt.UserRole + 3) is not False:
            return  # 已填充或非容器
        value = item.data(0, Qt.UserRole)
        self.tree.blockSignals(True)
        self.tree.setUpdatesEnabled(False)
        try:
            self._populate_children(value, item)
            item.setData(0, Qt.UserRole + 3, True)
        finally:
            self.tree.setUpdatesEnabled(True)
            self.tree.blockSignals(False)

    def _ensure_populated(self, item: QTreeWidgetItem):
        """确保节点已填充（搜索/展开全部时调用）。"""
        if item.data(0, Qt.UserRole + 3) is False:
            value = item.data(0, Qt.UserRole)
            self.tree.blockSignals(True)
            self.tree.setUpdatesEnabled(False)
            try:
                self._populate_children(value, item)
                item.setData(0, Qt.UserRole + 3, True)
            finally:
                self.tree.setUpdatesEnabled(True)
                self.tree.blockSignals(False)

    def _set_cell(self, item: QTreeWidgetItem, value: Any):
        item.setData(0, Qt.UserRole, value)
        if isinstance(value, dict):
            item.setText(1, f"({len(value)} 键)")
            item.setText(2, "object")
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.setData(0, Qt.UserRole + 3, False)  # 标记未填充
        elif isinstance(value, list):
            item.setText(1, f"[{len(value)} 项]")
            item.setText(2, "array")
            item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.setData(0, Qt.UserRole + 3, False)  # 标记未填充
        else:
            item.setText(1, _value_label(value))
            item.setText(2, type(value).__name__)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            color = _value_color(value)
            item.setForeground(1, color)
            item.setForeground(2, color)
            if isinstance(value, str):
                item.setToolTip(1, value)

    # ── 搜索 ─────────────────────────────────────────────

    def _on_search(self, keyword: str):
        if not keyword:
            self._restore_all(self.tree.invisibleRootItem())
            self.status_label.setText(
                "搜索结果: 已清除筛选" if self.json_data else "就绪"
            )
            return

        keyword = keyword.lower()
        match_count = self._filter_and_expand(
            self.tree.invisibleRootItem(), keyword
        )
        self._show_container_context(self.tree.invisibleRootItem())
        self.status_label.setText(f"搜索结果: 找到 {match_count} 个匹配节点")

    def _filter_and_expand(self, parent: QTreeWidgetItem, keyword: str) -> int:
        """递归搜索，隐藏不匹配节点，返回当前子树中匹配的节点数。"""
        total = 0
        for i in range(parent.childCount()):
            child = parent.child(i)
            self._ensure_populated(child)
            subtree_matches = self._filter_and_expand(child, keyword)

            key_ok = keyword in child.text(0).lower()
            val_ok = keyword in child.text(1).lower()
            matched = key_ok or val_ok or subtree_matches > 0

            child.setHidden(not matched)
            if matched:
                p = child
                while p:
                    p.setExpanded(True)
                    p = p.parent()
                total += 1

        return total

    def _show_container_context(self, parent: QTreeWidgetItem):
        """补全容器上下文：当容器中有叶子节点命中搜索时，显示该容器所有子节点。"""
        for i in range(parent.childCount()):
            child = parent.child(i)
            if not child.isHidden() and child.childCount() > 0:
                # 该容器可见且有子节点 → 检查是否包含直接命中的叶子
                has_matching_leaf = any(
                    not child.child(j).isHidden()
                    and child.child(j).childCount() == 0
                    for j in range(child.childCount())
                )
                if has_matching_leaf:
                    for j in range(child.childCount()):
                        child.child(j).setHidden(False)
                self._show_container_context(child)

    def _restore_all(self, parent: QTreeWidgetItem):
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setHidden(False)
            self._restore_all(child)

    # ── 展开 / 折叠 ──────────────────────────────────────

    def expand_all(self):
        self._expand_all_recursive(self.tree.invisibleRootItem())

    def _expand_all_recursive(self, parent: QTreeWidgetItem):
        for i in range(parent.childCount()):
            child = parent.child(i)
            self._ensure_populated(child)
            child.setExpanded(True)
            self._expand_all_recursive(child)

    def collapse_all(self):
        self.tree.collapseAll()

    # ── 清除数据 ─────────────────────────────────────────

    def _on_clear_requested(self):
        """清空按钮回调：确认后清除路径及所有已加载数据。"""
        if not self.json_data:
            self.path_edit.clear()
            return

        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="确认清除",
            content=f"确定要清除已加载的 JSON 数据 \"{os.path.basename(self.current_file_path)}\" 吗？",
            show_cancel_btn=True,
        ).exec()

        if confirmed:
            self._clear_all()

    def _clear_all(self):
        """清除全部数据，恢复初始状态。"""
        self.json_data = None
        self.current_file_path = ""
        self.path_edit.clear()
        self.file_info.setText("")
        self.file_size.setText("")
        self.tree.clear()
        self.search_edit.clear()
        self.status_label.setText("就绪 — 请打开一个 JSON 文件")

    # ── 右键扩展 ─────────────────────────────────────────

    def _open_url(self, url: str):
        """在系统默认浏览器中打开 URL。"""
        try:
            QDesktopServices.openUrl(QUrl(url))
            InfoBar.success(
                title="已打开",
                content=url,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
        except Exception as e:
            InfoBar.error(
                title="打开失败URL失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )
            print(f"打开{url}失败，{e}")

    def _parse_json_value(self, json_str: str):
        """将选中的 JSON 字符串解析并替换当前视图。"""
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            InfoBar.error(
                title="解析失败",
                content=f"行 {e.lineno} 列 {e.colno}: {e.msg}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return

        self.json_data = parsed
        self._build_tree()
        self.search_edit.clear()
        InfoBar.success(
            title="已解析",
            content=f"已将内嵌 JSON 替换到当前视图 ({_count_nodes(parsed)} 个节点)",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=2500,
        )

    # ── 编辑与还原 ───────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        """叶子节点值被编辑后的回调。"""
        raw = item.data(0, Qt.UserRole)
        # 跳过容器节点（仍可能有 childCount==0 的瞬态）和列号不符
        if column != 1 or isinstance(raw, (dict, list)) or item.childCount() > 0:
            return

        new_text = item.text(1)

        # 根据原始类型转换新值
        if raw is None:
            new_value = None if new_text == "null" else new_text
        elif isinstance(raw, bool):
            new_value = new_text.lower() in ("true", "1", "yes")
        elif isinstance(raw, int):
            try:
                new_value = int(new_text)
            except ValueError:
                return
        elif isinstance(raw, float):
            try:
                new_value = float(new_text)
            except ValueError:
                return
        else:
            new_value = new_text

        # 首次编辑时保存原始值
        if item.data(0, Qt.UserRole + 1) is None:
            item.setData(0, Qt.UserRole + 1, raw)

        # 更新外观
        item.setForeground(1, COLOR_EDITED)
        item.setForeground(2, COLOR_EDITED)
        if isinstance(raw, str) or isinstance(new_value, str):
            orig_label = _value_label(raw) if raw is not None else "null"
            cur_label = _value_label(new_value) if new_value is not None else "null"
            item.setToolTip(1, f"原始值: {orig_label}\n当前值: {cur_label}")

        # 同步到 json_data
        self._update_json_data(item, new_value)

    def _update_json_data(self, item: QTreeWidgetItem, new_value: Any):
        """沿树向上构建路径，更新 self.json_data 中对应位置的值。"""
        path = []
        cur = item
        while cur:
            info = cur.data(0, Qt.UserRole + 2)
            if info is not None:
                path.append(info)
            cur = cur.parent()
        path.reverse()

        if not path:
            self.json_data = new_value
            return

        target = self.json_data
        for key in path[:-1]:
            if not isinstance(target, (dict, list)):
                print(f"路径 {path} 中间节点 {key} 处遇到非容器值: {type(target).__name__}")
                InfoBar.warning(
                    title="路径错误",
                    content=f"路径 {path} 中间节点 {key} 处遇到非容器值: {type(target).__name__}",
                    parent=self, position=InfoBarPosition.TOP, duration=4000,
                )
                return
            try:
                target = target[key]
            except (KeyError, IndexError, TypeError) as e:
                print(f"路径 {path} 中 {key} 不存在: {e}")
                InfoBar.warning(
                    title="路径错误",
                    content=f"路径 {path} 中 {key} 不存在: {e}",
                    parent=self, position=InfoBarPosition.TOP, duration=4000,
                )
                return

        if not isinstance(target, (dict, list)):
            print(f"最终节点非容器 (类型: {type(target).__name__}, 值: {str(target)[:50]})")
            InfoBar.warning(
                title="路径错误",
                content=f"最终节点非容器 (类型: {type(target).__name__}, 值: {str(target)[:50]})，无法写入 path={path}",
                parent=self, position=InfoBarPosition.TOP, duration=4000,
            )
            return

        try:
            target[path[-1]] = new_value
        except (KeyError, IndexError, TypeError) as e:
            InfoBar.warning(
                title="写入失败",
                content=f"路径 {path} 写入 {path[-1]} 失败: {e}",
                parent=self, position=InfoBarPosition.TOP, duration=4000,
            )

    def _restore_value(self, item: QTreeWidgetItem):
        """还原节点到编辑前的原始值。"""
        original = item.data(0, Qt.UserRole + 1)
        if original is None:
            return

        self.tree.blockSignals(True)
        item.setText(1, _value_label(original))
        color = _value_color(original)
        item.setForeground(1, color)
        item.setForeground(2, color)
        if isinstance(original, str):
            item.setToolTip(1, original)
        else:
            item.setToolTip(1, "")
        item.setData(0, Qt.UserRole + 1, None)
        self.tree.blockSignals(False)

        self._update_json_data(item, original)

    # ── 保存 ─────────────────────────────────────────────

    def _save_to_file(self):
        """保存：覆盖当前文件。"""
        if self.json_data is None:
            InfoBar.warning(
                title="无数据",
                content="请先加载 JSON 文件",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        if not self.current_file_path:
            self._save_as()
            return

        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="确认保存",
            content=f"确定要覆盖保存到 \"{os.path.basename(self.current_file_path)}\" 吗？",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return

        try:
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                json.dump(self.json_data, f, ensure_ascii=False, indent=2)
            InfoBar.success(
                title="已保存",
                content=os.path.basename(self.current_file_path),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
            # 重新构建树以清除编辑标记
            self._clear_edit_marks()
            self._build_tree()
        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )

    def _save_as(self):
        """另存为：选择新路径保存。"""
        if self.json_data is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "", "JSON 文件 (*.json);;所有文件 (*)",
        )
        if not path:
            return

        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="确认另存为",
            content=f"确定要保存到 \"{os.path.basename(path)}\" 吗？",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.json_data, f, ensure_ascii=False, indent=2)
            self.current_file_path = path
            self.path_edit.setText(path)
            self.file_info.setText(f"文件: {os.path.basename(path)}")
            self.file_size.setText(_format_file_size(os.path.getsize(path)))
            InfoBar.success(
                title="已保存",
                content=os.path.basename(path),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
            self._clear_edit_marks()
            self._build_tree()
        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )

    def _clear_edit_marks(self):
        """清除所有节点的编辑标记（递归遍历树）。"""
        def _walk(item):
            item.setData(0, Qt.UserRole + 1, None)
            for i in range(item.childCount()):
                _walk(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            _walk(self.tree.topLevelItem(i))
