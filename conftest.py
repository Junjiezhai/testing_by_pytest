# -*- coding: utf-8 -*-
"""
pytest 全局配置
"""
import sys

# Windows 下强制 stdout/stderr 使用 UTF-8，防止中文乱码
# 使用 reconfigure() 避免直接替换 sys.stdout 导致 pytest 内部错误
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError, ValueError):
        pass


def pytest_configure(config):
    pass
