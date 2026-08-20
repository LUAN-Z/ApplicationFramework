#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件替换插件入口。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

try:
    from .ui import FileReplacerPage
except ImportError:
    from ui import FileReplacerPage


class FileReplacerPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="file_replacer",
        name="文件字段替换",
        description="批量按关键字或行范围替换文件内容",
        version="1.0.0",
        icon=FIF.EDIT,
    )

    def create_widget(self, parent=None):
        return FileReplacerPage(parent)


def create_plugin():
    return FileReplacerPlugin()
