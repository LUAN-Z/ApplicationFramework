#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""时间日志插件入口 — 持久化的工作日志,支持标签 / 搜索 / 桶 / 导入导出。

注:plugin_id 仍为 "demo_notes" 以保持与 plugins.json 的兼容,
   显示名称已升级为「时间日志」。
"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

try:
    from .ui import TimeLogPage
except ImportError:
    from ui import TimeLogPage


class DemoNotesPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="demo_notes",
        name="时间日志",
        description="带时间戳与标签的工作日志,支持按日 / 周 / 标签筛选,导入导出",
        version="2.0.0",
        icon=FIF.HISTORY,
    )

    def create_widget(self, parent=None):
        return TimeLogPage(parent)


def create_plugin():
    return DemoNotesPlugin()