#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command executor plugin entry point."""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

from .ui import CommandToolPage


class CommandExecutorPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="command_executor",
        name="命令执行",
        description="批量配置并执行命令行工具",
        version="1.0.0",
        icon=FIF.COMMAND_PROMPT,
    )

    def create_widget(self, parent=None):
        return CommandToolPage(parent)


def create_plugin():
    return CommandExecutorPlugin()
