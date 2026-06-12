# -*- coding: utf-8 -*-
"""
批量断言数据收集器

作用：
    在测试执行阶段收集实际输出数据，供 session finish 阶段批量断言使用。

设计：
    - 线程安全（threading.Lock）
    - 单例模式（通过模块级全局变量）
    - 支持保存到临时文件和从文件加载

使用方式：
    from utils.batch_assert_collector import BatchAssertCollector, batch_collector

    # 收集数据
    batch_collector.add({
        'case_id': 'MIR_0001',
        'intent': '提额降息咨询类',
        'actual_answer': '...',
        'expected_answer': '...',
        'similarity_threshold': 70,
    })

    # 获取所有数据
    items = batch_collector.get_all()

    # 清空
    batch_collector.clear()
"""

import json
import os
import threading
from typing import List


class BatchAssertCollector:
    """
    批量断言数据收集器（线程安全 + 单例模式）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._items = []
                    cls._instance._lock = threading.Lock()
        return cls._instance

    def add(self, item: dict):
        """添加一条待断言数据（线程安全）"""
        with self._lock:
            self._items.append(item)

    def get_all(self) -> List[dict]:
        """获取所有待断言数据（线程安全，返回副本）"""
        with self._lock:
            return self._items.copy()

    def clear(self):
        """清空收集器（线程安全）"""
        with self._lock:
            self._items.clear()

    @property
    def count(self) -> int:
        """获取已收集数据条数"""
        with self._lock:
            return len(self._items)

    def is_empty(self) -> bool:
        """检查是否为空"""
        return self.count == 0

    def save_to_file(self, filepath: str):
        """
        保存到临时 JSON 文件（供 session finish 读取）

        :param filepath: 文件路径
        """
        with self._lock:
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self._items, f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_file(cls, filepath: str) -> List[dict]:
        """
        从文件加载收集的数据

        :param filepath: 文件路径
        :return: 数据列表
        """
        if not os.path.exists(filepath):
            return []
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)


# 全局收集器实例（单例）
batch_collector = BatchAssertCollector()
