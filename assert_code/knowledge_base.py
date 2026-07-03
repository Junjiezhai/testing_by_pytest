# -*- coding: utf-8 -*-
"""
# @File    : knowledge_base.py
# @Date    : 2026-06-05
# @Author  : jeremyzhai
# @Description : 知识库管理器 — 为外部模型评估提供领域知识上下文
#
# 使用方式：
#   from assert_code.knowledge_base import KnowledgeBase
#   kb = KnowledgeBase()
#
#   # 获取通用规则
#   common_rules = kb.get_common_rules()
#
#   # 获取特定意图规则
#   intent_rules = kb.get_intent_rules("提额降息咨询类")
#
#   # 构建评估提示词（注入知识）
#   prompt = kb.build_eval_prompt(
#       intent="提额降息咨询类",
#       actual_answer="用户实际回复...",
#       expected_answer="标准答案..."
#   )
"""

import os
from typing import Dict, List, Optional

from utils.handle_log import log


class KnowledgeBase:
    """知识库管理器"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """单例模式，避免重复加载"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, knowledge_file: str = None):
        # 支持传入不同的知识库路径时重新加载（非单例行为）
        if knowledge_file and knowledge_file != getattr(self, 'knowledge_file', None):
            self.knowledge_file = knowledge_file
            self._knowledge = {}
            self._load()
            KnowledgeBase._initialized = True
        elif KnowledgeBase._initialized:
            return
        else:
            self.knowledge_file = knowledge_file or self._default_knowledge_file()
            self._knowledge = {}
            self._load()
            KnowledgeBase._initialized = True

    @classmethod
    def _default_knowledge_file(cls) -> str:
        """默认知识库文件路径"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, 'config', 'model_knowledge_base.yaml')

    def _load(self):
        """加载知识库"""
        try:
            from utils.handle_yaml import read_yaml_data
            self._knowledge = read_yaml_data(self.knowledge_file) or {}
            log.info(f"知识库加载成功：{self.knowledge_file}")
        except Exception as e:
            log.warning(f"知识库加载失败：{e}，使用空知识库")
            self._knowledge = {}

    # ============================================================
    # 知识检索 API
    # ============================================================

    def get_common_rules(self) -> str:
        """获取通用评估规则"""
        common = self._knowledge.get('common', {})
        if not common:
            return ""
        lines = ["【通用评估规则】"]
        if 'tone' in common:
            lines.append(f"语气要求：\n{common['tone']}")
        if 'compliance' in common:
            lines.append(f"合规要求：\n{common['compliance']}")
        if 'taboos' in common:
            lines.append("禁忌事项：")
            for item in common['taboos']:
                lines.append(f"  - {item}")
        return '\n'.join(lines)

    def get_intent_rules(self, intent: str) -> str:
        """获取特定意图的评估规则"""
        intents = self._knowledge.get('intents', {})
        intent_data = intents.get(intent, {})

        if not intent_data:
            log.warning(f"知识库中未找到意图[{intent}]的规则")
            return ""

        lines = [f"【意图：{intent}】"]
        lines.append(f"定义：{intent_data.get('description', 'N/A')}")

        # 关键要素
        key_elements = intent_data.get('key_elements', [])
        if key_elements:
            lines.append("关键要素：")
            for item in key_elements:
                lines.append(f"  - {item}")

        # 应答结构
        structure = intent_data.get('structure', '')
        if structure:
            lines.append(f"应答结构：\n{structure}")

        # 语气要求
        tone = intent_data.get('tone', '')
        if tone:
            lines.append(f"语气要求：{tone}")

        # 禁忌事项
        taboos = intent_data.get('taboos', [])
        if taboos:
            lines.append("禁忌事项：")
            for item in taboos:
                lines.append(f"  - {item}")

        # 评分维度
        dimensions = intent_data.get('dimensions', [])
        if dimensions:
            lines.append("评分维度：")
            for dim in dimensions:
                lines.append(f"  - {dim.get('name', 'N/A')}（权重{dim.get('weight', 0)}%）：{dim.get('criteria', 'N/A')}")

        return '\n'.join(lines)

    def get_dimensions(self, intent: str) -> List[Dict]:
        """获取意图的评分维度"""
        intents = self._knowledge.get('intents', {})
        intent_data = intents.get(intent, {})
        return intent_data.get('dimensions', [])

    # ============================================================
    # 提示词构建
    # ============================================================

    def build_eval_prompt(self, intent: str, actual_answer: str, expected_answer: str) -> str:
        """
        构建注入知识的评估提示词

        Args:
            intent: 意图分类
            actual_answer: 实际模型回复
            expected_answer: 标准答案

        Returns:
            增强后的评估提示词
        """
        common_rules = self.get_common_rules()
        intent_rules = self.get_intent_rules(intent)

        return f"""你是一名信贷客服话术质量评估专家。请基于以下领域知识，评估实际回复与标准答案的语义相似度及质量。

---
【领域知识】
{common_rules}

{intent_rules}

---
【评估标准】
- 100 分：语义完全一致，且完全符合领域知识中的结构、语气、合规要求
- 80-99 分：语义高度相似，符合关键要素，仅在措辞、格式上有微小差异
- 60-79 分：语义基本相似，核心结论一致，但缺少部分关键要素或存在轻微合规问题
- 40-59 分：语义部分相似，有部分重叠信息，但缺少重要关键要素
- 20-39 分：语义相似度较低，仅有少量相关信息
- 0-19 分：语义基本不相关或完全无关

【特别说明】
- 评分应关注"语义"而非"字面"，即使措辞不同，只要意思一致就应给高分
- 必须同时满足领域知识中的结构要求和语气要求
- 如有触碰禁忌事项，应大幅降低评分

---
【标准答案】
{expected_answer}

---
【实际回复】
{actual_answer}

---
【返回要求】
只返回JSON，不要返回markdown，不要返回额外解释。
JSON格式如下：
{{
  "score": <0-100整数>,
  "reason": "评分理由的简要说明，需指出优点和不足"
}}
"""

    def build_checklist_prompt(self, intent: str, actual_answer: str, expected_answer: str) -> str:
        """
        构建注入知识的检查清单提示词

        Args:
            intent: 意图分类
            actual_answer: 实际模型回复
            expected_answer: 标准答案

        Returns:
            增强后的检查清单提示词
        """
        common_rules = self.get_common_rules()
        intent_rules = self.get_intent_rules(intent)
        dimensions = self.get_dimensions(intent)

        # 构建检查清单项
        checklist_items = []
        for dim in dimensions:
            checklist_items.append(f"□ {dim.get('name')}：{dim.get('criteria')}")

        return f"""你是一名话术质量检查员。请基于以下领域知识，对实际回复进行逐条检查。

---
【领域知识】
{common_rules}

{intent_rules}

---
【检查清单】
{chr(10).join(checklist_items) if checklist_items else '请根据领域知识中的关键要素逐项检查'}

---
【标准话术】
{expected_answer}

【实际话术】
{actual_answer}

---
【返回要求】
只返回JSON，不要返回markdown，不要返回额外解释。
JSON格式如下：
{{
  "总体评分": <0-100整数>,
  "评分理由": "简要说明",
  "检查项": [
    {{
      "维度": "检查项名称",
      "状态": "是/否/部分",
      "说明": "具体原因"
    }}
  ]
}}
"""

    # ============================================================
    # 快捷方法
    # ============================================================

    @classmethod
    def quick_eval_prompt(cls, intent: str, actual_answer: str, expected_answer: str) -> str:
        """快速构建评估提示词（无需实例化）"""
        kb = cls()
        return kb.build_eval_prompt(intent, actual_answer, expected_answer)

    @classmethod
    def quick_checklist_prompt(cls, intent: str, actual_answer: str, expected_answer: str) -> str:
        """快速构建检查清单提示词（无需实例化）"""
        kb = cls()
        return kb.build_checklist_prompt(intent, actual_answer, expected_answer)


# ============================================================
# 使用示例
# ============================================================

if __name__ == '__main__':
    # 示例1：获取通用规则
    kb = KnowledgeBase()
    print("=" * 60)
    print("通用规则：")
    print(kb.get_common_rules())

    # 示例2：获取特定意图规则
    print("\n" + "=" * 60)
    print("提额降息咨询类规则：")
    print(kb.get_intent_rules("提额降息咨询类"))

    # 示例3：构建评估提示词
    print("\n" + "=" * 60)
    print("评估提示词预览：")
    prompt = kb.build_eval_prompt(
        intent="提额降息咨询类",
        actual_answer="您好，您的额度已提升至50000元。",
        expected_answer="您好，您当前可用额度为50000元，如需提额可尝试..."
    )
    print(prompt[:500] + "...")
