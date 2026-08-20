#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""番茄时钟页面。"""

import json
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LargeTitleLabel,
    PrimaryPushButton,
    ProgressRing,
    PushButton,
    SpinBox,
    StrongBodyLabel,
    SwitchButton,
    isDarkTheme,
    themeColor,
)

from ApplicationFramework import APP_STATE_DIR, connect_theme_changed


def _subtle_color() -> str:
    return "#6E7378" if isDarkTheme() else "#888"


class PomodoroPage(QWidget):
    """番茄计时器页面。"""

    MODE_NAMES = {
        "work": "专注工作",
        "short_break": "短休息",
        "long_break": "长休息",
    }

    MODE_COLORS = {
        "work": "#0078D4",
        "short_break": "#4CAF50",
        "long_break": "#4CAF50",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PomodoroPage")

        self.mode = "work"
        self.remaining_seconds = 0
        self.completed = 0
        self.running = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)

        self.work_minutes = 25
        self.short_break_minutes = 5
        self.long_break_minutes = 15
        self.long_break_interval = 4

        self.state_dir = APP_STATE_DIR / "pomodoro"
        self.state_path = self.state_dir / "pomodoro_state.json"
        self.legacy_state_path = Path(__file__).resolve().parent / "pomodoro_state.json"
        self._load_state()

        self.init_ui()
        self.remaining_seconds = self.work_minutes * 60
        self._update_display()

        connect_theme_changed(self.refresh_theme_styles)

    def _load_state(self) -> None:
        for path in (self.state_path, self.legacy_state_path):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.completed = int(data.get("completed", 0))
                return
            except Exception:
                continue
        self.completed = 0

    def _save_state(self) -> None:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps({"completed": self.completed}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("番茄时钟", self))

        timer_card = CardWidget(self)
        timer_layout = QVBoxLayout(timer_card)
        timer_layout.setContentsMargins(16, 24, 16, 24)
        timer_layout.setSpacing(8)

        self.mode_label = StrongBodyLabel("专注工作", timer_card)
        self.mode_label.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.mode_label)

        self.progress_ring = ProgressRing(timer_card)
        self.progress_ring.setFixedSize(220, 220)
        self.progress_ring.setTextVisible(False)

        self.time_label = LargeTitleLabel("25:00", self.progress_ring)
        self.time_label.setAlignment(Qt.AlignCenter)
        ring_layout = QHBoxLayout(self.progress_ring)
        ring_layout.setContentsMargins(0, 0, 0, 0)
        ring_layout.addWidget(self.time_label)
        timer_layout.addWidget(self.progress_ring, 0, Qt.AlignCenter)

        self.count_label = BodyLabel(
            f"今日完成: {self.completed} 个番茄",
            timer_card,
        )
        self.count_label.setAlignment(Qt.AlignCenter)
        timer_layout.addWidget(self.count_label)

        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(0, 12, 0, 0)
        self.start_btn = PrimaryPushButton("开始", timer_card)
        self.start_btn.setIcon(FIF.PLAY)
        self.start_btn.clicked.connect(self.toggle)

        self.reset_btn = PushButton("重置", timer_card)
        self.reset_btn.setIcon(FIF.SYNC)
        self.reset_btn.clicked.connect(self.reset)

        control_layout.addStretch(1)
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.reset_btn)
        control_layout.addStretch(1)
        timer_layout.addLayout(control_layout)

        layout.addWidget(timer_card)

        settings_card = CardWidget(self)
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(16, 16, 16, 16)
        settings_layout.setSpacing(10)

        settings_layout.addWidget(StrongBodyLabel("时长设置", settings_card))

        settings_layout.addLayout(self._duration_row("专注 (分钟)", settings_card))
        settings_layout.addLayout(self._duration_row("短休息 (分钟)", settings_card))
        settings_layout.addLayout(self._duration_row("长休息 (分钟)", settings_card))
        settings_layout.addLayout(self._duration_row("长休息间隔 (个番茄)", settings_card))

        auto_layout = QHBoxLayout()
        auto_layout.addWidget(BodyLabel("自动开始下一阶段", settings_card))
        auto_layout.addStretch(1)
        self.auto_start_switch = SwitchButton("", settings_card)
        self.auto_start_switch.setOnText("开")
        self.auto_start_switch.setOffText("关")
        self.auto_start_switch.setChecked(True)
        auto_layout.addWidget(self.auto_start_switch)
        settings_layout.addLayout(auto_layout)

        layout.addWidget(settings_card)
        layout.addStretch(1)

        self.refresh_theme_styles()

    def _duration_row(self, text: str, parent: QWidget):
        """生成一行“标签 + 数值输入”的配置行。"""
        row = QHBoxLayout()
        label = BodyLabel(text, parent)
        spin = SpinBox(parent)
        spin.setRange(1, 180)
        spin.setSuffix(" min")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(spin)

        if text.startswith("专注"):
            spin.setValue(self.work_minutes)
            spin.valueChanged.connect(self._set_work)
        elif text.startswith("短休息"):
            spin.setValue(self.short_break_minutes)
            spin.valueChanged.connect(self._set_short_break)
        elif text.startswith("长休息间隔"):
            spin.setRange(1, 12)
            spin.setSuffix(" 个")
            spin.setValue(self.long_break_interval)
            spin.valueChanged.connect(self._set_interval)
        else:
            spin.setValue(self.long_break_minutes)
            spin.valueChanged.connect(self._set_long_break)
        return row

    def refresh_theme_styles(self) -> None:
        """主题切换后刷新依赖 isDarkTheme() 的颜色。"""
        self.count_label.setStyleSheet(f"color: {_subtle_color()};")

    def _set_work(self, value) -> None:
        self.work_minutes = value
        if self.mode == "work" and not self.running:
            self.remaining_seconds = value * 60
            self._update_display()

    def _set_short_break(self, value) -> None:
        self.short_break_minutes = value
        if self.mode == "short_break" and not self.running:
            self.remaining_seconds = value * 60
            self._update_display()

    def _set_long_break(self, value) -> None:
        self.long_break_minutes = value
        if self.mode == "long_break" and not self.running:
            self.remaining_seconds = value * 60
            self._update_display()

    def _set_interval(self, value) -> None:
        self.long_break_interval = value

    def _duration_seconds(self, mode: str) -> int:
        if mode == "work":
            return self.work_minutes * 60
        if mode == "short_break":
            return self.short_break_minutes * 60
        return self.long_break_minutes * 60

    def toggle(self) -> None:
        if self.running:
            self.timer.stop()
            self.running = False
            self.start_btn.setText("继续")
            self.start_btn.setIcon(FIF.PLAY)
        else:
            self.timer.start()
            self.running = True
            self.start_btn.setText("暂停")
            self.start_btn.setIcon(FIF.PAUSE)

    def reset(self) -> None:
        self.timer.stop()
        self.running = False
        self.remaining_seconds = self._duration_seconds(self.mode)
        self.start_btn.setText("开始")
        self.start_btn.setIcon(FIF.PLAY)
        self._update_display()

    def _on_tick(self) -> None:
        self.remaining_seconds -= 1
        if self.remaining_seconds > 0:
            self._update_display()
            return

        self._finish_current_mode()
        next_auto = self.auto_start_switch.isChecked()
        self._start_next_mode()
        if next_auto:
            self.timer.start()
            self.running = True
            self.start_btn.setText("暂停")
            self.start_btn.setIcon(FIF.PAUSE)
        else:
            self.timer.stop()
            self.running = False
            self.start_btn.setText("开始")
            self.start_btn.setIcon(FIF.PLAY)

    def _finish_current_mode(self) -> None:
        if self.mode == "work":
            self.completed += 1
            self._save_state()

    def _start_next_mode(self) -> None:
        if self.mode == "work":
            self.mode = (
                "long_break"
                if self.completed % self.long_break_interval == 0
                else "short_break"
            )
        else:
            self.mode = "work"
        self.remaining_seconds = self._duration_seconds(self.mode)
        self._notify(f"{self.MODE_NAMES[self.mode]}阶段开始")
        self._update_display()

    def _notify(self, content: str) -> None:
        InfoBar.success(
            title="番茄时钟",
            content=content,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3000,
        )
        QApplication.beep()

    def _update_display(self) -> None:
        minutes, seconds = divmod(max(self.remaining_seconds, 0), 60)
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")
        self.mode_label.setText(self.MODE_NAMES[self.mode])
        self.progress_ring.setValue(self._elapsed_percent())
        self._apply_ring_color()

    def _apply_ring_color(self) -> None:
        """根据当前阶段设置进度环颜色：工作为蓝，休息为绿。"""
        color = self.MODE_COLORS.get(self.mode, themeColor().name())
        self.progress_ring.setCustomBarColor(color, color)

    def _elapsed_percent(self) -> int:
        total = self._duration_seconds(self.mode)
        if total <= 0:
            return 0
        elapsed = total - max(self.remaining_seconds, 0)
        return max(0, min(100, round(elapsed / total * 100)))

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self._save_state()
        super().closeEvent(event)
