#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""番茄时钟插件入口。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

from .ui import PomodoroPage


class PomodoroPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="pomodoro",
        name="番茄时钟",
        description="番茄工作法计时器：25 分钟专注 + 短休息 + 长休息",
        version="1.0.0",
        icon=FIF.STOP_WATCH,
    )

    def create_widget(self, parent=None):
        return PomodoroPage(parent)


def create_plugin():
    return PomodoroPlugin()
