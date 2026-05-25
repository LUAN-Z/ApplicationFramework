#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JSON 文件查看器插件入口。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

try:
    from .ui import JsonViewerPage
except ImportError:
    from ui import JsonViewerPage


class JsonViewerPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="json_viewer",
        name="JSON 查看器",
        description="读取、浏览和搜索 JSON 文件",
        version="1.0.0",
        icon=FIF.DOCUMENT,
    )

    def create_widget(self, parent=None):
        return JsonViewerPage(parent)


def create_plugin():
    return JsonViewerPlugin()
