#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INI 配置文件查看器 UI — 节/键值浏览、搜索、行内编辑、拖拽加载。"""

import configparser
import io
import os
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent, QPalette
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SearchLineEdit,
    SplitPushButton,
    StrongBodyLabel,
    TreeWidget,
    isDarkTheme,
    qconfig,
)

# ── 配色 ────────────────────────────────────────────────
COLOR_VALUE = QColor("#4CAF50")
COLOR_EDITED = QColor("#FF5722")
COLOR_EMPTY = QColor("#9E9E9E")


def _format_file_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _make_parser() -> configparser.RawConfigParser:
    """返回一个保持键名大小写、不做 % 插值的解析器。"""
    parser = configparser.RawConfigParser()
    parser.optionxform = str  # 保留键名原始大小写
    return parser


# ── 树组件 ────────────────────────────────────────────────

class ConfigTreeWidget(TreeWidget):
    """支持拖拽和右键菜单的 INI 配置树。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setHeaderLabels(["键", "值"])
        self.header().setSectionResizeMode(0, QHeaderView.Interactive)
        self.header().setSectionResizeMode(1, QHeaderView.Stretch)
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
            if path.lower().endswith((".ini", ".cfg", ".conf")):
                self._find_page().load_config_file(path)
                return
        event.ignore()

    def _find_page(self):
        p = self.parent()
        while p and not isinstance(p, ConfigViewerPage):
            p = p.parent()
        return p

    # 右键菜单 ──

    def _show_context_menu(self, pos):
        item = self.itemAt(pos)
        page = self._find_page()
        if page is None:
            return

        menu = RoundMenu("", self)

        # 顶层（空白处或节节点）
        act_add_section = QAction("新增节", self)
        act_add_section.triggered.connect(page._add_section)
        menu.addAction(act_add_section)

        if item is not None:
            is_section = item.parent() is None
            if is_section:
                act_add_key = QAction("在该节新增键", self)
                act_add_key.triggered.connect(lambda _c, it=item: page._add_key(it))
                menu.addAction(act_add_key)

                menu.addSeparator()
                act_rename_section = QAction("重命名节", self)
                act_rename_section.triggered.connect(
                    lambda _c, it=item: page._rename_section(it)
                )
                menu.addAction(act_rename_section)

                act_remove_section = QAction("删除节", self)
                act_remove_section.triggered.connect(
                    lambda _c, it=item: page._remove_section(it)
                )
                menu.addAction(act_remove_section)
            else:
                menu.addSeparator()
                act_copy_val = QAction("复制值", self)
                act_copy_val.triggered.connect(lambda _c, it=item: self._copy_value(it))
                menu.addAction(act_copy_val)

                act_copy_path = QAction("复制 节.键", self)
                act_copy_path.triggered.connect(lambda _c, it=item: self._copy_path(it))
                menu.addAction(act_copy_path)

                if item.data(0, Qt.UserRole + 1) is not None:
                    act_restore = QAction("还原", self)
                    act_restore.triggered.connect(
                        lambda _c, it=item: page._restore_value(it)
                    )
                    menu.addAction(act_restore)

                menu.addSeparator()
                act_remove_key = QAction("删除键", self)
                act_remove_key.triggered.connect(
                    lambda _c, it=item: page._remove_key(it)
                )
                menu.addAction(act_remove_key)

        menu.exec_(self.viewport().mapToGlobal(pos))

    def _copy_value(self, item: QTreeWidgetItem):
        QApplication.clipboard().setText(item.text(1))

    def _copy_path(self, item: QTreeWidgetItem):
        section = item.parent().text(0) if item.parent() else ""
        key = item.text(0)
        QApplication.clipboard().setText(f"{section}.{key}" if section else key)


# ── 主页面 ────────────────────────────────────────────────

class ConfigViewerPage(QWidget):
    """INI 配置文件查看器主页面。"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("ConfigViewerPage")
        self.current_file_path = ""
        self.parser: Optional[configparser.RawConfigParser] = None
        self._dirty = False
        self._init_ui()
        # 主题切换时重建树,确保前景色 / 编辑标记重新着色
        qconfig.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        if self.parser is not None:
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

        fc_title = StrongBodyLabel("INI 配置文件", self)
        fc_layout.addWidget(fc_title)

        path_row = QHBoxLayout()
        self.path_edit = LineEdit(self)
        self.path_edit.setClearButtonEnabled(True)
        self.path_edit.setPlaceholderText("拖入 .ini / .cfg / .conf 文件，或点击浏览选择…")
        self.path_edit.setReadOnly(True)
        self.path_edit.clearButton.clicked.disconnect()
        self.path_edit.clearButton.clicked.connect(self._on_clear_requested)

        browse_btn = PrimaryPushButton("浏览", self)
        browse_btn.setIcon(FIF.FOLDER)
        browse_btn.clicked.connect(self.browse_file)

        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse_btn)

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

        add_section_btn = PushButton("新增节", self)
        add_section_btn.setIcon(FIF.ADD)
        add_section_btn.clicked.connect(self._add_section)

        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索节或键…")
        self.search_edit.setMaximumWidth(300)
        self.search_edit.searchSignal.connect(self._on_search)
        self.search_edit.clearSignal.connect(lambda: self._on_search(""))
        self.search_edit.returnPressed.connect(
            lambda: self.search_edit.search() if self.search_edit.text().strip()
            else self.search_edit.clearSignal.emit()
        )

        tool_row.addWidget(expand_btn)
        tool_row.addWidget(collapse_btn)
        tool_row.addWidget(add_section_btn)
        tool_row.addStretch(1)
        tool_row.addWidget(self.search_edit)

        layout.addWidget(tool_card)

        # ===== 树 =====
        self.tree = ConfigTreeWidget(self)
        self.tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.tree, 1)

        # ===== 状态栏 =====
        status_card = CardWidget(self)
        s_row = QHBoxLayout(status_card)
        s_row.setContentsMargins(15, 8, 15, 8)

        self.status_label = BodyLabel("就绪 — 请打开一个 INI 文件", self)
        s_row.addWidget(self.status_label)
        s_row.addStretch(1)

        layout.addWidget(status_card)

    # ── 文件操作 ─────────────────────────────────────────

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 INI 文件", "",
            "配置文件 (*.ini *.cfg *.conf);;所有文件 (*)",
        )
        if path:
            self.load_config_file(path)

    def load_config_file(self, file_path: str):
        """读取并解析 INI 文件，构建树。"""
        if not os.path.exists(file_path):
            InfoBar.error(
                title="文件不存在",
                content=file_path,
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        parser = _make_parser()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                parser.read_file(f)
        except UnicodeDecodeError:
            # 退回到 GBK，常见于 Windows 上的旧配置
            try:
                parser = _make_parser()
                with open(file_path, "r", encoding="gbk") as f:
                    parser.read_file(f)
            except Exception as e:
                InfoBar.error(
                    title="编码错误",
                    content=str(e),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                )
                return
        except configparser.Error as e:
            InfoBar.error(
                title="INI 解析错误",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return
        except Exception as e:
            InfoBar.error(
                title="读取失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return

        self.parser = parser
        self.current_file_path = file_path
        self._dirty = False
        self.path_edit.setText(file_path)
        fsize = os.path.getsize(file_path)
        self.file_info.setText(f"文件: {os.path.basename(file_path)}")
        self.file_size.setText(_format_file_size(fsize))

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
        try:
            self.tree.clear()
            if self.parser is None:
                self.status_label.setText("无数据")
                return

            section_count = 0
            key_count = 0

            # DEFAULT 节单独显示在最前
            defaults = dict(self.parser.defaults())
            if defaults:
                section_count += 1
                key_count += len(defaults)
                self._append_section_item("DEFAULT", defaults.items(), is_default=True)

            for section in self.parser.sections():
                section_count += 1
                items = self.parser.items(section, raw=True)
                # 过滤掉来自 DEFAULT 的继承项（保留本节自身的）
                local_keys = set(self.parser._sections[section].keys())  # 内部字段
                pairs = [(k, v) for k, v in items if k in local_keys]
                key_count += len(pairs)
                self._append_section_item(section, pairs)
        finally:
            self.tree.setUpdatesEnabled(True)
            self.tree.blockSignals(False)

        self.status_label.setText(
            f"共 {section_count} 节，{key_count} 个键  |  "
            f"文件: {os.path.basename(self.current_file_path)}"
        )

    def _append_section_item(self, section: str, pairs, is_default: bool = False):
        """构建一个节（含其所有键值对）并挂到树上。"""
        section_item = QTreeWidgetItem()
        section_item.setText(0, section)
        section_item.setData(0, Qt.UserRole + 2, "section")
        if is_default:
            section_item.setData(0, Qt.UserRole + 4, True)
        # 使用树自身的字体作为基底再加粗，避免分离 item 默认字体不一致
        font = self.tree.font()
        font.setBold(True)
        section_item.setFont(0, font)
        # 节名可编辑（除 DEFAULT 外）
        if not is_default:
            section_item.setFlags(section_item.flags() | Qt.ItemIsEditable)

        children = []
        for key, value in pairs:
            child = QTreeWidgetItem()
            child.setText(0, str(key))
            child.setText(1, "" if value is None else str(value))
            child.setData(0, Qt.UserRole + 2, "key")
            child.setFlags(child.flags() | Qt.ItemIsEditable)
            self._apply_value_color(child, value)
            children.append(child)

        if children:
            section_item.addChildren(children)
        self.tree.addTopLevelItem(section_item)
        section_item.setExpanded(True)

    def _apply_value_color(self, item: QTreeWidgetItem, value: Optional[str]):
        if value is None or value == "":
            item.setForeground(1, COLOR_EMPTY)
        else:
            item.setForeground(1, COLOR_VALUE)

    # ── 搜索 ─────────────────────────────────────────────

    def _on_search(self, keyword: str):
        if not keyword:
            self._restore_all(self.tree.invisibleRootItem())
            self.status_label.setText(
                "搜索结果: 已清除筛选" if self.parser else "就绪"
            )
            return

        keyword = keyword.lower()
        match_count = self._filter_and_expand(self.tree.invisibleRootItem(), keyword)
        self.status_label.setText(f"搜索结果: 找到 {match_count} 个匹配项")

    def _filter_and_expand(self, parent: QTreeWidgetItem, keyword: str) -> int:
        total = 0
        for i in range(parent.childCount()):
            child = parent.child(i)
            subtree = self._filter_and_expand(child, keyword)
            key_ok = keyword in child.text(0).lower()
            val_ok = keyword in child.text(1).lower()
            matched = key_ok or val_ok or subtree > 0
            child.setHidden(not matched)
            if matched:
                p = child
                while p:
                    p.setExpanded(True)
                    p = p.parent()
                total += 1
        return total

    def _restore_all(self, parent: QTreeWidgetItem):
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setHidden(False)
            self._restore_all(child)

    # ── 展开 / 折叠 ──────────────────────────────────────

    def expand_all(self):
        self.tree.expandAll()

    def collapse_all(self):
        self.tree.collapseAll()

    # ── 清除数据 ─────────────────────────────────────────

    def _on_clear_requested(self):
        if not self.parser:
            self.path_edit.clear()
            return

        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="确认清除",
            content=f"确定要清除已加载的配置 \"{os.path.basename(self.current_file_path)}\" 吗？",
            show_cancel_btn=True,
        ).exec()

        if confirmed:
            self._clear_all()

    def _clear_all(self):
        self.parser = None
        self.current_file_path = ""
        self._dirty = False
        self.path_edit.clear()
        self.file_info.setText("")
        self.file_size.setText("")
        self.tree.clear()
        self.search_edit.clear()
        self.status_label.setText("就绪 — 请打开一个 INI 文件")

    # ── 节 / 键 增删 ────────────────────────────────────

    def _add_section(self):
        if self.parser is None:
            self.parser = _make_parser()
            self.current_file_path = ""
            self.path_edit.clear()
            self.file_info.setText("(未保存)")
            self.file_size.setText("")

        name, ok = QInputDialog.getText(self, "新增节", "节名:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name == "DEFAULT" or self.parser.has_section(name):
            InfoBar.warning(
                title="名称已存在",
                content=f"节 [{name}] 已存在",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        self.parser.add_section(name)
        self._dirty = True
        self._build_tree()

    def _add_key(self, section_item: QTreeWidgetItem):
        section = section_item.text(0)
        is_default = bool(section_item.data(0, Qt.UserRole + 4))

        key, ok = QInputDialog.getText(self, "新增键", f"在 [{section}] 中的键名:")
        if not ok:
            return
        key = key.strip()
        if not key:
            return

        # DEFAULT 节使用 parser.defaults() 不能直接 add，需走内部接口或 set
        if is_default:
            self.parser._defaults[key] = ""  # type: ignore[attr-defined]
        else:
            if self.parser.has_option(section, key):
                InfoBar.warning(
                    title="键已存在",
                    content=f"[{section}] 中已存在键 {key}",
                    parent=self,
                    position=InfoBarPosition.TOP,
                )
                return
            self.parser.set(section, key, "")
        self._dirty = True
        self._build_tree()

    def _remove_section(self, section_item: QTreeWidgetItem):
        section = section_item.text(0)
        is_default = bool(section_item.data(0, Qt.UserRole + 4))
        if is_default:
            InfoBar.warning(
                title="无法删除",
                content="DEFAULT 节不能整体删除",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="确认删除",
            content=f"确定要删除节 [{section}] 及其所有键吗？",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return

        self.parser.remove_section(section)
        self._dirty = True
        self._build_tree()

    def _rename_section(self, section_item: QTreeWidgetItem):
        old_name = section_item.text(0)
        new_name, ok = QInputDialog.getText(
            self, "重命名节", "新节名:", text=old_name
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        if new_name == "DEFAULT" or self.parser.has_section(new_name):
            InfoBar.warning(
                title="名称已存在",
                content=f"节 [{new_name}] 已存在",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        # 保留原有键值
        items = self.parser.items(old_name, raw=True)
        local_keys = set(self.parser._sections[old_name].keys())
        self.parser.add_section(new_name)
        for k, v in items:
            if k in local_keys:
                self.parser.set(new_name, k, v)
        self.parser.remove_section(old_name)
        self._dirty = True
        self._build_tree()

    def _remove_key(self, key_item: QTreeWidgetItem):
        section_item = key_item.parent()
        if section_item is None:
            return
        section = section_item.text(0)
        key = key_item.text(0)
        is_default = bool(section_item.data(0, Qt.UserRole + 4))

        from customWidget import MessageConfirmBox

        confirmed = MessageConfirmBox(
            parent=self.window(),
            title="确认删除",
            content=f"确定要从 [{section}] 中删除键 \"{key}\" 吗？",
            show_cancel_btn=True,
        ).exec()
        if not confirmed:
            return

        if is_default:
            self.parser._defaults.pop(key, None)  # type: ignore[attr-defined]
        else:
            self.parser.remove_option(section, key)
        self._dirty = True
        self._build_tree()

    # ── 行内编辑 ─────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self.parser is None:
            return

        node_kind = item.data(0, Qt.UserRole + 2)
        if node_kind == "section":
            # 不在此处处理 — 节重命名走右键菜单
            return
        if node_kind != "key" or column not in (0, 1):
            return

        section_item = item.parent()
        if section_item is None:
            return
        section = section_item.text(0)
        is_default = bool(section_item.data(0, Qt.UserRole + 4))

        # 记录原始值（首次编辑时）
        if item.data(0, Qt.UserRole + 1) is None:
            try:
                if is_default:
                    orig_val = self.parser.defaults().get(item.text(0), "")
                else:
                    orig_val = self.parser.get(section, item.text(0), raw=True)
            except (configparser.NoSectionError, configparser.NoOptionError):
                orig_val = ""
            item.setData(0, Qt.UserRole + 1, (item.text(0), orig_val))

        new_key = item.text(0).strip()
        new_val = item.text(1)

        if not new_key:
            InfoBar.warning(
                title="键名不能为空",
                content="已撤销修改",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            self.tree.blockSignals(True)
            orig = item.data(0, Qt.UserRole + 1)
            if orig is not None:
                item.setText(0, orig[0])
                item.setText(1, orig[1] or "")
            self.tree.blockSignals(False)
            return

        # 同步到 parser
        try:
            if is_default:
                # 处理键名变更
                orig_key = item.data(0, Qt.UserRole + 1)[0]
                if orig_key != new_key:
                    self.parser._defaults.pop(orig_key, None)  # type: ignore[attr-defined]
                self.parser._defaults[new_key] = new_val  # type: ignore[attr-defined]
            else:
                orig_key = item.data(0, Qt.UserRole + 1)[0]
                if orig_key != new_key and self.parser.has_option(section, orig_key):
                    self.parser.remove_option(section, orig_key)
                self.parser.set(section, new_key, new_val)
        except Exception as e:
            InfoBar.error(
                title="写入失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        self._dirty = True
        item.setForeground(0, COLOR_EDITED)
        item.setForeground(1, COLOR_EDITED)

    def _restore_value(self, item: QTreeWidgetItem):
        original = item.data(0, Qt.UserRole + 1)
        if original is None:
            return
        orig_key, orig_val = original
        section_item = item.parent()
        if section_item is None:
            return
        section = section_item.text(0)
        is_default = bool(section_item.data(0, Qt.UserRole + 4))

        # 撤销 parser 中的修改
        cur_key = item.text(0)
        try:
            if is_default:
                if cur_key != orig_key:
                    self.parser._defaults.pop(cur_key, None)  # type: ignore[attr-defined]
                self.parser._defaults[orig_key] = orig_val or ""  # type: ignore[attr-defined]
            else:
                if cur_key != orig_key and self.parser.has_option(section, cur_key):
                    self.parser.remove_option(section, cur_key)
                self.parser.set(section, orig_key, orig_val or "")
        except Exception as e:
            InfoBar.error(
                title="还原失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        self.tree.blockSignals(True)
        item.setText(0, orig_key)
        item.setText(1, orig_val or "")
        self._apply_value_color(item, orig_val)
        # 清除编辑时设的橙色前景，让键名回到主题默认色
        item.setData(0, Qt.ForegroundRole, None)
        item.setData(0, Qt.UserRole + 1, None)
        self.tree.blockSignals(False)

    # ── 保存 ─────────────────────────────────────────────

    def _serialize(self) -> str:
        """把当前 parser 序列化为 INI 文本（不写入文件）。"""
        buf = io.StringIO()
        self.parser.write(buf)
        return buf.getvalue()

    def _save_to_file(self):
        if self.parser is None:
            InfoBar.warning(
                title="无数据",
                content="请先加载或创建 INI 配置",
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
                f.write(self._serialize())
            InfoBar.success(
                title="已保存",
                content=os.path.basename(self.current_file_path),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
            self._dirty = False
            self._build_tree()
        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )

    def _save_as(self):
        if self.parser is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", "",
            "INI 文件 (*.ini);;配置文件 (*.cfg *.conf);;所有文件 (*)",
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
                f.write(self._serialize())
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
            self._dirty = False
            self._build_tree()
        except Exception as e:
            InfoBar.error(
                title="保存失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
            )