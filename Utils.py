import ctypes
import os
from enum import Enum


class WindowsScaleFactorType(Enum):
    SCALE_FACTOR_AUTO = "Auto"
    SCALE_FACTOR_100 = "100%"
    SCALE_FACTOR_125 = "125%"
    SCALE_FACTOR_150 = "150%"
    SCALE_FACTOR_175 = "175%"


class WindowsScaleFactorSetting:
    def __init__(self): 
        self.set_scale_factor()

    def cal_windows_scaling_factor(self):
        try:
            # 调用 Windows API 函数获取缩放比例
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            scaling_factor = user32.GetDpiForSystem()

            # 计算缩放比例
            return scaling_factor / 96.0

        except Exception as e:
            print("无法获取缩放比例，设置为1，错误:", e)
            return 1

    def get_scale_factor(self, scale_factor: WindowsScaleFactorType):
        if scale_factor == WindowsScaleFactorType.SCALE_FACTOR_AUTO:
            return [self.cal_windows_scaling_factor(), "Windows API"]
        else:
            # "100%"
            factor = int(scale_factor.value.replace("%", ""))/100.0
            return [factor, "用户设置"]

    def set_scale_factor(self, scale_factor: WindowsScaleFactorType=WindowsScaleFactorType.SCALE_FACTOR_AUTO):
        factor, identity = self.get_scale_factor(scale_factor)
        os.environ["QT_SCALE_FACTOR"] = str(factor)
        # logger.debug(f"已将环境变量 QT_SCALE_FACTOR 设为 {factor} (来源: {identity})")
        print(f"界面缩放比例已设置为 {factor} (来源: {identity})")
        