#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Demo 插件 1: 独立计数器。"""

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from ApplicationFramework import ApplicationPlugin, PluginInfo


class DemoCounterPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.count = 0
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = StrongBodyLabel("Demo 计数器插件", self)
        layout.addWidget(title)

        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        self.count_label = BodyLabel("当前计数: 0", card)
        card_layout.addWidget(self.count_label)

        button_layout = QHBoxLayout()
        increase_btn = PrimaryPushButton("增加", card)
        increase_btn.setIcon(FIF.ADD)
        increase_btn.clicked.connect(self.increase)

        reset_btn = PushButton("重置", card)
        reset_btn.setIcon(FIF.DELETE)
        reset_btn.clicked.connect(self.reset)

        button_layout.addWidget(increase_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch(1)
        card_layout.addLayout(button_layout)

        layout.addWidget(card)
        layout.addStretch(1)

    def increase(self):
        self.count += 1
        self.count_label.setText(f"当前计数: {self.count}")

    def reset(self):
        self.count = 0
        self.count_label.setText("当前计数: 0")


class DemoCounterPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="demo_counter",
        name="Demo 计数器",
        description="用于测试插件加载、卸载和页面状态隔离",
        version="1.0.0",
        icon=FIF.ADD,
    )

    def create_widget(self, parent=None):
        return DemoCounterPage(parent)


def create_plugin():
    return DemoCounterPlugin()
