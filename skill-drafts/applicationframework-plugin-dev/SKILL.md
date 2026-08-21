---
name: applicationframework-plugin-dev
description: 在 ApplicationFramework 项目中创建、修改或审查插件时使用，确保插件结构、配置注册、数据存放和 UI 实现遵守项目规范。
metadata:
  short-description: 开发 ApplicationFramework 插件
---

# ApplicationFramework 插件开发

用于在 `ApplicationFramework` 项目中创建、修改或审查插件。目标是让新插件和现有 `plugin_scaffolder` 生成结果保持一致，并避免把运行数据、业务实现或配置写到错误位置。

## 先读取这些项目文件

处理插件任务前，优先读取当前仓库中的这些文件作为规范来源：

- `ApplicationFramework.py`：插件加载、生命周期、配置路径、`APP_STATE_DIR`、主题变更辅助函数。
- `plugins/plugin_scaffolder/ui.py`：脚手架生成的标准插件目录和模板。
- `config/plugins.json`：插件分组、默认加载列表、启动页和主题配置。
- 同类插件的 `__init__.py`、`ui.py`、`storage.py`：用于匹配项目当前风格。

如果这些文件中的实现与本 skill 描述不一致，以项目文件为准。

## 标准插件结构

新插件默认使用文件夹插件：

```text
plugins/<plugin_id>/
  __init__.py
  ui.py
  storage.py      可选，仅在确实需要独立存储辅助类时创建
  README.md       可选，只有用户要求或脚手架生成时保留
```

`plugin_id` 必须匹配 `^[A-Za-z_][A-Za-z0-9_]*$`，路径和配置里使用 `plugins/<plugin_id>/__init__.py`。

## `__init__.py` 规范

`__init__.py` 只作为插件入口，不放页面实现和业务逻辑。

必须包含：

- 从 `ApplicationFramework` 导入 `ApplicationPlugin`、`PluginInfo`。
- 从 `qfluentwidgets` 导入 `FluentIcon as FIF`。
- 兼容包内和直接加载的页面导入：

```python
try:
    from .ui import ExamplePage
except ImportError:
    from ui import ExamplePage
```

- 定义继承 `ApplicationPlugin` 的插件类。
- `info = PluginInfo(...)` 显式提供 `plugin_id`、`name`、`description`、`version`、`icon`。
- `create_widget(self, parent=None)` 返回页面实例。
- 顶层 `create_plugin()` 返回插件实例。

不要在 `__init__.py` 中创建 UI 控件、读写数据文件、启动线程或执行耗时逻辑。

## `ui.py` 规范

页面实现放在 `ui.py`。页面类通常继承 `QWidget`，在 `__init__` 中：

- 调用 `super().__init__(parent)`。
- 设置稳定的 `objectName`，例如 `PomodoroPage`。
- 保存必要状态，再调用 `_init_ui()`。

UI 优先沿用项目现有 PyQt5 + qfluentwidgets 风格：

- 使用 `QVBoxLayout`、`QHBoxLayout`、`CardWidget`、`SimpleCardWidget` 等现有组件。
- 使用 `LineEdit`、`PlainTextEdit`、`PushButton`、`PrimaryPushButton`、`CheckBox`、`EditableComboBox` 等 qfluentwidgets 组件。
- 按钮尽量设置 `FluentIcon` 图标。
- 避免在紧凑工具界面里做营销式大页面；插件页面应直接可用、信息密度适中。

如果插件需要响应主题变化，使用 `ApplicationFramework.connect_theme_changed(callback)`，回调内部要足够稳健，避免主题切换导致崩溃。

## 数据和配置规范

不要把运行数据写入插件目录。插件目录只放代码、模板或静态资源。

插件运行状态、用户数据、缓存数据应写入 `ApplicationFramework.APP_STATE_DIR` 下的插件专属子目录，例如：

```python
from ApplicationFramework import APP_STATE_DIR

STATE_PATH = APP_STATE_DIR / "my_plugin" / "state.json"
```

保存前创建父目录：

```python
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
```

如果修复旧插件的数据位置，可保留旧路径读取兼容，但新的保存只能写入 `APP_STATE_DIR`。

插件列表和分组写入 `config/plugins.json` 的 `plugin_groups`：

```json
{
  "plugin_groups": [
    {
      "title": "工具",
      "plugins": ["plugins/example/__init__.py"]
    }
  ]
}
```

添加新插件时，优先读取已有 `plugin_groups[].title`，按用户选择或插件用途归类；不要退回旧版顶层 `plugins` 列表格式。

## 开发流程

创建新插件时：

1. 先确认插件用途、`plugin_id`、中文名称、所属分组和是否需要持久化数据。
2. 按脚手架结构创建 `__init__.py` 和 `ui.py`。
3. 只有确实需要独立存储辅助类时才创建 `storage.py`。
4. 如需默认加载，将插件路径加入 `config/plugins.json` 对应 `plugin_groups`。
5. 使用 `python -m compileall -q plugins/<plugin_id>` 做语法校验。
6. 若改动会影响主框架加载或主题切换，尽量运行应用或做轻量导入检查。

修改已有插件时：

- 先对比 `plugin_scaffolder` 输出规范，找出结构差异。
- 保持用户已有逻辑，不做无关重构。
- 如果发现插件目录中存在运行数据，迁移到 `APP_STATE_DIR` 并保留必要的旧数据读取兼容。
- 不要擅自删除用户数据或覆盖用户配置。

## 审查重点

审查插件是否规范时，重点检查：

- `__init__.py` 是否只作为入口。
- 页面和业务 UI 是否在 `ui.py`。
- `create_plugin()` 是否存在并返回 `ApplicationPlugin` 实例。
- `PluginInfo.plugin_id` 是否唯一且符合命名规则。
- 数据文件是否写入 `APP_STATE_DIR`，而不是插件目录。
- `config/plugins.json` 是否使用显式 `plugin_groups` 分组。
- 主题切换、加载、卸载、文件路径操作是否有异常保护。
- 多文件操作、文件写入、批量替换等功能是否避免破坏用户原文件，必要时提供明确提示或备份策略。
