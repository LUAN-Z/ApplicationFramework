#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令执行工具 UI."""

import os
from typing import List, Optional

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QFileDialog, QHeaderView, QTableWidgetItem,
    QAbstractItemView, QMenu, QAction
)

from qfluentwidgets import (
    PushButton, PrimaryPushButton, LineEdit, TextEdit,
    TableWidget, InfoBar, InfoBarPosition, ComboBox,
    BodyLabel, StrongBodyLabel, CardWidget, FluentIcon as FIF,
)

from .logic import (
    CommandExecutor,
    build_command,
    default_output_path,
    ensure_output_directory,
    get_tool_help,
    output_path_in_directory,
)

from customWidget import InfoBarWithButton

class DraggableTableWidget(TableWidget):
    """支持文件拖拽的表格组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["输入路径", "输出路径", "附加参数", "状态"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.setMouseTracking(True)
        self.itemEntered.connect(self.on_item_entered)

        # 存储每行的完整命令
        self.row_commands = {}

    def on_item_entered(self, item):
        """鼠标悬浮显示完整命令"""
        row = item.row()
        if row in self.row_commands:
            cmd = self.row_commands[row]
            # 截断过长的命令用于 tooltip
            tooltip_text = f"完整命令:{cmd}"
            self.setToolTip(tooltip_text)
        else:
            self.setToolTip("")

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
        urls = event.mimeData().urls()
        for url in urls:
            path = url.toLocalFile()
            if os.path.exists(path):
                self.add_file_row(path)
        event.acceptProposedAction()

    def add_file_row(self, input_path: str, output_path: str = "", extra_args: str = ""):
        """添加一行数据"""
        row = self.rowCount()
        self.insertRow(row)

        item_input = QTableWidgetItem(input_path)
        item_input.setFlags(item_input.flags() | Qt.ItemIsEditable)
        item_input.setToolTip(input_path)

        item_output = QTableWidgetItem(output_path)
        item_output.setFlags(item_output.flags() | Qt.ItemIsEditable)
        item_output.setToolTip(output_path if output_path else "双击编辑输出路径")

        item_args = QTableWidgetItem(extra_args)
        item_args.setFlags(item_args.flags() | Qt.ItemIsEditable)
        item_args.setToolTip(extra_args if extra_args else "双击编辑附加参数")

        item_status = QTableWidgetItem("待执行")
        item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)

        self.setItem(row, 0, item_input)
        self.setItem(row, 1, item_output)
        self.setItem(row, 2, item_args)
        self.setItem(row, 3, item_status)

        # 如果输出路径为空，尝试自动生成
        if not output_path and os.path.isfile(input_path):
            self.item(row, 1).setText(default_output_path(input_path))

        return row

    def show_context_menu(self, position: QPoint):
        """右键菜单"""
        menu = QMenu(self)

        add_file_action = QAction("添加文件", self)
        add_file_action.triggered.connect(self.browse_input_file)
        menu.addAction(add_file_action)

        add_folder_action = QAction("添加文件夹", self)
        add_folder_action.triggered.connect(self.browse_input_folder)
        menu.addAction(add_folder_action)

        menu.addSeparator()

        remove_action = QAction("删除选中行", self)
        remove_action.triggered.connect(self.remove_selected_rows)
        menu.addAction(remove_action)

        clear_action = QAction("清空所有", self)
        clear_action.triggered.connect(self.clear_all_rows)
        menu.addAction(clear_action)

        menu.exec_(self.viewport().mapToGlobal(position))

    def browse_input_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "选择输入文件", "", "所有文件 (*)")
        for f in files:
            self.add_file_row(f)

    def browse_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输入文件夹")
        if folder:
            self.add_file_row(folder)

    def remove_selected_rows(self):
        rows = sorted(set(item.row() for item in self.selectedItems()), reverse=True)
        for row in rows:
            self.removeRow(row)
            if row in self.row_commands:
                del self.row_commands[row]

    def clear_all_rows(self):
        self.setRowCount(0)
        self.row_commands.clear()

    def set_row_command(self, row: int, cmd: str):
        """设置行的完整命令"""
        self.row_commands[row] = cmd

    def get_row_data(self, row: int) -> dict:
        """获取行数据"""
        return {
            'input': self.item(row, 0).text() if self.item(row, 0) else "",
            'output': self.item(row, 1).text() if self.item(row, 1) else "",
            'args': self.item(row, 2).text() if self.item(row, 2) else "",
            'status': self.item(row, 3).text() if self.item(row, 3) else "",
        }


class CommandToolPage(QWidget):
    """主页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CommandToolPage")
        self.executors: List[CommandExecutor] = []
        self.completed_count = 0
        self.cmd_tool_path = ""
        self.init_ui()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # ===== 命令行工具选择区域 =====
        tool_card = CardWidget(self)
        tool_layout = QVBoxLayout(tool_card)
        tool_layout.setContentsMargins(15, 15, 15, 15)

        tool_title = StrongBodyLabel("命令行工具配置", self)
        tool_layout.addWidget(tool_title)

        # 工具路径选择
        path_layout = QHBoxLayout()
        self.tool_path_edit = LineEdit(self)
        self.tool_path_edit.setPlaceholderText("请选择命令行工具 (如 ffmpeg.exe, python.exe 等)")
        self.tool_path_edit.setReadOnly(True)

        browse_btn = PushButton("浏览", self)
        browse_btn.setIcon(FIF.FOLDER)
        browse_btn.clicked.connect(self.browse_tool)

        help_btn = PushButton("获取帮助 (--help)", self)
        help_btn.setIcon(FIF.QUESTION)
        help_btn.clicked.connect(self.get_help)

        path_layout.addWidget(self.tool_path_edit, 1)
        path_layout.addWidget(browse_btn)
        path_layout.addWidget(help_btn)
        tool_layout.addLayout(path_layout)

        # 帮助信息显示
        self.help_text = TextEdit(self)
        self.help_text.setPlaceholderText(f"点击【获取帮助】按钮查看命令行工具使用方法...")
        self.help_text.setMaximumHeight(120)
        self.help_text.setReadOnly(True)
        tool_layout.addWidget(self.help_text)

        self.main_layout.addWidget(tool_card)

        # ===== 参数模板配置区域 =====
        template_card = CardWidget(self)
        template_layout = QVBoxLayout(template_card)
        template_layout.setContentsMargins(15, 15, 15, 15)

        template_title = StrongBodyLabel("命令模板配置", self)
        template_layout.addWidget(template_title)

        template_desc = BodyLabel(
            "使用 {input} 表示输入路径, {output} 表示输出路径, {args} 表示附加参数", 
            self
        )
        template_layout.addWidget(template_desc)

        template_input_layout = QHBoxLayout()
        self.template_edit = LineEdit(self)
        self.template_edit.setText('"{tool}" {args} "{input}" "{output}"')
        self.template_edit.setPlaceholderText('示例: "{tool}" -i "{input}" -o "{output}"')

        template_input_layout.addWidget(BodyLabel("模板:", self))
        template_input_layout.addWidget(self.template_edit, 1)
        template_layout.addLayout(template_input_layout)

        # 预设模板选择
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(BodyLabel("预设模板:", self))

        self.preset_combo = ComboBox(self)
        self.preset_combo.addItems([
            "自定义",
            "cmd.exe [输入] [输出]",
            "cmd.exe [输入]",
            "cmd.exe [其它参数] [输入] [输出]",
            "cmd.exe [输入] [其它参数] [输出]"
        ])
        self.preset_combo.currentTextChanged.connect(self.apply_preset)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addStretch()

        template_layout.addLayout(preset_layout)
        self.main_layout.addWidget(template_card)

        # ===== 文件列表区域 =====
        file_card = CardWidget(self)
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(15, 15, 15, 15)

        file_title_layout = QHBoxLayout()
        file_title = StrongBodyLabel("任务列表 (支持拖拽文件/文件夹到表格)", self)
        file_title_layout.addWidget(file_title)
        file_title_layout.addStretch()

        add_file_btn = PushButton("添加文件", self)
        add_file_btn.setIcon(FIF.ADD)
        add_file_btn.clicked.connect(self.add_files)
        file_title_layout.addWidget(add_file_btn)

        add_folder_btn = PushButton("添加文件夹", self)
        add_folder_btn.setIcon(FIF.FOLDER_ADD)
        add_folder_btn.clicked.connect(self.add_folder)
        file_title_layout.addWidget(add_folder_btn)

        clear_btn = PushButton("清空", self)
        clear_btn.setIcon(FIF.DELETE)
        clear_btn.clicked.connect(self.clear_tasks)
        file_title_layout.addWidget(clear_btn)

        file_layout.addLayout(file_title_layout)

        self.task_table = DraggableTableWidget(self)
        self.task_table.itemChanged.connect(self.update_row_commands)
        file_layout.addWidget(self.task_table)

        # 批量输出目录
        output_dir_layout = QHBoxLayout()
        output_dir_layout.addWidget(BodyLabel("批量输出目录:", self))
        self.output_dir_edit = LineEdit(self)
        self.output_dir_edit.setPlaceholderText("可选: 设置统一的输出目录")

        out_browse_btn = PushButton("浏览", self)
        out_browse_btn.setIcon(FIF.FOLDER)
        out_browse_btn.clicked.connect(self.browse_output_dir)

        output_dir_layout.addWidget(self.output_dir_edit, 1)
        output_dir_layout.addWidget(out_browse_btn)
        file_layout.addLayout(output_dir_layout)

        self.main_layout.addWidget(file_card, 1)

        # ===== 执行控制区域 =====
        control_layout = QHBoxLayout()
        control_layout.addStretch()

        self.stop_btn = PushButton("停止", self)
        self.stop_btn.setIcon(FIF.PAUSE)
        self.stop_btn.clicked.connect(self.stop_all)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        self.run_btn = PrimaryPushButton("开始执行", self)
        self.run_btn.setIcon(FIF.PLAY)
        self.run_btn.clicked.connect(self.start_execution)
        control_layout.addWidget(self.run_btn)

        self.main_layout.addLayout(control_layout)

        # ===== 日志区域 =====
        log_card = CardWidget(self)
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(15, 15, 15, 15)

        log_title = StrongBodyLabel("执行日志", self)
        log_layout.addWidget(log_title)

        self.log_text = TextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.setPlaceholderText("执行日志将显示在这里...")
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        self.main_layout.addWidget(log_card)

    def apply_preset(self, text: str):
        """应用预设模板"""
        tool = self.cmd_tool_path or "{tool}"
        if text == "cmd.exe [输入] [输出]":
            self.template_edit.setText(f'"{tool}" "{{input}}" "{{output}}"')
        elif text == "cmd.exe [输入]":
            self.template_edit.setText(f'"{tool}" "{{input}}"')
        elif text == "cmd.exe [其它参数] [输入] [输出]":
            self.template_edit.setText(f'"{tool}" {{args}} "{{input}}" "{{output}}"')
        elif text == "cmd.exe [输入] [其它参数] [输出]":
            self.template_edit.setText(f'"{tool}" "{{input}}" {{args}} "{{output}}"')

    def browse_tool(self):
        """选择命令行工具"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择命令行工具", "", 
            "可执行文件 (*.exe);;所有文件 (*)"
        )
        if file_path:
            self.cmd_tool_path = file_path
            self.tool_path_edit.setText(file_path)
            # 更新模板中的工具路径
            self.update_template_tool_path()

    def update_template_tool_path(self):
        """更新模板中的工具路径"""
        template = self.template_edit.text()
        # 简单替换 {tool} 占位符
        if "{tool}" in template and self.cmd_tool_path:
            # 保留用户其他修改
            pass

    def get_help(self):
        """获取命令行工具帮助信息"""
        if not self.cmd_tool_path or not os.path.exists(self.cmd_tool_path):
            InfoBar.error(
                title="错误",
                content="请先选择有效的命令行工具",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        self.help_text.setPlainText("正在获取帮助信息，请稍候...")

        try:
            self.help_text.setPlainText(get_tool_help(self.cmd_tool_path))
        except Exception as e:
            self.help_text.setPlainText(f"获取帮助失败: {str(e)}")

    def add_files(self):
        """添加文件到列表"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择输入文件", "", "所有文件 (*)")
        for f in files:
            self.task_table.add_file_row(f)
        self.update_row_commands()

    def add_folder(self):
        """添加文件夹到列表"""
        folder = QFileDialog.getExistingDirectory(self, "选择输入文件夹")
        if folder:
            self.task_table.add_file_row(folder)
            self.update_row_commands()

    def clear_tasks(self):
        """清空任务"""
        self.task_table.clear_all_rows()

    def browse_output_dir(self):
        """选择批量输出目录"""
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if folder:
            self.output_dir_edit.setText(folder)
            self.update_output_paths()

    def update_output_paths(self):
        """根据输出目录更新所有行的输出路径"""
        out_dir = self.output_dir_edit.text()
        if not out_dir:
            return

        for row in range(self.task_table.rowCount()):
            input_path = self.task_table.item(row, 0).text()
            if input_path:
                output_path = output_path_in_directory(input_path, out_dir)
                self.task_table.item(row, 1).setText(output_path)

        self.update_row_commands()

    def build_command(self, tool: str, input_path: str, output_path: str, args: str) -> str:
        """构建命令"""
        return build_command(self.template_edit.text(), tool, input_path, output_path, args)

    def update_row_commands(self):
        """更新所有行的完整命令显示"""
        tool = self.cmd_tool_path or "{tool}"

        for row in range(self.task_table.rowCount()):
            data = self.task_table.get_row_data(row)
            cmd = self.build_command(
                tool,
                data['input'],
                data['output'],
                data['args']
            )
            self.task_table.set_row_command(row, cmd)

    def start_execution(self):
        """开始执行"""
        if not self.cmd_tool_path or not os.path.exists(self.cmd_tool_path):
            InfoBar.error(
                title="错误",
                content="请先选择有效的命令行工具",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        if self.task_table.rowCount() == 0:
            InfoBar.warning(
                title="提示",
                content="请先添加任务",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.log_text.clear()
        self.executors.clear()
        self.completed_count = 0

        # 更新所有命令
        self.update_row_commands()

        for row in range(self.task_table.rowCount()):
            data = self.task_table.get_row_data(row)

            if not data['input'] or not os.path.exists(data['input']):
                self.task_table.item(row, 3).setText("输入无效")
                continue

            # 构建命令
            cmd = self.build_command(
                self.cmd_tool_path,
                data['input'],
                data['output'],
                data['args']
            )

            self.task_table.item(row, 3).setText("执行中...")
            self.task_table.set_row_command(row, cmd)

            # 确保输出目录存在
            try:
                ensure_output_directory(data['output'])
            except OSError as exc:
                self.task_table.item(row, 3).setText(f"输出目录错误: {exc}")
                continue

            # 创建工作目录
            cwd = os.path.dirname(self.cmd_tool_path)

            executor = CommandExecutor(row, cmd, cwd)
            executor.output.connect(self.on_executor_output)
            executor.finished.connect(self.on_executor_finished)
            self.executors.append(executor)
            executor.start()

        if not self.executors:
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def on_executor_output(self, row: int, text: str):
        """接收执行输出"""
        self.log_text.append(f"[行{row+1}] {text.strip()}")

    def on_executor_finished(self, row: int, status: str, message: str):
        """执行完成回调"""
        self.task_table.item(row, 3).setText(status)
        self.completed_count += 1

        if self.completed_count >= len(self.executors):
            self.run_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

            success_count = sum(
                1 for r in range(self.task_table.rowCount())
                if self.task_table.item(r, 3) and "成功" in self.task_table.item(r, 3).text()
            )

            InfoBar.success(
                title="执行完成",
                content=f"任务执行结束，成功: {success_count} 个",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def stop_all(self):
        """停止所有执行"""
        for executor in self.executors:
            executor.stop()

        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        InfoBar.info(
            title="已停止",
            content="所有任务已停止",
            parent=self,
            position=InfoBarPosition.TOP
        )

    def closeEvent(self, event):
        """关闭时停止所有线程"""
        self.stop_all()
        for executor in self.executors:
            executor.wait(1000)
        event.accept()

