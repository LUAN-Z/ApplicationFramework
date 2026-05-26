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

import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Type

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ColorDialog,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    Theme,
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

    def discover_from_directory(self, plugin_dir: Path) -> None:
        """从目录发现插件。

        支持两种布局:
        - plugins/foo.py
        - plugins/foo/__init__.py
        """

        if not plugin_dir.exists():
            return

        for path in self._iter_plugin_entries(plugin_dir):
            try:
                plugin = self._load_plugin_from_path(path)
                self.register(plugin)
            except Exception:
                traceback.print_exc()

    def register_from_path(self, path: Path) -> ApplicationPlugin:
        plugin_path = self.resolve_plugin_path(path)
        if not plugin_path.exists():
            raise FileNotFoundError(f"插件不存在: {path}")

        plugin = self._load_plugin_from_path(plugin_path)
        self.register(plugin)
        return plugin

    def resolve_plugin_path(self, path: Path) -> Path:
        plugin_path = path / "__init__.py" if path.is_dir() else path
        if plugin_path.suffix != ".py":
            raise ValueError("请选择 .py 插件文件，或包含 __init__.py 的插件目录")
        return plugin_path.resolve()

    def load(self, plugin_id: str) -> QWidget:
        if plugin_id in self.loaded_plugins:
            return self.loaded_plugins[plugin_id].widget

        plugin = self.available_plugins[plugin_id]
        widget = plugin.create_widget(self.framework)
        widget.setObjectName(plugin.info.plugin_id)

        self.framework.add_plugin_widget(plugin, widget)
        plugin.on_load(self.framework)

        self.loaded_plugins[plugin_id] = LoadedPlugin(plugin=plugin, widget=widget)
        return widget

    def unload(self, plugin_id: str) -> None:
        loaded = self.loaded_plugins.pop(plugin_id, None)
        if not loaded:
            return

        loaded.plugin.on_unload()
        loaded.widget.close()
        self.framework.remove_plugin_widget(loaded.widget)
        loaded.widget.deleteLater()

    def is_loaded(self, plugin_id: str) -> bool:
        return plugin_id in self.loaded_plugins

    def _iter_plugin_entries(self, plugin_dir: Path) -> Iterable[Path]:
        for file_path in plugin_dir.glob("*.py"):
            if self._is_plugin_entry(file_path):
                yield file_path
        for child in plugin_dir.iterdir():
            init_file = child / "__init__.py"
            if (
                child.is_dir()
                and init_file.exists()
                and self._is_plugin_entry(init_file)
            ):
                yield init_file

    def _is_plugin_entry(self, path: Path) -> bool:
        try:
            return "create_plugin" in path.read_text(encoding="utf-8")
        except Exception:
            return False

    def _load_plugin_from_path(self, path: Path) -> ApplicationPlugin:
        module_name = f"app_plugin_{abs(hash(path.resolve()))}_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载插件: {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        factory = getattr(module, "create_plugin", None)
        if not callable(factory):
            raise AttributeError(f"插件缺少 create_plugin(): {path}")

        plugin = factory()
        if not isinstance(plugin, ApplicationPlugin):
            raise TypeError(f"create_plugin() 必须返回 ApplicationPlugin 实例: {path}")
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

        title = StrongBodyLabel("插件管理", self)
        self.layout.addWidget(title)

        action_layout = QHBoxLayout()
        add_btn = PrimaryPushButton("添加插件", self)
        add_btn.setIcon(FIF.ADD)
        add_btn.clicked.connect(self.framework.add_plugin)
        action_layout.addWidget(add_btn)
        action_layout.addStretch(1)
        self.layout.addLayout(action_layout)

        for plugin in self.framework.plugin_manager.available_plugins.values():
            self.layout.addWidget(self._create_plugin_card(plugin))

        self.layout.addStretch(1)

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
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(12)

        text_layout = QVBoxLayout()
        name_label = StrongBodyLabel(f"{info.name}  v{info.version}", card)
        status = "已加载" if is_loaded else "未加载"
        desc_label = BodyLabel(
            f"{info.description or info.plugin_id}    状态: {status}", card
        )
        text_layout.addWidget(name_label)
        text_layout.addWidget(desc_label)

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

        remove_btn = PushButton("移除", card)
        remove_btn.setIcon(FIF.CLOSE)
        remove_btn.clicked.connect(
            lambda _, pid=info.plugin_id: self._remove_plugin(pid)
        )
        remove_btn.setEnabled(self.framework.is_user_plugin(info.plugin_id))

        card_layout.addLayout(text_layout, 1)
        card_layout.addWidget(load_btn)
        card_layout.addWidget(unload_btn)
        card_layout.addWidget(jump_btn)
        card_layout.addWidget(remove_btn)
        return card

    def _load_plugin(self, plugin_id: str) -> None:
        try:
            widget = self.framework.plugin_manager.load(plugin_id)
            self.framework.navigate_to_widget(widget)
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

    def _remove_plugin(self, plugin_id: str) -> None:
        plugin_name = self.framework.plugin_manager.available_plugins[
            plugin_id
        ].info.name
        if not self.framework.confirm_action(
            "确认移除",
            f"确定要移除插件“{plugin_name}”吗？移除后下次启动不会自动加载到插件管理。",
        ):
            return

        try:
            self.framework.remove_user_plugin(plugin_id)
            self.framework.navigationInterface.setCurrentItem(self.objectName())
            self.refresh()
        except Exception as exc:
            InfoBar.error(
                title="移除失败",
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
        self, plugin_dir: str = "plugins", plugin_config: str = "plugins.json"
    ):
        super().__init__()
        self.setWindowTitle("应用框架")
        self.resize(1200, 900)

        self.app_dir = Path(__file__).resolve().parent
        self.plugin_manager = PluginManager(self)
        self.plugin_dir = self._resolve_app_path(plugin_dir)
        self.plugin_config_path = self._resolve_app_path(plugin_config)
        self.user_plugin_paths: Dict[str, Path] = {}

        # 默认主题色 / 主题模式;真正的值会在 _load_user_plugins() 里从配置覆盖
        self.theme_color = "#0078D4"
        self.theme_mode = ""
        setThemeColor(self.theme_color)

        # self._register_builtin_plugins()
        self._load_user_plugins()

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
            routeKey="theme",
            icon=FIF.CONSTRACT,
            text="切换主题",
            onClick=self._toggle_theme_and_save,
            selectable=False,
            tooltip="切换主题",
            position=NavigationItemPosition.BOTTOM,
        )
        self.navigationInterface.addItem(
            routeKey="theme_color",
            icon=FIF.PALETTE,
            text="主题色",
            onClick=self._open_theme_color_dialog,
            selectable=False,
            tooltip="选择主题色",
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.setExpandWidth(200)
        self._load_startup_plugins()
        self.plugin_center_page.refresh()
        self._navigate_to_open_screen()

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
        toggleTheme()
        try:
            new_mode = qconfig.theme.value
        except AttributeError:
            from qfluentwidgets import isDarkTheme
            new_mode = "dark" if isDarkTheme() else "light"
        self.theme_mode = new_mode
        self._save_theme_settings()

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
        self.theme_color = color.name()
        setThemeColor(self.theme_color)
        self._save_theme_settings()

    def _save_theme_settings(self) -> None:
        """把 theme_color / theme_mode 写回 plugins.json。"""
        existing: Dict = {}
        if self.plugin_config_path.exists():
            try:
                existing = json.loads(
                    self.plugin_config_path.read_text(encoding="utf-8")
                )
            except Exception:
                existing = {}
        existing["theme_color"] = self.theme_color
        existing["theme_mode"] = self.theme_mode
        self.plugin_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _resolve_app_path(self, path: str | Path) -> Path:
        path = Path(path)
        if path.is_absolute():
            return path
        return self.app_dir / path

    def add_plugin_widget(self, plugin: ApplicationPlugin, widget: QWidget) -> None:
        info = plugin.info
        self.addSubInterface(widget, info.icon, info.name, NavigationItemPosition.TOP)

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

    def add_plugin(self) -> None:
        paths = self._select_plugin_paths()
        if not paths:
            return

        added_plugins = []
        errors = []

        for path in paths:
            try:
                plugin_path = self.plugin_manager.resolve_plugin_path(path)
                plugin = self.plugin_manager.register_from_path(plugin_path)
                self.user_plugin_paths[plugin.info.plugin_id] = plugin_path
                added_plugins.append(plugin.info.name)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")

        if added_plugins:
            self._save_user_plugins()
            self.plugin_center_page.refresh()
            self.navigationInterface.setCurrentItem(
                self.plugin_center_page.objectName()
            )

            InfoBar.success(
                title="插件已添加",
                content=f"已添加 {len(added_plugins)} 个插件",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )

        if errors:
            InfoBar.error(
                title="部分插件添加失败" if added_plugins else "添加失败",
                content="; ".join(errors),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def confirm_action(self, title: str, content: str) -> bool:
        # result = QMessageBox.question(
        #     self,
        #     title,
        #     content,
        #     QMessageBox.Yes | QMessageBox.No,
        #     QMessageBox.No,
        # )
        # return result == QMessageBox.Yes
        result = MessageConfirmBox(
            parent=self,
            title=title,
            content=content,
            show_cancel_btn=True,
        ).exec()
        return result

    def is_user_plugin(self, plugin_id: str) -> bool:
        return plugin_id in self.user_plugin_paths

    def remove_user_plugin(self, plugin_id: str) -> None:
        if plugin_id not in self.user_plugin_paths:
            raise ValueError("内置插件不能从插件管理中移除")

        self.plugin_manager.unregister(plugin_id)
        self.user_plugin_paths.pop(plugin_id, None)
        self._save_user_plugins()

    def _select_plugin_paths(self) -> list[Path]:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择插件文件",
            str(self.plugin_dir),
            "Python 插件 (*.py)",
        )
        return [Path(file_path) for file_path in file_paths]

    def _load_user_plugins(self) -> None:
        if not self.plugin_config_path.exists():
            self.open_screen_interface = ""
            return

        try:
            data = json.loads(self.plugin_config_path.read_text(encoding="utf-8"))
        except Exception:
            traceback.print_exc()
            self.open_screen_interface = ""
            return

        self.open_screen_interface = data.get("open_screen_interface", "")

        # 主题色 / 主题模式 — 在 __init__ 中会被读取并应用
        saved_color = data.get("theme_color")
        if isinstance(saved_color, str) and saved_color.strip():
            self.theme_color = saved_color.strip()
        saved_mode = data.get("theme_mode")
        if isinstance(saved_mode, str):
            self.theme_mode = saved_mode.strip()

        for raw_path in data.get("plugins", []):
            try:
                resolved = self._resolve_app_path(raw_path)
                plugin_path = self.plugin_manager.resolve_plugin_path(resolved)
                plugin = self.plugin_manager.register_from_path(plugin_path)
                self.user_plugin_paths[plugin.info.plugin_id] = plugin_path
            except Exception:
                traceback.print_exc()

    def _load_startup_plugins(self) -> None:
        for plugin_id in list(self.user_plugin_paths.keys()):
            try:
                self.plugin_manager.load(plugin_id)
            except Exception:
                traceback.print_exc()

    def _navigate_to_open_screen(self) -> None:
        """根据插件配置 open_screen_interface 跳转到对应界面。"""
        target = getattr(self, "open_screen_interface", "")

        if target and target != self.plugin_center_page.objectName():
            # 在已加载的插件中查找匹配的 widget
            for loaded in self.plugin_manager.loaded_plugins.values():
                if loaded.widget.objectName() == target:
                    self.navigate_to_widget(loaded.widget)
                    return

        # 默认回到插件管理页
        self.navigate_to_widget(self.plugin_center_page)

    def _save_user_plugins(self) -> None:
        existing = {}
        if self.plugin_config_path.exists():
            try:
                existing = json.loads(
                    self.plugin_config_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass

        data = {
            "plugins": [
                str(path) for _, path in sorted(self.user_plugin_paths.items())
            ],
            "open_screen_interface": existing.get("open_screen_interface", ""),
            "theme_color": getattr(
                self, "theme_color", existing.get("theme_color", "#0078D4")
            ),
            "theme_mode": getattr(
                self, "theme_mode", existing.get("theme_mode", "")
            ),
        }
        if self.plugin_config_path.parent != Path("."):
            self.plugin_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugin_config_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # def _register_builtin_plugins(self) -> None:
    #     try:
    #         from cmd_executor import CommandToolPage

    #         self.plugin_manager.register(
    #             PagePlugin(
    #                 PluginInfo(
    #                     plugin_id="command_tool",
    #                     name="命令执行",
    #                     description="批量配置并执行命令行工具",
    #                     icon=FIF.COMMAND_PROMPT,
    #                 ),
    #                 CommandToolPage,
    #             )
    #         )
    #     except Exception:
    #         traceback.print_exc()

    def closeEvent(self, event) -> None:
        # 保存当前界面到配置，下次启动自动恢复
        try:
            current_widget = self.stackedWidget.currentWidget()
            if current_widget:
                self._save_open_screen_interface(current_widget.objectName())
        except Exception:
            pass

        for plugin_id in list(self.plugin_manager.loaded_plugins.keys()):
            try:
                self.plugin_manager.unload(plugin_id)
            except Exception:
                pass
        event.accept()

    def _save_open_screen_interface(self, interface_name: str) -> None:
        """将当前界面名称写入 plugins.json 的 open_screen_interface 字段。"""
        existing = {}
        if self.plugin_config_path.exists():
            try:
                existing = json.loads(
                    self.plugin_config_path.read_text(encoding="utf-8")
                )
            except Exception:
                pass
        existing["open_screen_interface"] = interface_name
        self.plugin_config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def main() -> None:
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
