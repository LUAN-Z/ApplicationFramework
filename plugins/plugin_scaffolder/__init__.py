#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插件脚手架入口。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

from .ui import PluginScaffolderPage


class PluginScaffolderPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="plugin_scaffolder",
        name="插件脚手架",
        description="快速创建新插件目录和标准模板文件",
        version="1.0.0",
        icon=FIF.CODE,
    )

    def create_widget(self, parent=None):
        return PluginScaffolderPage(parent)


def create_plugin():
    return PluginScaffolderPlugin()
