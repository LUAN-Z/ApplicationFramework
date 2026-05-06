#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo 插件 2: 独立文本记录。"""

from datetime import datetime

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    CardWidget,
    FluentIcon as FIF,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TextEdit,
)

from ApplicationFramework import ApplicationPlugin, PluginInfo


class DemoNotesPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = StrongBodyLabel("Demo 记录插件", self)
        layout.addWidget(title)

        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        self.input_edit = LineEdit(card)
        self.input_edit.setPlaceholderText("输入一条测试记录")
        self.input_edit.returnPressed.connect(self.add_note)
        card_layout.addWidget(self.input_edit)

        button_layout = QHBoxLayout()
        add_btn = PrimaryPushButton("添加记录", card)
        add_btn.setIcon(FIF.ADD)
        add_btn.clicked.connect(self.add_note)

        clear_btn = PushButton("清空", card)
        clear_btn.setIcon(FIF.DELETE)
        clear_btn.clicked.connect(self.clear_notes)

        button_layout.addWidget(add_btn)
        button_layout.addWidget(clear_btn)
        button_layout.addStretch(1)
        card_layout.addLayout(button_layout)

        self.notes_edit = TextEdit(card)
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setPlaceholderText("记录会显示在这里...")
        card_layout.addWidget(self.notes_edit)

        layout.addWidget(card, 1)

    def add_note(self):
        text = self.input_edit.text().strip()
        if not text:
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.notes_edit.append(f"[{timestamp}] {text}")
        self.input_edit.clear()

    def clear_notes(self):
        self.notes_edit.clear()


class DemoNotesPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="demo_notes",
        name="Demo 记录",
        description="用于测试第二个独立插件页面",
        version="1.0.0",
        icon=FIF.APPLICATION,
    )

    def create_widget(self, parent=None):
        return DemoNotesPage(parent)


def create_plugin():
    return DemoNotesPlugin()
