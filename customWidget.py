import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Type

from PyQt5.QtCore import (Qt, pyqtSignal)
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon as FIF,
    FluentWindow,
    InfoBar,
    InfoBarPosition,
    NavigationItemPosition,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    setThemeColor,
    InfoBarIcon,
    ToolButton,
    MessageBox
)


class InfoBarWithButton(InfoBar):
    """ Info bar with confirm and cancel buttons """
    confirmed = pyqtSignal()

    def __init__(self, icon: InfoBarIcon, title: str, content: str,
                 duration=1000, position=InfoBarPosition.TOP_RIGHT, parent=None):
        super().__init__(icon=icon, title=title, content=content, orient=Qt.Vertical,
                         isClosable=False, duration=duration, position=position, parent=parent)

        # 1. Icon Vertical Center
        self.hBoxLayout.itemAt(0).setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        # 2. Make Text Layout Expand
        # Item 0 is Icon, Item 1 is TextLayout. Set stretch for TextLayout to 1.
        self.hBoxLayout.setStretch(1, 1)

        # 3. Buttons (Vertical Layout)
        self.confirmButton = ToolButton(FIF.ACCEPT, self)
        self.confirmButton.setFixedSize(30, 30)

        self.cancelButton = ToolButton(FIF.CLOSE, self)
        self.cancelButton.setFixedSize(30, 30)

        self.buttonLayout = QVBoxLayout()
        self.buttonLayout.setSpacing(5)
        self.buttonLayout.setContentsMargins(20, 0, 10, 0)
        self.buttonLayout.addWidget(self.cancelButton)
        self.buttonLayout.addWidget(self.confirmButton)

        # 4. Add Button Layout to Main Horizontal Layout
        self.hBoxLayout.addLayout(self.buttonLayout)

        self.cancelButton.clicked.connect(self.close)
        self.confirmButton.clicked.connect(self.on_confirmButton_clicked)
        self.show()

    def on_confirmButton_clicked(self):
        self.confirmed.emit()
        self.close()
        

class MessageConfirmBox(MessageBox):
    def __init__(self, parent=None, title=None, content=None, show_cancel_btn=False):
        super().__init__(title, content, parent)  # 传递所有必要的参数

        self.yesButton.setText("确定")
        if show_cancel_btn:
            self.cancelButton.setText("取消")
            self.cancelButton.show()
        else:
            self.cancelButton.hide()