#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INI 配置文件查看器插件入口。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

from .ui import ConfigViewerPage


class ConfigViewerPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="config_viewer",
        name="配置查看器",
        description="读取、浏览和编辑 INI 配置文件",
        version="1.0.0",
        icon=FIF.SETTING,
    )

    def create_widget(self, parent=None):
        return ConfigViewerPage(parent)


def create_plugin():
    return ConfigViewerPlugin()
