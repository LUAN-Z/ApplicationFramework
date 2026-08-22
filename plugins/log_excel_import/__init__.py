#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Log 导入 Excel 插件入口。"""

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

from .ui import LogExcelImportPage


class LogExcelImportPlugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id="log_excel_import",
        name="Log 导入 Excel",
        description="批量排序测试 log TXT，并按关键字分 sheet 导入 Excel，自动生成 log汇总",
        version="1.0.0",
        icon=FIF.DOWNLOAD,
    )

    def create_widget(self, parent=None):
        return LogExcelImportPage(parent)


def create_plugin():
    return LogExcelImportPlugin()
