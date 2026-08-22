#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Log 导入 Excel 插件页面。"""

import sys

from PyQt5.QtCore import QObject, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    EditableComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from .core import (
    DEFAULT_KEYWORDS,
    build_sorted_content,
    collect_txt_files,
    export_to_excel,
    resolve_output_path,
    save_sorted_txt,
)


class _StdoutEmitter(QObject):
    """把 print 输出转发为信号，交给主线程写进日志框。"""
    out = pyqtSignal(str)


class _StdoutRedirector:
    def __init__(self, emitter):
        self.emitter = emitter

    def write(self, text):
        if text:
            self.emitter.out.emit(text)

    def flush(self):
        pass


class _ExportWorker(QThread):
    """后台执行排序与导入，避免阻塞界面。"""

    finishedOk = pyqtSignal(int)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = options
        self.result_path = None

    def run(self):
        try:
            opt = self.options
            txt_files, missing_paths = collect_txt_files(
                opt["inputs"], recursive=opt["recursive"]
            )
            for missing in missing_paths:
                print(f"警告：路径不存在，已跳过 -> {missing}")

            if not txt_files:
                print("错误：未找到可处理的 TXT 文件")
                self.finishedOk.emit(1)
                return

            processed_files = []
            failed_files = []
            saved_sorted_files = []

            print(f"--- 开始处理 {len(txt_files)} 个文件 ---")
            for txt_file in txt_files:
                print(f"正在排序文件：{txt_file.name}")
                try:
                    processed = build_sorted_content(
                        txt_file,
                        encoding=opt["encoding"],
                        keep_header=opt["keep_header"],
                    )
                    processed_files.append(processed)
                    print(
                        f"[成功] {txt_file.name} 排序完成，检测到 {processed['batch_count']} "
                        f"个批次，共排序 {processed['sorted_row_count']} 条数据。"
                    )

                    if opt["save_sorted"]:
                        output_path = save_sorted_txt(
                            processed,
                            sorted_dir=opt["sorted_dir"],
                            encoding=opt["encoding"],
                        )
                        saved_sorted_files.append(output_path)
                        print(f"[OK] 已输出排序文件：{output_path}")
                except Exception as exc:
                    failed_files.append((txt_file.name, str(exc)))
                    print(f"[错误] {txt_file.name} 处理失败：{exc}")

            if not processed_files:
                print("错误：所有文件处理失败，未生成 Excel")
                self.finishedOk.emit(1)
                return

            output_path = resolve_output_path(opt["output"], txt_files)

            success, skipped_files = export_to_excel(
                processed_files=processed_files,
                excel_file_path=output_path,
                key_words=opt["keywords"],
                append_existing=opt["append_existing"],
                import_unmatched=opt["import_unmatched"],
            )

            print("\n--- 处理完成 ---")
            print(f"成功排序 {len(processed_files)}/{len(txt_files)} 个文件")
            if skipped_files:
                print(f"未命中关键字并跳过 {len(skipped_files)} 个文件")
            if failed_files:
                print(f"处理失败 {len(failed_files)} 个文件：")
                for file_name, err in failed_files:
                    print(f"  - {file_name}: {err}")
            if saved_sorted_files:
                print(f"额外输出排序 TXT {len(saved_sorted_files)} 个")

            self.result_path = str(output_path)
            self.finishedOk.emit(0 if success else 1)
        except Exception as exc:
            print(f"执行失败：{exc}")
            self.finishedOk.emit(1)


class DropFileList(ListWidget):
    """支持拖入 TXT 文件/目录的路径列表。"""

    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile()
        ]
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class LogExcelImportPage(QWidget):
    """Log TXT 排序并按关键字导入 Excel 页面。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogExcelImportPage")

        self.worker = None
        self._old_stdout = sys.stdout
        self.emitter = _StdoutEmitter(self)
        self.redirector = _StdoutRedirector(self.emitter)

        # 输出路径是用户显式指定（False）还是上一次自动解析出的（True）。
        # 自动解析出的路径仅供提示与"打开"，下次运行应按新输入重新解析，
        # 避免上一个文件夹的 result.xlsx 被本次数据覆盖。
        self._output_is_auto = False
        self._last_output_explicit = True

        self._init_ui()
        self.emitter.out.connect(self._append_log)

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        root.addWidget(StrongBodyLabel("Log 导入 Excel", self))

        # ---- 输入 ----
        input_card = CardWidget(self)
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(8)
        input_layout.addWidget(CaptionLabel("输入：拖入或添加要处理的 TXT 文件/目录", input_card))

        self.input_list = DropFileList(input_card)
        self.input_list.setMinimumHeight(72)
        self.input_list.filesDropped.connect(self._add_paths)
        input_layout.addWidget(self.input_list)

        in_row = QHBoxLayout()
        add_file_btn = PushButton("添加文件", input_card)
        add_file_btn.setIcon(FIF.DOCUMENT)
        add_file_btn.clicked.connect(self._add_files)
        add_dir_btn = PushButton("添加目录", input_card)
        add_dir_btn.setIcon(FIF.FOLDER)
        add_dir_btn.clicked.connect(self._add_directory)
        remove_btn = PushButton("移除所选", input_card)
        remove_btn.setIcon(FIF.DELETE)
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn = PushButton("清空", input_card)
        clear_btn.setIcon(FIF.CANCEL)
        clear_btn.clicked.connect(self._clear_inputs)
        self.recursive_check = CheckBox("递归扫描子目录", input_card)
        self.recursive_check.setToolTip("输入为目录时，递归扫描子目录中的 TXT")
        in_row.addWidget(add_file_btn)
        in_row.addWidget(add_dir_btn)
        in_row.addStretch(1)
        in_row.addWidget(remove_btn)
        in_row.addWidget(clear_btn)
        in_row.addWidget(self.recursive_check)
        input_layout.addLayout(in_row)
        root.addWidget(input_card)

        # ---- 选项 ----
        option_card = CardWidget(self)
        option_layout = QVBoxLayout(option_card)
        option_layout.setContentsMargins(14, 10, 14, 10)
        option_layout.setSpacing(8)
        option_layout.addWidget(CaptionLabel("导入选项", option_card))

        self.keywords_edit = LineEdit(option_card)
        self.keywords_edit.setText("NTNV NTHV NTLV HTNV HTHV HTLV")
        self.keywords_edit.setToolTip("文件名命中关键字的顺序决定 sheet 生成顺序；空格分隔")
        self.encoding_combo = EditableComboBox(option_card)
        self.encoding_combo.addItems(["utf-8", "gbk", "gb2312", "latin-1"])
        self.encoding_combo.setCurrentText("utf-8")
        row_a = QHBoxLayout()
        row_a.addWidget(BodyLabel("关键字", option_card))
        row_a.addWidget(self.keywords_edit, 1)
        row_a.addWidget(BodyLabel("编码", option_card))
        row_a.addWidget(self.encoding_combo)
        option_layout.addLayout(row_a)

        self.output_edit = LineEdit(option_card)
        self.output_edit.setPlaceholderText("输出 Excel 路径（留空自动放到日志目录 result.xlsx）")
        self.output_edit.textEdited.connect(self._set_output_manual)
        choose_btn = PushButton("选择", option_card)
        choose_btn.setIcon(FIF.SAVE_AS)
        choose_btn.clicked.connect(self._choose_output)
        self.open_btn = PushButton("打开", option_card)
        self.open_btn.setIcon(FIF.FOLDER)
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open_output)
        row_b = QHBoxLayout()
        row_b.addWidget(BodyLabel("输出", option_card))
        row_b.addWidget(self.output_edit, 1)
        row_b.addWidget(choose_btn)
        row_b.addWidget(self.open_btn)
        option_layout.addLayout(row_b)

        self.append_check = CheckBox("追加已有 Excel", option_card)
        self.import_unmatched_check = CheckBox("未命中按文件名导入", option_card)
        self.save_sorted_check = CheckBox("输出排序 TXT", option_card)
        self.no_header_check = CheckBox("去除头部", option_card)
        row_c = QHBoxLayout()
        for cb in (self.append_check, self.import_unmatched_check,
                   self.save_sorted_check, self.no_header_check):
            row_c.addWidget(cb)
        row_c.addStretch(1)
        option_layout.addLayout(row_c)
        tooltips = {
            self.append_check: "输出 Excel 已存在时追加 sheet，而非覆盖",
            self.import_unmatched_check: "文件名未命中关键字时按自身文件名建 sheet",
            self.save_sorted_check: "额外输出排序后的 TXT 文件",
            self.no_header_check: "导出时不保留原始头部信息",
        }
        for cb, tip in tooltips.items():
            cb.setToolTip(tip)

        self.sorted_dir_edit = LineEdit(option_card)
        self.sorted_dir_edit.setPlaceholderText("排序 TXT 输出目录（可选，配合上方\"输出排序 TXT\"）")
        self.save_sorted_check.toggled.connect(self.sorted_dir_edit.setEnabled)
        self.sorted_dir_edit.setEnabled(False)
        row_d = QHBoxLayout()
        row_d.addWidget(BodyLabel("排序目录", option_card))
        row_d.addWidget(self.sorted_dir_edit, 1)
        option_layout.addLayout(row_d)
        root.addWidget(option_card)

        self.run_btn = PrimaryPushButton("开始导入", self)
        self.run_btn.setIcon(FIF.DOWNLOAD)
        self.run_btn.clicked.connect(self._start_export)
        root.addWidget(self.run_btn, 0, Qt.AlignLeft)

        log_card = CardWidget(self)
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(14, 10, 14, 10)
        log_layout.setSpacing(8)
        log_layout.addWidget(CaptionLabel("运行日志", log_card))
        self.log_text = PlainTextEdit(log_card)
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(110)
        log_layout.addWidget(self.log_text)
        root.addWidget(log_card, 1)

    # ---- 输入管理 ----
    def _current_inputs(self) -> list:
        return [self.input_list.item(i).text() for i in range(self.input_list.count())]

    def _add_paths(self, new_paths) -> None:
        existing = set(self._current_inputs())
        for p in new_paths:
            if p and p not in existing:
                self.input_list.addItem(QListWidgetItem(p))
                existing.add(p)

    def _add_files(self) -> None:
        files, _selected = QFileDialog.getOpenFileNames(
            self, "选择 TXT 文件", "", "文本文件 (*.txt);;所有文件 (*)",
        )
        self._add_paths(files)

    def _add_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择目录")
        if directory:
            self._add_paths([directory])

    def _remove_selected(self) -> None:
        rows = sorted(
            (self.input_list.row(item) for item in self.input_list.selectedItems()),
            reverse=True,
        )
        for row in rows:
            self.input_list.takeItem(row)

    def _clear_inputs(self) -> None:
        self.input_list.clear()

    def _choose_output(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "选择输出 Excel", "result.xlsx", "Excel 文件 (*.xlsx)",
        )
        if path:
            self.output_edit.setText(path)
            self._output_is_auto = False

    def _set_output_manual(self, _text: str) -> None:
        # 用户在输出框手动输入/编辑，视为显式指定，不再沿途自动解析
        self._output_is_auto = False

    def _open_output(self) -> None:
        path = self.output_edit.text().strip()
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---- 执行 ----
    def _collect_options(self) -> dict:
        keywords = [k for k in self.keywords_edit.text().replace(",", " ").split() if k]
        if not keywords:
            keywords = list(DEFAULT_KEYWORDS)
        return {
            "inputs": self._current_inputs(),
            "recursive": self.recursive_check.isChecked(),
            "keywords": keywords,
            "encoding": self.encoding_combo.currentText().strip() or "utf-8",
            "keep_header": not self.no_header_check.isChecked(),
            "save_sorted": self.save_sorted_check.isChecked(),
            "sorted_dir": self.sorted_dir_edit.text().strip() or None,
            "import_unmatched": self.import_unmatched_check.isChecked(),
            "append_existing": self.append_check.isChecked(),
            # 自动解析出的路径不属于用户选择，每次按当前输入重新解析，
            # 避免上一个文件夹生成的 result.xlsx 被本次数据覆盖
            "output": None
            if self._output_is_auto
            else (self.output_edit.text().strip() or None),
        }

    def _start_export(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        options = self._collect_options()
        # 记住本次输出是否为用户显式指定，供 _on_finished 标记自动/手动
        self._last_output_explicit = options["output"] is not None
        if not options["inputs"]:
            InfoBar.warning(
                title="缺少输入",
                content="请先添加要处理的 TXT 文件或目录",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return

        self.log_text.clear()
        self.run_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.worker = _ExportWorker(options, self)
        self.worker.finishedOk.connect(self._on_finished)
        sys.stdout = self.redirector
        self.worker.start()

    def _on_finished(self, code: int) -> None:
        sys.stdout = self._old_stdout
        self.run_btn.setEnabled(True)

        result_path = getattr(self.worker, "result_path", None)
        if result_path:
            self.output_edit.setText(result_path)
            self.open_btn.setEnabled(True)
            # 自动解析出的结果路径仅作提示；下一次运行按新输入重新解析
            self._output_is_auto = not self._last_output_explicit

        if code == 0:
            InfoBar.success(
                title="导入完成",
                content="Excel 已生成，可点击\"打开\"查看",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
        else:
            InfoBar.error(
                title="导入失败",
                content="请查看运行日志确认原因",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _append_log(self, text: str) -> None:
        self.log_text.appendPlainText(text.rstrip("\n"))
        bar = self.log_text.verticalScrollBar()
        bar.setValue(bar.maximum())


# ===========================================================================
