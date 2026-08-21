#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用框架 - PyQt5 + QFluentWidgets

插件约定:
1. 插件模块提供 create_plugin() -> ApplicationPlugin
2. ApplicationPlugin.create_widget(parent) 返回一个 QWidget 页面
3. 每个插件页面独立创建、独立销毁，互不共享生命周期

最小插件示例:

    from ApplicationFramework import ApplicationPlugin, PluginInfo
    from qfluentwidgets import FluentIcon as FIF
    from my_page import MyPage

    class MyPlugin(ApplicationPlugin):
        info = PluginInfo(
            plugin_id="my_plugin",
            name="我的插件",
            description="示例插件",
            icon=FIF.APPLICATION,
        )

        def create_widget(self, parent=None):
            return MyPage(parent)

    def create_plugin():
        return MyPlugin()
"""

import importlib
import json
import os
import sys
import traceback
import weakref
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Type

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ColorDialog,
    FluentWindow,
    EditableComboBox,
    InfoBar,
    InfoBarPosition,
    NavigationItemHeader,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    Theme,
    TransparentToolButton,
    qconfig,
    setTheme,
    setThemeColor,
    themeColor,
    toggleTheme,
)
from qfluentwidgets import FluentIcon as FIF

from customWidget import InfoBarWithButton, MessageConfirmBox
from Utils import WindowsScaleFactorSetting

if __name__ == "__main__":
    sys.modules.setdefault("ApplicationFramework", sys.modules[__name__])


APP_STATE_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "ApplicationFramework"
CRASH_LOG_PATH = APP_STATE_DIR / "crash.log"
APP_VERSION = "1.0.0"
BUILTIN_PLUGIN_MODULES = [
    "plugins.cmd_executor",
    "plugins.config_viewer",
    "plugins.file_replacer",
    "plugins.json_viewer",
    "plugins.log_excel_import",
    "plugins.plugin_scaffolder",
    "plugins.pomodoro",
    "plugins.time_log",
    "plugins.todo",
]


def _write_crash_log(title: str, detail: str = "") -> None:
    try:
        APP_STATE_DIR.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(f"[{datetime.now().isoformat(timespec='seconds')}] {title}\n")
            if detail:
                file.write(detail.rstrip() + "\n")
            file.write("\n")
    except Exception:
        pass


def _install_exception_hook() -> None:
    def handle_exception(exc_type, exc_value, exc_traceback):
        detail = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        _write_crash_log("Unhandled exception", detail)
        traceback.print_exception(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def connect_theme_changed(callback) -> None:
    callback_ref = weakref.WeakMethod(callback) if hasattr(callback, "__self__") else None

    def safe_callback(*args, **kwargs):
        try:
            target = callback_ref() if callback_ref is not None else callback
            if target is None:
                return
            target()
        except Exception:
            _write_crash_log(
                f"Theme callback failed: {callback!r}",
                traceback.format_exc(),
            )

    qconfig.themeChanged.connect(safe_callback)


@dataclass(frozen=True)
class PluginInfo:
    """插件元信息，用于导航、插件管理页和唯一标识。"""

    plugin_id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    icon: FIF = FIF.APPLICATION


class ApplicationPlugin:
    """插件基类。

    插件只需要负责创建自己的页面；框架负责加载、卸载和导航。
    """

    info = PluginInfo(
        plugin_id="application_plugin",
        name="应用插件",
        description="未命名插件",
    )

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        raise NotImplementedError

    def on_load(self, framework: "ApplicationFramework") -> None:
        """插件页面加入框架后调用。"""

    def on_unload(self) -> None:
        """插件卸载前调用，可在这里停止线程、释放资源。"""


class PagePlugin(ApplicationPlugin):
    """把已有 QWidget 页面类包装成插件。

    这让已有 QWidget 页面类可以直接接入框架。
    """

    def __init__(self, info: PluginInfo, page_class: Type[QWidget]):
        self.info = info
        self.page_class = page_class

    def create_widget(self, parent: Optional[QWidget] = None) -> QWidget:
        return self.page_class(parent)


@dataclass
class LoadedPlugin:
    plugin: ApplicationPlugin
    widget: QWidget


class AboutPage(ScrollArea):
    """关于页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AboutPage")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QScrollArea { background: transparent; border: 0; }")

        self.container = QWidget(self)
        self.container.setStyleSheet("QWidget { background: transparent; }")
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("关于", self))
        layout.addWidget(BodyLabel(f"软件版本: {APP_VERSION}", self))
        layout.addWidget(BodyLabel("主要功能", self))

        features = BodyLabel(
            "插件管理\n"
            "插件分组\n"
            "加载 / 卸载插件\n"
            "一键全部加载 / 卸载\n"
            "主题切换与主题色\n"
            "内置插件随主程序一起编译",
            self,
        )
        features.setWordWrap(True)
        layout.addWidget(features)
        layout.addStretch(1)

        self.setWidget(self.container)


class PluginManager:
    """负责插件实例的注册、加载和卸载。"""

    def __init__(self, framework: "ApplicationFramework"):
        self.framework = framework
        self.available_plugins: Dict[str, ApplicationPlugin] = {}
        self.loaded_plugins: Dict[str, LoadedPlugin] = {}

    def register(self, plugin: ApplicationPlugin) -> None:
        info = plugin.info
        if not info.plugin_id:
            raise ValueError("插件 plugin_id 不能为空")
        if info.plugin_id in self.available_plugins:
            raise ValueError(f"插件 ID 重复: {info.plugin_id}")
        self.available_plugins[info.plugin_id] = plugin

    def unregister(self, plugin_id: str) -> None:
        self.unload(plugin_id)
        self.available_plugins.pop(plugin_id, None)

    def discover_builtin_plugins(self, module_names: Iterable[str]) -> list:
        """从内置模块列表发现插件。"""

        errors = []
        for module_name in module_names:
            try:
                plugin = self._load_plugin_from_module(module_name)
                self.register(plugin)
            except Exception as exc:
                errors.append((module_name, exc))
        return errors

    def load(self, plugin_id: str, sync_navigation: bool = True) -> QWidget:
        if plugin_id in self.loaded_plugins:
            return self.loaded_plugins[plugin_id].widget

        plugin = self.available_plugins[plugin_id]
        widget = plugin.create_widget(self.framework)
        widget.setObjectName(plugin.info.plugin_id)

        self.framework.add_plugin_widget(plugin, widget)
        plugin.on_load(self.framework)

        self.loaded_plugins[plugin_id] = LoadedPlugin(plugin=plugin, widget=widget)
        if sync_navigation:
            self.framework.request_plugin_navigation_sync()
        return widget

    def unload(self, plugin_id: str, sync_navigation: bool = True) -> None:
        loaded = self.loaded_plugins.pop(plugin_id, None)
        if not loaded:
            return

        loaded.plugin.on_unload()
        loaded.widget.close()
        self.framework.remove_plugin_widget(loaded.widget)
        loaded.widget.deleteLater()
        if sync_navigation:
            self.framework.request_plugin_navigation_sync()

    def is_loaded(self, plugin_id: str) -> bool:
        return plugin_id in self.loaded_plugins

    def _load_plugin_from_module(self, module_name: str) -> ApplicationPlugin:
        module = importlib.import_module(module_name)
        factory = getattr(module, "create_plugin", None)
        if not callable(factory):
            raise AttributeError(f"插件缺少 create_plugin(): {module_name}")

        plugin = factory()
        if not isinstance(plugin, ApplicationPlugin):
            raise TypeError(
                f"create_plugin() 必须返回 ApplicationPlugin 实例: {module_name}"
            )
        return plugin


class PluginCenterPage(ScrollArea):
    """插件管理页，负责显示已注册插件并触发加载/卸载。"""

    def __init__(self, framework: "ApplicationFramework", parent=None):
        super().__init__(parent)
        self.framework = framework
        self.setObjectName("PluginCenterPage")
        self.setWidgetResizable(True)
        # ScrollArea 自身去掉边框,让 FluentWindow 的整体背景透出来
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: 0; }"
        )

        self.container = QWidget(self)
        self.container.setObjectName("PluginCenterContainer")
        # 内层容器透明,避免在深色主题下露出默认浅色底
        self.container.setStyleSheet(
            "QWidget#PluginCenterContainer { background: transparent; }"
        )
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(12)
        self.setWidget(self.container)

        self.refresh()

    def refresh(self) -> None:
        self._clear_layout(self.layout)

        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 0)
        title_bar.setSpacing(8)
        title_bar.addWidget(StrongBodyLabel("插件管理", self))
        title_bar.addStretch(1)

        self.group_manage_combo = EditableComboBox(self)
        self.group_manage_combo.setPlaceholderText("新分组")
        self.group_manage_combo.setFixedWidth(160)
        self._reload_group_manage_options()

        add_group_btn = TransparentToolButton(FIF.ADD, self)
        add_group_btn.setToolTip("添加分组")
        add_group_btn.clicked.connect(self._add_group)

        delete_group_btn = TransparentToolButton(FIF.DELETE, self)
        delete_group_btn.setToolTip("删除分组")
        delete_group_btn.clicked.connect(self._delete_group)

        load_all_btn = TransparentToolButton(FIF.PLAY, self)
        load_all_btn.setToolTip("全部加载")
        load_all_btn.clicked.connect(self._load_all_plugins)

        unload_all_btn = TransparentToolButton(FIF.CLOSE, self)
        unload_all_btn.setToolTip("全部卸载")
        unload_all_btn.clicked.connect(self._unload_all_plugins)

        title_bar.addWidget(self.group_manage_combo)
        title_bar.addWidget(add_group_btn)
        title_bar.addWidget(delete_group_btn)
        title_bar.addSpacing(6)
        title_bar.addWidget(load_all_btn)
        title_bar.addWidget(unload_all_btn)
        self.layout.addLayout(title_bar)

        ordered_groups, grouped_plugins = self._grouped_plugins()

        for group in ordered_groups:
            header = StrongBodyLabel(group, self)
            self.layout.addWidget(header)
            for plugin in sorted(
                grouped_plugins[group], key=lambda item: item.info.name.lower()
            ):
                self.layout.addWidget(self._create_plugin_card(plugin))

        self.layout.addStretch(1)

    def _grouped_plugins(self) -> tuple[list[str], Dict[str, list[ApplicationPlugin]]]:
        grouped_plugins: Dict[str, list[ApplicationPlugin]] = {}
        for plugin in self.framework.plugin_manager.available_plugins.values():
            group = self.framework.plugin_group_by_id.get(plugin.info.plugin_id, "工具")
            grouped_plugins.setdefault(group, []).append(plugin)

        ordered_groups = self.framework._ordered_groups(grouped_plugins.keys())
        return ordered_groups, grouped_plugins

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)

    def _create_plugin_card(self, plugin: ApplicationPlugin) -> CardWidget:
        info = plugin.info
        is_loaded = self.framework.plugin_manager.is_loaded(info.plugin_id)
        card = CardWidget(self)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(10)

        text_layout = QVBoxLayout()
        name_label = StrongBodyLabel(f"{info.name}  v{info.version}", card)
        status = "已加载" if is_loaded else "未加载"
        desc_label = BodyLabel(
            f"{info.description or info.plugin_id}    状态: {status}", card
        )
        text_layout.addWidget(name_label)
        text_layout.addWidget(desc_label)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        group_combo = EditableComboBox(card)
        self._fill_group_combo(group_combo)
        group_combo.setCurrentText(self.framework.plugin_group_by_id.get(info.plugin_id, "工具"))
        group_combo.setFixedWidth(140)
        group_combo.setToolTip("插件分组")
        group_combo.currentTextChanged.connect(
            lambda text, pid=info.plugin_id: self._change_plugin_group(pid, text)
        )
        right_layout.addWidget(group_combo)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        load_btn = PrimaryPushButton("加载", card)
        load_btn.setIcon(FIF.ADD)
        load_btn.clicked.connect(lambda _, pid=info.plugin_id: self._load_plugin(pid))
        load_btn.setEnabled(not is_loaded)

        unload_btn = PushButton("卸载", card)
        unload_btn.setIcon(FIF.DELETE)
        unload_btn.clicked.connect(
            lambda _, pid=info.plugin_id: self._unload_plugin(pid)
        )
        unload_btn.setEnabled(is_loaded)

        jump_btn = PushButton("跳转", card)
        jump_btn.setIcon(FIF.RIGHT_ARROW)
        jump_btn.clicked.connect(
            lambda _, pid=info.plugin_id: self._jump_to_plugin(pid)
        )
        jump_btn.setEnabled(is_loaded)

        action_row.addWidget(load_btn)
        action_row.addWidget(unload_btn)
        action_row.addWidget(jump_btn)

        card_layout.addLayout(text_layout, 1)
        right_layout.addLayout(action_row)
        card_layout.addLayout(right_layout)
        return card

    def _fill_group_combo(self, combo: EditableComboBox) -> None:
        combo.clear()
        combo.addItems(self.framework.plugin_group_order or ["工具"])

    def _reload_group_manage_options(self) -> None:
        current = getattr(self, "group_manage_combo", None)
        selected = current.currentText().strip() if current else ""
        self.group_manage_combo.clear()
        self.group_manage_combo.addItems(self.framework.plugin_group_order or ["工具"])
        if selected:
            self.group_manage_combo.setCurrentText(selected)

    def _add_group(self) -> None:
        title = self.group_manage_combo.currentText().strip()
        if not title:
            title, ok = QInputDialog.getText(self, "添加分组", "输入分组名称")
            if not ok:
                return
            title = title.strip()
        if not title:
            return

        if title not in self.framework.plugin_group_order:
            self.framework.plugin_group_order.append(title)
            self.framework._save_plugin_groups()
        self.refresh()

    def _delete_group(self) -> None:
        title = self.group_manage_combo.currentText().strip()
        if not title:
            return
        if title == "工具" and len(self.framework.plugin_group_order) <= 1:
            return
        if not self.framework.confirm_action(
            "确认删除分组",
            f"确定要删除分组“{title}”吗？该组中的插件会移动到“工具”。",
        ):
            return

        for plugin_id, group_title in list(self.framework.plugin_group_by_id.items()):
            if group_title == title:
                self.framework.plugin_group_by_id[plugin_id] = "工具"

        if title in self.framework.plugin_group_order and title != "工具":
            self.framework.plugin_group_order.remove(title)
        if "工具" not in self.framework.plugin_group_order:
            self.framework.plugin_group_order.insert(0, "工具")

        self.framework._save_plugin_groups()
        self.framework.request_plugin_navigation_sync()
        self.refresh()

    def _change_plugin_group(self, plugin_id: str, group_title: str) -> None:
        group_title = group_title.strip() or "工具"
        if self.framework.plugin_group_by_id.get(plugin_id) == group_title:
            return

        self.framework.plugin_group_by_id[plugin_id] = group_title
        if group_title not in self.framework.plugin_group_order:
            self.framework.plugin_group_order.append(group_title)
        self.framework._save_plugin_groups()
        self.framework.request_plugin_navigation_sync()
        self.refresh()

    def _load_plugin(self, plugin_id: str) -> None:
        try:
            self.framework.plugin_manager.load(plugin_id)
            self.framework._save_loaded_plugins()
            self.refresh()
            InfoBar.success(
                title="已加载",
                content=self.framework.plugin_manager.available_plugins[
                    plugin_id
                ].info.name,
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=2000,
            )
        except Exception as exc:
            InfoBar.error(
                title="加载失败",
                content=str(exc),
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=4000,
            )

    def _load_all_plugins(self) -> None:
        loaded_count = 0
        errors = []
        for plugin in sorted(
            self.framework.plugin_manager.available_plugins.values(),
            key=lambda item: (
                self.framework._plugin_group_sort_key(
                    self.framework.plugin_group_by_id.get(item.info.plugin_id, "工具")
                ),
                item.info.name.lower(),
                item.info.plugin_id,
            ),
        ):
            plugin_id = plugin.info.plugin_id
            if self.framework.plugin_manager.is_loaded(plugin_id):
                continue
            try:
                self.framework.plugin_manager.load(plugin_id, sync_navigation=False)
                loaded_count += 1
            except Exception as exc:
                errors.append(f"{plugin.info.name}: {exc}")

        self.framework._save_loaded_plugins()
        self.refresh()
        if loaded_count:
            InfoBar.success(
                title="已加载全部",
                content=f"已加载 {loaded_count} 个插件",
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=2500,
            )
        if errors:
            InfoBar.error(
                title="部分插件加载失败",
                content="; ".join(errors[-3:]),
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _unload_all_plugins(self) -> None:
        loaded_ids = list(self.framework.plugin_manager.loaded_plugins.keys())
        if not loaded_ids:
            return
        if not self.framework.confirm_action(
            "确认全部卸载",
            f"确定要卸载当前已加载的 {len(loaded_ids)} 个插件吗？",
        ):
            return

        errors = []
        for plugin_id in loaded_ids:
            try:
                self.framework.plugin_manager.unload(plugin_id, sync_navigation=False)
            except Exception as exc:
                errors.append(f"{self.framework.plugin_manager.available_plugins[plugin_id].info.name}: {exc}")

        self.framework._save_loaded_plugins()
        self.framework.navigationInterface.setCurrentItem(self.framework.plugin_center_page.objectName())
        self.refresh()
        if errors:
            InfoBar.error(
                title="部分插件卸载失败",
                content="; ".join(errors[-3:]),
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
        else:
            InfoBar.success(
                title="已全部卸载",
                content="已卸载当前全部插件",
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=2500,
            )

    def _jump_to_plugin(self, plugin_id: str) -> None:
        loaded = self.framework.plugin_manager.loaded_plugins.get(plugin_id)
        if not loaded:
            self.refresh()
            return

        self.framework.navigate_to_widget(loaded.widget)

    def _unload_plugin(self, plugin_id: str) -> None:
        plugin_name = self.framework.plugin_manager.available_plugins[
            plugin_id
        ].info.name
        if not self.framework.confirm_action(
            "确认卸载",
            f"确定要卸载插件“{plugin_name}”吗？",
        ):
            return

        try:
            self.framework.plugin_manager.unload(plugin_id)
            self.framework._save_loaded_plugins()
            self.framework.navigationInterface.setCurrentItem(self.objectName())
            self.refresh()
        except Exception as exc:
            InfoBar.error(
                title="卸载失败",
                content=str(exc),
                parent=self.framework,
                position=InfoBarPosition.TOP,
                duration=4000,
            )


class ApplicationFramework(FluentWindow):
    """插件式应用主框架。

    页面插件通过 addSubInterface 接入；页面创建和生命周期交给插件管理器。
    """

    def __init__(
        self, plugin_dir: str = "plugins", plugin_config: str = "config/plugins.json"
    ):
        super().__init__()
        self.setWindowTitle(f"应用框架 {APP_VERSION}")
        self.resize(1200, 900)

        self.app_dir = Path(__file__).resolve().parent
        self.user_config_dir = APP_STATE_DIR
        self.plugin_manager = PluginManager(self)
        self.default_plugin_config_path = self._resolve_app_path(plugin_config)
        self.plugin_config_path = self.user_config_dir / plugin_config
        self.legacy_plugin_config_path = self.user_config_dir / Path(plugin_config).name
        self.plugin_load_errors: list = []
        self.plugin_group_by_id: Dict[str, str] = {}
        self.plugin_group_order: list[str] = []
        self._plugin_navigation_header_keys: list[str] = []
        self._plugin_navigation_sync_pending = False

        saved_config = self._read_plugin_config()
        self.open_screen_interface = saved_config.get("open_screen_interface", "")

        # 默认主题色 / 主题模式;真正的值会从配置覆盖
        self.theme_color = "#0078D4"
        self.theme_mode = ""
        setThemeColor(self.theme_color)

        self._load_builtin_plugins()
        self._load_plugin_groups(saved_config)

        # 应用从配置中读到的主题色 / 主题模式
        setThemeColor(self.theme_color)
        self._apply_saved_theme_mode()

        self.plugin_center_page = PluginCenterPage(self, self)
        self.addSubInterface(
            self.plugin_center_page,
            FIF.APPLICATION,
            "插件管理",
            NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FIF.SETTING,
            text="设置",
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )
        self.about_page = AboutPage(self)
        self.stackedWidget.addWidget(self.about_page)
        self.navigationInterface.addItem(
            routeKey=self.about_page.objectName(),
            icon=FIF.INFO,
            text="关于",
            onClick=lambda: self.switchTo(self.about_page),
            position=NavigationItemPosition.BOTTOM,
            parentRouteKey="settings",
        )
        self.navigationInterface.addItem(
            routeKey="theme",
            icon=FIF.CONSTRACT,
            text="切换主题",
            onClick=self._toggle_theme_and_save,
            selectable=False,
            tooltip="切换主题",
            position=NavigationItemPosition.BOTTOM,
            parentRouteKey="settings",
        )
        self.navigationInterface.addItem(
            routeKey="theme_color",
            icon=FIF.PALETTE,
            text="主题色",
            onClick=self._open_theme_color_dialog,
            selectable=False,
            tooltip="选择主题色",
            position=NavigationItemPosition.BOTTOM,
            parentRouteKey="settings",
        )

        self.navigationInterface.setExpandWidth(200)
        self._restore_loaded_plugins(saved_config)
        self.plugin_center_page.refresh()
        self._show_plugin_load_errors()

    # ── 主题持久化 ────────────────────────────────────────

    def _apply_saved_theme_mode(self) -> None:
        """根据 self.theme_mode 设置当前主题。空字符串表示沿用默认。"""
        mode = (self.theme_mode or "").lower()
        mapping = {
            "light": Theme.LIGHT,
            "dark": Theme.DARK,
            "auto": Theme.AUTO,
        }
        if mode in mapping:
            setTheme(mapping[mode])

    def _toggle_theme_and_save(self) -> None:
        """切换主题并把新模式持久化到 plugins.json。"""
        try:
            toggleTheme()
            try:
                new_mode = qconfig.theme.value
            except AttributeError:
                from qfluentwidgets import isDarkTheme
                new_mode = "dark" if isDarkTheme() else "light"
            self.theme_mode = new_mode
            self._save_theme_settings()
        except Exception:
            detail = traceback.format_exc()
            _write_crash_log("Theme switch failed", detail)
            InfoBar.error(
                title="主题切换失败",
                content=f"错误已写入 {CRASH_LOG_PATH}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _open_theme_color_dialog(self) -> None:
        """弹出 ColorDialog 选择主题色,确认后持久化并实时应用。"""
        try:
            current = QColor(self.theme_color)
        except Exception:
            current = themeColor()
        dlg = ColorDialog(current, "选择主题色", self)
        dlg.colorChanged.connect(self._on_theme_color_changed)
        dlg.exec()

    def _on_theme_color_changed(self, color: QColor) -> None:
        if not color.isValid():
            return
        try:
            self.theme_color = color.name()
            setThemeColor(self.theme_color)
            self._save_theme_settings()
        except Exception:
            detail = traceback.format_exc()
            _write_crash_log("Theme color change failed", detail)
            InfoBar.error(
                title="主题色保存失败",
                content=f"错误已写入 {CRASH_LOG_PATH}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _save_theme_settings(self) -> None:
        """把 theme_color / theme_mode 写回 plugins.json。"""
        existing = self._read_plugin_config()
        existing["theme_color"] = self.theme_color
        existing["theme_mode"] = self.theme_mode
        self.plugin_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_plugin_groups(self, data: Dict) -> None:
        available_ids = set(self.plugin_manager.available_plugins.keys())
        group_by_id: Dict[str, str] = {}
        group_order: list[str] = []

        groups = data.get("plugin_groups")
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue

                title = group.get("title", "工具")
                if not isinstance(title, str) or not title.strip():
                    title = "工具"
                title = title.strip()

                if title not in group_order:
                    group_order.append(title)

                plugins = group.get("plugins", [])
                if not isinstance(plugins, list):
                    continue

                for raw_plugin_id in plugins:
                    plugin_id = self._normalize_plugin_id(raw_plugin_id)
                    if plugin_id in available_ids:
                        group_by_id[plugin_id] = title

        for plugin_id in available_ids:
            group_by_id.setdefault(plugin_id, "工具")

        if "工具" not in group_order:
            group_order.insert(0, "工具")

        self.plugin_group_by_id = group_by_id
        self.plugin_group_order = group_order

    def _ordered_groups(self, groups: Iterable[str]) -> list[str]:
        group_set = set(groups)
        ordered = [group for group in self.plugin_group_order if group in group_set]
        for group in sorted(group_set):
            if group not in ordered:
                ordered.append(group)
        return ordered

    def _plugin_group_sort_key(self, group: str) -> tuple[int, str]:
        if group in self.plugin_group_order:
            return self.plugin_group_order.index(group), ""
        return len(self.plugin_group_order), group.lower()

    def _ordered_loaded_plugins(self) -> list[LoadedPlugin]:
        return sorted(
            self.plugin_manager.loaded_plugins.values(),
            key=lambda item: (
                self._plugin_group_sort_key(
                    self._plugin_navigation_group(item.plugin.info.plugin_id)
                ),
                item.plugin.info.name.lower(),
                item.plugin.info.plugin_id,
            ),
        )

    def _plugin_navigation_header_key(self, group: str) -> str:
        return f"plugin-group::{group}"

    def _restore_loaded_plugins(self, data: Dict) -> None:
        loaded_plugins = data.get("loaded_plugins")
        if not isinstance(loaded_plugins, list):
            target = self.open_screen_interface.strip() if isinstance(self.open_screen_interface, str) else ""
            loaded_plugins = [target] if target and target in self.plugin_manager.available_plugins else []

        restored = False
        for raw_plugin_id in loaded_plugins:
            plugin_id = self._normalize_plugin_id(raw_plugin_id)
            if not plugin_id or plugin_id not in self.plugin_manager.available_plugins:
                continue

            try:
                self.plugin_manager.load(plugin_id, sync_navigation=False)
                restored = True
            except Exception as exc:
                self.plugin_load_errors.append(f"{plugin_id}: {exc}")

        if restored:
            self.request_plugin_navigation_sync()
            self._save_loaded_plugins()

    def _save_plugin_groups(self) -> None:
        existing = self._read_plugin_config()
        grouped_plugins: Dict[str, list[str]] = {}
        for plugin_id in self.plugin_manager.available_plugins.keys():
            group = self.plugin_group_by_id.get(plugin_id, "工具")
            grouped_plugins.setdefault(group, []).append(plugin_id)

        group_order = list(self.plugin_group_order)
        for group in grouped_plugins:
            if group not in group_order:
                group_order.append(group)

        existing["plugin_groups"] = [
            {
                "title": group,
                "plugins": grouped_plugins.get(group, []),
            }
            for group in group_order
            if grouped_plugins.get(group)
        ]
        self.plugin_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _normalize_plugin_id(self, raw_plugin_id) -> str:
        if not isinstance(raw_plugin_id, str):
            return ""

        raw_plugin_id = raw_plugin_id.strip().replace("\\", "/")
        if not raw_plugin_id:
            return ""

        path = Path(raw_plugin_id)
        if path.name == "__init__.py":
            return path.parent.name
        if path.suffix == ".py":
            return path.stem
        return path.name

    def _resolve_app_path(self, path: str | Path) -> Path:
        path = Path(path)
        if path.is_absolute():
            return path
        return self.app_dir / path

    def _read_plugin_config(self) -> Dict:
        for config_path in (
            self.plugin_config_path,
            self.legacy_plugin_config_path,
            self.default_plugin_config_path,
        ):
            if not config_path.exists():
                continue

            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                _write_crash_log(
                    f"Failed to read config: {config_path}",
                    traceback.format_exc(),
                )
                continue

            return data if isinstance(data, dict) else {}

        return {}

    def add_plugin_widget(self, plugin: ApplicationPlugin, widget: QWidget) -> None:
        info = plugin.info
        self.addSubInterface(widget, info.icon, info.name, NavigationItemPosition.SCROLL)

    def _plugin_navigation_group(self, plugin_id: str) -> str:
        return self.plugin_group_by_id.get(plugin_id, "工具")

    def request_plugin_navigation_sync(self) -> None:
        if self._plugin_navigation_sync_pending:
            return

        self._plugin_navigation_sync_pending = True
        QTimer.singleShot(100, self.sync_plugin_navigation)

    def sync_plugin_navigation(self) -> None:
        self._plugin_navigation_sync_pending = False
        if not hasattr(self, "navigationInterface"):
            return

        current_widget = self.stackedWidget.currentWidget() if hasattr(self, "stackedWidget") else None
        current_route_key = current_widget.objectName() if current_widget else ""

        for header_key in self._plugin_navigation_header_keys:
            self.navigationInterface.removeWidget(header_key)
        self._plugin_navigation_header_keys.clear()

        for loaded in list(self.plugin_manager.loaded_plugins.values()):
            self.remove_plugin_widget(loaded.widget)

        grouped_plugins: Dict[str, list[LoadedPlugin]] = {}
        for loaded in self._ordered_loaded_plugins():
            group = self._plugin_navigation_group(loaded.plugin.info.plugin_id)
            grouped_plugins.setdefault(group, []).append(loaded)

        for group in self._ordered_groups(grouped_plugins.keys()):
            header_key = self._plugin_navigation_header_key(group)
            header = NavigationItemHeader(group, self.navigationInterface)
            self.navigationInterface.addWidget(
                header_key, header, position=NavigationItemPosition.SCROLL
            )
            self._plugin_navigation_header_keys.append(header_key)

            for loaded in grouped_plugins[group]:
                self.add_plugin_widget(loaded.plugin, loaded.widget)

        if current_route_key and current_route_key in self.plugin_manager.loaded_plugins:
            self.navigate_to_widget(current_widget)

    def _save_loaded_plugins(self) -> None:
        existing = self._read_plugin_config()
        existing["loaded_plugins"] = [
            loaded.plugin.info.plugin_id for loaded in self._ordered_loaded_plugins()
        ]
        self.plugin_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def remove_plugin_widget(self, widget: QWidget) -> None:
        route_key = widget.objectName()

        # qfluentwidgets 不同版本的移除 API 名称可能不同，这里兼容处理。
        if hasattr(self.navigationInterface, "removeWidget"):
            self.navigationInterface.removeWidget(route_key)
        elif hasattr(self.navigationInterface, "removeItem"):
            self.navigationInterface.removeItem(route_key)

        if hasattr(self, "stackedWidget"):
            self.stackedWidget.removeWidget(widget)

    def navigate_to_widget(self, widget: QWidget) -> None:
        if hasattr(self, "switchTo"):
            self.switchTo(widget)
        self.navigationInterface.setCurrentItem(widget.objectName())

    def center_on_current_screen(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return

        available_geometry = screen.availableGeometry()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(available_geometry.center())
        self.move(frame_geometry.topLeft())

    def center_on_startup_screen(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            return

        available_geometry = screen.availableGeometry()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(available_geometry.center())
        self.move(frame_geometry.topLeft())

    def confirm_action(self, title: str, content: str) -> bool:
        result = MessageConfirmBox(
            parent=self,
            title=title,
            content=content,
            show_cancel_btn=True,
        ).exec()
        return result

    def _load_builtin_plugins(self) -> None:
        errors = self.plugin_manager.discover_builtin_plugins(BUILTIN_PLUGIN_MODULES)
        self.plugin_load_errors = [f"{name}: {exc}" for name, exc in errors]

    def _show_plugin_load_errors(self) -> None:
        if self.plugin_load_errors:
            InfoBar.error(
                title="部分插件加载失败",
                content="; ".join(self.plugin_load_errors[-3:]),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _navigate_to_open_screen(self) -> None:
        """根据插件配置 open_screen_interface 跳转到对应界面。"""
        target = getattr(self, "open_screen_interface", "")

        if target and target in self.plugin_manager.available_plugins:
            loaded = self.plugin_manager.loaded_plugins.get(target)
            if loaded:
                self.navigate_to_widget(loaded.widget)
                return

        self.navigate_to_widget(self.plugin_center_page)

    def closeEvent(self, event) -> None:
        # 保存当前界面到配置，下次启动自动恢复
        try:
            current_widget = self.stackedWidget.currentWidget()
            if current_widget:
                self._save_open_screen_interface(current_widget.objectName())
        except Exception:
            pass

        try:
            self._save_loaded_plugins()
        except Exception:
            pass

        for plugin_id in list(self.plugin_manager.loaded_plugins.keys()):
            try:
                self.plugin_manager.unload(plugin_id, sync_navigation=False)
            except Exception:
                pass
        event.accept()

    def _save_open_screen_interface(self, interface_name: str) -> None:
        """将当前界面名称写入 plugins.json 的 open_screen_interface 字段。"""
        existing = self._read_plugin_config()
        existing["open_screen_interface"] = interface_name
        self.plugin_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> None:
    _install_exception_hook()
    WindowsScaleFactorSetting()
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)
    window = ApplicationFramework()
    window.center_on_startup_screen()
    window._navigate_to_open_screen()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
