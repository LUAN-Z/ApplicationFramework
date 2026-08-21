#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插件脚手架 UI。"""

import json
import re
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    CaptionLabel,
    CheckBox,
    EditableComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SimpleCardWidget,
    StrongBodyLabel,
    SubtitleLabel,
)


PLUGIN_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _class_name(plugin_id: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in plugin_id.split("_") if part)


def _init_template(plugin_id: str, plugin_name: str, description: str, class_name: str) -> str:
    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插件入口。"""

import sys
from pathlib import Path


def _add_plugin_dependency_paths() -> None:
    plugin_dir = Path(__file__).resolve().parent
    for name in ("vendor", "deps"):
        dependency_path = plugin_dir / name
        if dependency_path.exists():
            raw_path = str(dependency_path)
            if raw_path not in sys.path:
                sys.path.insert(0, raw_path)


_add_plugin_dependency_paths()

from ApplicationFramework import ApplicationPlugin, PluginInfo
from qfluentwidgets import FluentIcon as FIF

try:
    from .ui import {class_name}Page
except ImportError:
    from ui import {class_name}Page


class {class_name}Plugin(ApplicationPlugin):
    info = PluginInfo(
        plugin_id={plugin_id!r},
        name={plugin_name!r},
        description={description!r},
        version="1.0.0",
        icon=FIF.APPLICATION,
    )

    def create_widget(self, parent=None):
        return {class_name}Page(parent)


def create_plugin():
    return {class_name}Plugin()
'''


def _ui_template(class_name: str, plugin_name: str, description: str, with_storage: bool) -> str:
    storage_import = ""
    storage_init = ""
    if with_storage:
        storage_import = """
try:
    from .storage import JsonStore
except ImportError:
    from storage import JsonStore
"""
        storage_init = """
        self.store = JsonStore(Path.home() / ".application_framework" / "{folder}" / "data.json")
        self.store.load()
""".format(folder=class_name.lower())

    return f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""插件页面。"""

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, PrimaryPushButton, StrongBodyLabel
{storage_import}

class {class_name}Page(QWidget):
    """插件主页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("{class_name}Page")
{storage_init}
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = StrongBodyLabel({plugin_name!r}, self)
        layout.addWidget(title)

        desc = BodyLabel({(description or "这是一个新插件。")!r}, self)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        action_btn = PrimaryPushButton("示例操作", self)
        action_btn.clicked.connect(self._on_action)
        layout.addWidget(action_btn, 0, Qt.AlignLeft)

        layout.addStretch(1)

    def _on_action(self):
        print({f"{plugin_name}: 示例操作"!r})
'''


def _storage_template() -> str:
    return '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""简单 JSON 存储工具。"""

import json
from pathlib import Path
from typing import Any, Dict


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        return self.data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
'''


def _readme_template(plugin_id: str, plugin_name: str, description: str) -> str:
    return f'''# {plugin_name}

插件 ID：`{plugin_id}`

{description or "这是一个通过插件脚手架生成的新插件。"}

## 文件结构

- `__init__.py`：插件入口，提供 `create_plugin()`
- `ui.py`：插件页面
- `storage.py`：可选 JSON 存储工具

## 第三方依赖

如果插件需要额外 Python 包，可以在插件目录创建 `requirements.txt`，然后执行：

```bash
python scripts/vendor_plugin_deps.py plugins/{plugin_id}
```

依赖会安装到插件自己的 `vendor/` 目录，编译版主程序也会自动识别，不需要重新编译主程序。
'''


class PluginScaffolderPage(QWidget):
    """创建插件模板的工具页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.framework = parent
        self.setObjectName("PluginScaffolderPage")
        self.default_root = Path(__file__).resolve().parents[1]
        self.app_dir = self.default_root.parent
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(4)
        title = SubtitleLabel("插件脚手架", self)
        subtitle = CaptionLabel("生成标准插件目录、入口文件和页面模板", self)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_row.addLayout(header_text, 1)

        self.create_btn = PrimaryPushButton("创建插件", self)
        self.create_btn.setIcon(FIF.ADD.icon())
        self.create_btn.clicked.connect(self.create_plugin_files)
        header_row.addWidget(self.create_btn, 0, Qt.AlignTop)
        root.addLayout(header_row)

        content = QHBoxLayout()
        content.setSpacing(14)

        form_card = CardWidget(self)
        form = QVBoxLayout(form_card)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(12)
        form.addWidget(StrongBodyLabel("插件信息", self))

        self.plugin_id_edit = LineEdit(self)
        self.plugin_id_edit.setPlaceholderText("my_plugin")
        self.plugin_id_edit.textChanged.connect(self._sync_default_name)
        self.plugin_id_edit.textChanged.connect(self._update_preview)
        form.addWidget(CaptionLabel("插件 ID", self))
        form.addWidget(self.plugin_id_edit)

        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText("我的插件")
        self.name_edit.textChanged.connect(self._update_preview)
        form.addWidget(CaptionLabel("插件名称", self))
        form.addWidget(self.name_edit)

        self.description_edit = LineEdit(self)
        self.description_edit.setPlaceholderText("插件描述")
        self.description_edit.textChanged.connect(self._update_preview)
        form.addWidget(CaptionLabel("插件描述", self))
        form.addWidget(self.description_edit)

        path_row = QHBoxLayout()
        self.target_dir_edit = LineEdit(self)
        self.target_dir_edit.setText(str(self.default_root))
        self.target_dir_edit.textChanged.connect(self._update_preview)
        browse_btn = PushButton("选择目录", self)
        browse_btn.setIcon(FIF.FOLDER.icon())
        browse_btn.clicked.connect(self._choose_target_dir)
        path_row.addWidget(self.target_dir_edit, 1)
        path_row.addWidget(browse_btn)
        form.addWidget(CaptionLabel("生成位置", self))
        form.addLayout(path_row)

        form.addSpacing(2)
        form.addWidget(StrongBodyLabel("模板选项", self))
        self.storage_check = CheckBox("生成 storage.py", self)
        self.readme_check = CheckBox("生成 README.md", self)
        self.readme_check.setChecked(True)
        self.register_check = CheckBox("创建后自动加入当前插件列表", self)
        self.storage_check.stateChanged.connect(self._update_preview)
        self.readme_check.stateChanged.connect(self._update_preview)
        self.register_check.stateChanged.connect(self._sync_register_ui)
        self.register_check.stateChanged.connect(self._update_preview)
        form.addWidget(self.storage_check)
        form.addWidget(self.readme_check)
        form.addWidget(self.register_check)

        group_row = QHBoxLayout()
        group_row.addWidget(CaptionLabel("归类", self))
        self.group_combo = EditableComboBox(self)
        self.group_combo.setPlaceholderText("工具")
        self._reload_group_options()
        self.group_combo.textChanged.connect(self._update_preview)
        group_row.addWidget(self.group_combo, 1)
        reload_group_btn = PushButton("刷新", self)
        reload_group_btn.setIcon(FIF.SYNC.icon())
        reload_group_btn.clicked.connect(lambda _checked=False: self._reload_group_options())
        group_row.addWidget(reload_group_btn)
        form.addLayout(group_row)
        self._sync_register_ui()
        form.addStretch(1)

        content.addWidget(form_card, 5)

        preview_col = QVBoxLayout()
        preview_col.setSpacing(12)

        summary_card = SimpleCardWidget(self)
        summary = QVBoxLayout(summary_card)
        summary.setContentsMargins(16, 14, 16, 14)
        summary.setSpacing(8)
        summary.addWidget(StrongBodyLabel("生成预览", self))
        self.summary_label = BodyLabel("", self)
        self.summary_label.setWordWrap(True)
        summary.addWidget(self.summary_label)
        preview_col.addWidget(summary_card)

        tree_card = CardWidget(self)
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(16, 14, 16, 16)
        tree_layout.setSpacing(8)
        tree_layout.addWidget(StrongBodyLabel("文件结构", self))
        self.preview_text = PlainTextEdit(self)
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(190)
        tree_layout.addWidget(self.preview_text)
        preview_col.addWidget(tree_card, 1)

        self.result_label = CaptionLabel("", self)
        self.result_label.setWordWrap(True)
        preview_col.addWidget(self.result_label)
        content.addLayout(preview_col, 6)

        root.addLayout(content, 1)
        self._update_preview()

    def _sync_default_name(self, plugin_id: str) -> None:
        if self.name_edit.text().strip():
            return
        readable = plugin_id.replace("_", " ").strip().title()
        if readable:
            self.name_edit.setPlaceholderText(readable)

    def _choose_target_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择生成目录",
            self.target_dir_edit.text().strip() or str(self.default_root),
        )
        if directory:
            self.target_dir_edit.setText(directory)

    def _current_plugin_id(self) -> str:
        return self.plugin_id_edit.text().strip() or self.plugin_id_edit.placeholderText()

    def _current_plugin_name(self) -> str:
        return self.name_edit.text().strip() or self.name_edit.placeholderText()

    def _current_group_title(self) -> str:
        return self.group_combo.currentText().strip() or "工具"

    def _reload_group_options(self) -> None:
        current = ""
        if hasattr(self, "group_combo"):
            current = self.group_combo.currentText().strip()

        groups = self._load_plugin_groups()
        self.group_combo.clear()
        self.group_combo.addItems(groups)
        self.group_combo.setText(current or groups[0])

    def _load_plugin_groups(self) -> list[str]:
        data = {}
        groups = []
        if self.framework is not None and hasattr(self.framework, "_read_plugin_config"):
            data = self.framework._read_plugin_config()
            for title in getattr(self.framework, "plugin_group_order", []):
                if isinstance(title, str) and title.strip() and title.strip() not in groups:
                    groups.append(title.strip())
        else:
            config_path = self.app_dir / "config" / "plugins.json"
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}

        for group in data.get("plugin_groups", []):
            if not isinstance(group, dict):
                continue
            title = group.get("title")
            if isinstance(title, str) and title.strip() and title.strip() not in groups:
                groups.append(title.strip())

        if not groups:
            groups.append("工具")
        return groups

    def _sync_register_ui(self, *args) -> None:
        enabled = self.register_check.isChecked()
        self.group_combo.setEnabled(enabled)

    def _preview_lines(self) -> list[str]:
        plugin_id = self._current_plugin_id()
        lines = [
            f"{plugin_id}/",
            "  __init__.py",
            "  ui.py",
        ]
        if self.storage_check.isChecked():
            lines.append("  storage.py")
        if self.readme_check.isChecked():
            lines.append("  README.md")
        return lines

    def _update_preview(self, *args) -> None:
        plugin_id = self._current_plugin_id()
        plugin_name = self._current_plugin_name()
        target_root = self.target_dir_edit.text().strip() or str(self.default_root)
        target_path = Path(target_root).expanduser() / plugin_id

        validity = "可创建" if PLUGIN_ID_RE.match(plugin_id) else "插件 ID 格式不合法"
        auto_register = (
            f"会加入“{self._current_group_title()}”分类"
            if self.register_check.isChecked()
            else "仅生成文件"
        )
        self.summary_label.setText(
            f"{plugin_name}\n"
            f"{target_path}\n"
            f"{validity} · {auto_register}"
        )
        self.preview_text.setPlainText("\n".join(self._preview_lines()))

    def create_plugin_files(self) -> None:
        try:
            plugin_dir = self._create_plugin_files()
        except Exception as exc:
            InfoBar.error(
                title="创建失败",
                content=str(exc),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return

        self.result_label.setText(f"已创建: {plugin_dir}")
        self._update_preview()
        InfoBar.success(
            title="插件已创建",
            content=str(plugin_dir),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3500,
        )

    def _create_plugin_files(self) -> Path:
        plugin_id = self.plugin_id_edit.text().strip()
        if not PLUGIN_ID_RE.match(plugin_id):
            raise ValueError("插件 ID 只能包含字母、数字、下划线，且不能以数字开头")

        plugin_name = self.name_edit.text().strip() or self.name_edit.placeholderText()
        description = self.description_edit.text().strip()
        target_root = Path(self.target_dir_edit.text().strip()).expanduser()
        if not target_root:
            raise ValueError("请选择生成位置")

        plugin_dir = target_root / plugin_id
        if plugin_dir.exists():
            raise FileExistsError(f"目录已存在: {plugin_dir}")

        class_name = _class_name(plugin_id)
        if not class_name:
            raise ValueError("无法从插件 ID 生成类名")

        with_storage = self.storage_check.isChecked()
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "__init__.py").write_text(
            _init_template(plugin_id, plugin_name, description, class_name),
            encoding="utf-8",
        )
        (plugin_dir / "ui.py").write_text(
            _ui_template(class_name, plugin_name, description, with_storage),
            encoding="utf-8",
        )

        if with_storage:
            (plugin_dir / "storage.py").write_text(
                _storage_template(),
                encoding="utf-8",
            )

        if self.readme_check.isChecked():
            (plugin_dir / "README.md").write_text(
                _readme_template(plugin_id, plugin_name, description),
                encoding="utf-8",
            )

        if self.register_check.isChecked():
            self._register_created_plugin(plugin_dir / "__init__.py")

        return plugin_dir

    def _register_created_plugin(self, init_path: Path) -> None:
        if self.framework is None:
            return

        plugin = self.framework.plugin_manager.register_from_path(init_path)
        self.framework.user_plugin_paths[plugin.info.plugin_id] = init_path.resolve()
        self.framework.plugin_group_by_id[plugin.info.plugin_id] = self._current_group_title()
        if self._current_group_title() not in self.framework.plugin_group_order:
            self.framework.plugin_group_order.append(self._current_group_title())
        self.framework._save_user_plugins()
        self.framework.plugin_center_page.refresh()
