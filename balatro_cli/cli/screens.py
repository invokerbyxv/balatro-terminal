"""兼容入口：App 已拆分到 screens_pkg 包，这里保留原有导入路径。"""
from .screens_pkg import App, run

__all__ = ["App", "run"]
