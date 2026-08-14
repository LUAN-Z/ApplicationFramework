#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量文件关键字/行范围替换工具。"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QAction,
    QFileDialog,
    QHBoxLayout,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SpinBox,
    StrongBodyLabel,
    TableWidget,
    RoundMenu,
)


@dataclass
class ReplacementPreview:
    path: Path
    changed: bool
    count: int
    error: str = ""


class DropFileTable(TableWidget):
    """支持拖入文件/文件夹的表格。"""

    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile()
        ]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class FileReplacerPage(QWidget):
    """批量文件替换页面。"""

    MODE_KEYWORDS = "关键字替换"
    MODE_LINES = "行范围替换"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FileReplacerPage")
        self.setAcceptDrops(True)
        self.files: List[Path] = []
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(StrongBodyLabel("文件替换", self))
        title_col.addWidget(BodyLabel("批量处理文本文件，支持拖拽文件、关键字映射和指定行范围替换", self))
        title_row.addLayout(title_col, 1)

        self.preview_btn = PushButton("预览", self)
        self.preview_btn.setIcon(FIF.VIEW.icon())
        self.preview_btn.clicked.connect(self.preview_changes)
        title_row.addWidget(self.preview_btn)

        self.apply_btn = PrimaryPushButton("执行替换", self)
        self.apply_btn.setIcon(FIF.SAVE.icon())
        self.apply_btn.clicked.connect(self.apply_changes)
        title_row.addWidget(self.apply_btn)
        root.addLayout(title_row)

        main = QHBoxLayout()
        main.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self._build_files_card(), 3)
        left.addWidget(self._build_options_card(), 2)
        main.addLayout(left, 5)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._build_rule_card(), 4)
        right.addWidget(self._build_log_card(), 3)
        main.addLayout(right, 6)

        root.addLayout(main, 1)

    def _build_files_card(self) -> QWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(StrongBodyLabel("文件列表", self))
        row.addStretch(1)

        add_files_btn = PushButton("添加文件", self)
        add_files_btn.setIcon(FIF.ADD.icon())
        add_files_btn.clicked.connect(self.add_files)
        row.addWidget(add_files_btn)

        clear_btn = PushButton("清空", self)
        clear_btn.setIcon(FIF.DELETE.icon())
        clear_btn.clicked.connect(self.clear_files)
        row.addWidget(clear_btn)
        layout.addLayout(row)

        self.file_table = DropFileTable(self)
        self.file_table.filesDropped.connect(self.add_file_paths)
        self.file_table.setColumnCount(2)
        self.file_table.setHorizontalHeaderLabels(["文件", "状态"])
        self.file_table.verticalHeader().hide()
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setEditTriggers(TableWidget.NoEditTriggers)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self._show_file_menu)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.file_table, 1)

        return card

    def _build_options_card(self) -> QWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(StrongBodyLabel("执行选项", self))

        mode_row = QHBoxLayout()
        mode_row.addWidget(BodyLabel("模式", self))
        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems([self.MODE_KEYWORDS, self.MODE_LINES])
        self.mode_combo.currentTextChanged.connect(self._sync_mode_ui)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        encoding_row = QHBoxLayout()
        encoding_row.addWidget(BodyLabel("编码", self))
        self.encoding_edit = LineEdit(self)
        self.encoding_edit.setText("utf-8")
        encoding_row.addWidget(self.encoding_edit, 1)
        layout.addLayout(encoding_row)

        self.backup_check = CheckBox("执行前创建 .bak 备份", self)
        self.backup_check.setChecked(True)
        layout.addWidget(self.backup_check)

        return card

    def _build_rule_card(self) -> QWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(StrongBodyLabel("替换规则", self))

        self.keyword_panel = QWidget(self)
        keyword_layout = QVBoxLayout(self.keyword_panel)
        keyword_layout.setContentsMargins(0, 0, 0, 0)
        keyword_layout.setSpacing(8)
        header_row = QHBoxLayout()
        header_row.addWidget(BodyLabel("每行一组关键字映射", self))
        header_row.addStretch(1)
        add_rule_btn = PushButton("新增规则", self)
        add_rule_btn.setIcon(FIF.ADD.icon())
        add_rule_btn.clicked.connect(lambda _checked=False: self.add_keyword_rule_row())
        header_row.addWidget(add_rule_btn)
        keyword_layout.addLayout(header_row)

        label_row = QHBoxLayout()
        label_row.addWidget(BodyLabel("原关键字", self), 1)
        label_row.addWidget(BodyLabel("新关键字", self), 1)
        label_row.addSpacing(76)
        keyword_layout.addLayout(label_row)

        self.keyword_rule_rows = []
        self.keyword_rules_layout = QVBoxLayout()
        self.keyword_rules_layout.setSpacing(8)
        keyword_layout.addLayout(self.keyword_rules_layout)
        keyword_layout.addStretch(1)
        self.add_keyword_rule_row("AA", "BB")
        layout.addWidget(self.keyword_panel, 1)

        self.line_panel = QWidget(self)
        line_layout = QVBoxLayout(self.line_panel)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(8)

        range_row = QHBoxLayout()
        range_row.addWidget(BodyLabel("从第", self))
        self.start_line_spin = SpinBox(self)
        self.start_line_spin.setRange(1, 999999)
        self.start_line_spin.setValue(5)
        range_row.addWidget(self.start_line_spin)
        range_row.addWidget(BodyLabel("行到第", self))
        self.end_line_spin = SpinBox(self)
        self.end_line_spin.setRange(1, 999999)
        self.end_line_spin.setValue(20)
        range_row.addWidget(self.end_line_spin)
        range_row.addWidget(BodyLabel("行", self))
        range_row.addStretch(1)
        line_layout.addLayout(range_row)

        self.line_content_edit = PlainTextEdit(self)
        self.line_content_edit.setPlaceholderText("输入用于替换该行范围的新内容")
        line_layout.addWidget(self.line_content_edit, 1)
        layout.addWidget(self.line_panel, 1)

        self._sync_mode_ui(self.mode_combo.currentText())
        return card

    def _build_log_card(self) -> QWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(StrongBodyLabel("预览 / 日志", self))

        self.log_text = PlainTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("预览结果和执行日志会显示在这里")
        layout.addWidget(self.log_text, 1)
        return card

    def _sync_mode_ui(self, mode: str) -> None:
        self.keyword_panel.setVisible(mode == self.MODE_KEYWORDS)
        self.line_panel.setVisible(mode == self.MODE_LINES)

    def add_keyword_rule_row(self, old: str = "", new: str = "") -> None:
        row_widget = QWidget(self.keyword_panel)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        old_edit = LineEdit(row_widget)
        old_edit.setPlaceholderText("AA")
        old_edit.setText(old)
        new_edit = LineEdit(row_widget)
        new_edit.setPlaceholderText("BB")
        new_edit.setText(new)
        remove_btn = PushButton("删除", row_widget)
        remove_btn.setIcon(FIF.DELETE.icon())

        row.addWidget(old_edit, 1)
        row.addWidget(new_edit, 1)
        row.addWidget(remove_btn)

        self.keyword_rules_layout.addWidget(row_widget)
        self.keyword_rule_rows.append((row_widget, old_edit, new_edit))
        remove_btn.clicked.connect(
            lambda _checked=False: self.remove_keyword_rule_row(row_widget)
        )

    def remove_keyword_rule_row(self, row_widget: QWidget) -> None:
        if len(self.keyword_rule_rows) <= 1:
            for widget, old_edit, new_edit in self.keyword_rule_rows:
                if widget is row_widget:
                    old_edit.clear()
                    new_edit.clear()
                    return

        self.keyword_rule_rows = [
            row for row in self.keyword_rule_rows if row[0] is not row_widget
        ]
        self.keyword_rules_layout.removeWidget(row_widget)
        row_widget.deleteLater()

    def add_files(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要替换的文件",
            "",
            "文本文件 (*.txt *.md *.json *.ini *.cfg *.py *.yaml *.yml);;所有文件 (*)",
        )
        if not file_paths:
            return

        self.add_file_paths(file_paths)

    def add_file_paths(self, file_paths: List[str]) -> None:
        existing = {path.resolve() for path in self.files}
        for file_path in file_paths:
            path = Path(file_path).resolve()
            candidates = path.rglob("*") if path.is_dir() else [path]
            for candidate in candidates:
                candidate = candidate.resolve()
                if candidate.is_file() and candidate not in existing:
                    self.files.append(candidate)
                    existing.add(candidate)

        self._refresh_file_table()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile()
        ]
        if paths:
            self.add_file_paths(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def clear_files(self) -> None:
        self.files.clear()
        self._refresh_file_table()
        self.log_text.clear()

    def _show_file_menu(self, pos) -> None:
        row = self.file_table.rowAt(pos.y())
        if row < 0 or row >= len(self.files):
            return

        path = self.files[row]
        menu = RoundMenu("", self)

        open_file = QAction(FIF.DOCUMENT.icon(), "打开文件", self)
        open_file.triggered.connect(lambda: self._open_file(path))
        menu.addAction(open_file)

        open_folder = QAction(FIF.FOLDER.icon(), "打开所在目录", self)
        open_folder.triggered.connect(lambda: self._open_parent_dir(path))
        menu.addAction(open_folder)

        menu.exec_(self.file_table.viewport().mapToGlobal(pos))

    def _open_file(self, path: Path) -> None:
        if not path.exists():
            self._show_missing_file(path)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_parent_dir(self, path: Path) -> None:
        parent = path.parent
        if not parent.exists():
            self._show_missing_file(parent)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent)))

    def _show_missing_file(self, path: Path) -> None:
        InfoBar.error(
            title="路径不存在",
            content=str(path),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=4000,
        )

    def preview_changes(self) -> None:
        try:
            previews = self._preview_all()
        except Exception as exc:
            InfoBar.error(
                title="无法预览",
                content=str(exc),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return
        self._render_previews(previews, applied=False)

    def apply_changes(self) -> None:
        try:
            previews = self._preview_all()
        except Exception as exc:
            InfoBar.error(
                title="无法执行",
                content=str(exc),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return

        changed = [item for item in previews if item.changed and not item.error]
        if not changed:
            self._render_previews(previews, applied=False)
            InfoBar.info(
                title="没有可替换内容",
                content="没有文件会发生变化",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return

        encoding = self._encoding()
        errors = []
        for item in changed:
            try:
                original = item.path.read_text(encoding=encoding)
                updated, _ = self._replace_content(original)
                if self.backup_check.isChecked():
                    shutil.copy2(item.path, item.path.with_suffix(item.path.suffix + ".bak"))
                item.path.write_text(updated, encoding=encoding)
            except Exception as exc:
                errors.append(f"{item.path.name}: {exc}")

        self._render_previews(previews, applied=True)
        self._refresh_file_table()

        if errors:
            InfoBar.error(
                title="部分文件替换失败",
                content="; ".join(errors[:3]),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=6000,
            )
        else:
            InfoBar.success(
                title="替换完成",
                content=f"已处理 {len(changed)} 个文件",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3500,
            )

    def _preview_all(self) -> List[ReplacementPreview]:
        if not self.files:
            raise ValueError("请先添加至少一个文件")

        previews = []
        encoding = self._encoding()
        for path in self.files:
            try:
                content = path.read_text(encoding=encoding)
                updated, count = self._replace_content(content)
                previews.append(
                    ReplacementPreview(
                        path=path,
                        changed=updated != content,
                        count=count,
                    )
                )
            except Exception as exc:
                previews.append(
                    ReplacementPreview(path=path, changed=False, count=0, error=str(exc))
                )
        return previews

    def _replace_content(self, content: str) -> Tuple[str, int]:
        if self.mode_combo.currentText() == self.MODE_KEYWORDS:
            return self._replace_keywords(content)
        return self._replace_lines(content)

    def _replace_keywords(self, content: str) -> Tuple[str, int]:
        rules = self._keyword_rules()
        if not rules:
            raise ValueError("请填写至少一条关键字替换规则")

        updated = content
        total = 0
        for old, new in rules.items():
            total += updated.count(old)
            updated = updated.replace(old, new)
        return updated, total

    def _replace_lines(self, content: str) -> Tuple[str, int]:
        start = self.start_line_spin.value()
        end = self.end_line_spin.value()
        if start > end:
            raise ValueError("起始行不能大于结束行")

        lines = content.splitlines(keepends=True)
        if not lines:
            raise ValueError("文件内容为空")
        if start > len(lines):
            return content, 0

        start_index = start - 1
        end_index = min(end, len(lines))
        replacement = self.line_content_edit.toPlainText()
        replacement_lines = replacement.splitlines(keepends=True)
        if replacement and not replacement.endswith(("\n", "\r")):
            replacement_lines[-1] += "\n"

        updated_lines = lines[:start_index] + replacement_lines + lines[end_index:]
        return "".join(updated_lines), end_index - start_index

    def _keyword_rules(self) -> Dict[str, str]:
        rules: Dict[str, str] = {}
        for row_number, (_, old_edit, new_edit) in enumerate(self.keyword_rule_rows, 1):
            old = old_edit.text()
            new = new_edit.text()
            if not old and not new:
                continue
            if not old:
                raise ValueError(f"第 {row_number} 行原关键字不能为空")
            rules[old] = new
        return rules

    def _encoding(self) -> str:
        return self.encoding_edit.text().strip() or "utf-8"

    def _refresh_file_table(self) -> None:
        self.file_table.setRowCount(len(self.files))
        for row, path in enumerate(self.files):
            self.file_table.setItem(row, 0, QTableWidgetItem(str(path)))
            self.file_table.setItem(row, 1, QTableWidgetItem("待处理"))
        self.file_table.resizeColumnsToContents()

    def _render_previews(self, previews: List[ReplacementPreview], applied: bool) -> None:
        lines = ["执行结果" if applied else "预览结果"]
        for item in previews:
            if item.error:
                status = f"失败: {item.error}"
            elif item.changed:
                status = f"将替换 {item.count} 处" if not applied else f"已替换 {item.count} 处"
            else:
                status = "无变化"
            lines.append(f"- {item.path.name}: {status}")
        self.log_text.setPlainText("\n".join(lines))

        for row, item in enumerate(previews):
            if row >= self.file_table.rowCount():
                continue
            status_item = self.file_table.item(row, 1)
            if status_item is not None:
                status_item.setText("失败" if item.error else "有变化" if item.changed else "无变化")
