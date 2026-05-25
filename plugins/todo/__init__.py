#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Todo 工具插件入口（参考 Microsoft To Do 的三栏式体验）。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

try:
    from .ui import TodoPage
except ImportError:
    from ui import TodoPage


class TodoPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="todo",
        name="任务",
        description="多列表 / 步骤 / 备注 / 计划日期，仿 Microsoft To Do",
        version="1.0.0",
        icon=FIF.CHECKBOX,
    )

    def create_widget(self, parent=None):
        return TodoPage(parent)


def create_plugin():
    return TodoPlugin()