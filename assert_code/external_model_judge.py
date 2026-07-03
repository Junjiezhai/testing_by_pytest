# -*- coding: utf-8 -*-
"""
# @File    : external_model_judge.py
# @Date    : 2026-06-02
# @Author  : jeremyzhai
# @Description  : 外部模型细粒度检查清单评分器（可配置版本）
#
# 核心设计：
#   - 检查清单完全可配置（通过 YAML 文件定义维度、检查项）
#   - 阈值策略可扩展（支持自定义评分模式）
#   - 提示词模板可替换（支持自定义评估逻辑）
#
# 使用方式：
#   from assert_code.external_model_judge import (
#       ExternalModelJudge, ChecklistConfig
#   )
#
#   # 从 YAML 配置文件加载（默认自动加载）
#   judge = ExternalModelJudge()
#
#   # 使用自定义检查清单配置
#   config = ChecklistConfig.from_dict({
#       "dimensions": [{
#           "name": "事实层面",
#           "key": "fact",
#           "items": ["利率数字一致", "额度范围一致"]
#       }]
#   })
#   judge = ExternalModelJudge(config=config, strategy="balanced")
"""

import json
import os
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Union

Base_Path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(Base_Path)

from common.modelHttpAction import ModelHttpAction
from utils.handle_log import log


# ============================================================
# 基础枚举
# ============================================================

class CheckStatus(Enum):
    """检查项状态"""
    YES = "是"
    NO = "否"
    PARTIAL = "部分"


class Verdict(Enum):
    """综合判定结果"""
    PASS = "通过"
    CONDITIONAL_PASS = "条件通过"
    FAIL = "失败"


# ============================================================
# 检查项数据结构
# ============================================================

@dataclass
class ChecklistItem:
    """单个检查项"""
    dimension: str           # 所属维度key，如 "fact"
    dimension_name: str     # 维度显示名，如 "事实层面"
    name: str               # 检查项名称
    status: CheckStatus = CheckStatus.YES
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "dimension_name": self.dimension_name,
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
        }


@dataclass
class ChecklistResult:
    """检查清单结果"""
    items: List[ChecklistItem] = field(default_factory=list)
    verdict: Verdict = Verdict.PASS
    score: float = 0.0
    summary: str = ""

    def add_item(self, dimension: str, dimension_name: str, name: str,
                 status: CheckStatus, reason: str = "") -> None:
        self.items.append(ChecklistItem(
            dimension=dimension,
            dimension_name=dimension_name,
            name=name,
            status=status,
            reason=reason,
        ))

    def get_items_by_dimension(self, dimension: str) -> List[ChecklistItem]:
        return [item for item in self.items if item.dimension == dimension]

    def get_dimensions(self) -> List[str]:
        return list(dict.fromkeys(item.dimension for item in self.items))

    def has_status_in_dimension(self, dimension: str, status: CheckStatus) -> bool:
        return any(item.status == status for item in self.get_items_by_dimension(dimension))

    def count_status_in_dimension(self, dimension: str, status: CheckStatus) -> int:
        return sum(1 for item in self.get_items_by_dimension(dimension) if item.status == status)

    def count_status(self, status: CheckStatus) -> int:
        return sum(1 for item in self.items if item.status == status)

    def all_yes(self) -> bool:
        return all(item.status == CheckStatus.YES for item in self.items)

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict.value,
            "score": self.score,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


# ============================================================
# 阈值策略（策略模式）
# ============================================================

class ThresholdStrategy(ABC):
    """阈值策略抽象基类"""

    @abstractmethod
    def evaluate(self, result: ChecklistResult) -> None:
        """执行阈值判定，修改 result.verdict 和 result.summary"""
        pass


class RelaxedThreshold(ThresholdStrategy):
    """
    标准宽松（效率优先）
    规则：事实层面全"是"，其他无"否"
    任一事实项为"否" → 失败
    """

    def evaluate(self, result: ChecklistResult) -> None:
        # 获取各维度状态
        fact_yes = all(item.status == CheckStatus.YES
                        for item in result.get_items_by_dimension("fact"))
        logic_no = result.has_status_in_dimension("logic", CheckStatus.NO)
        safety_no = result.has_status_in_dimension("safety", CheckStatus.NO)

        if not fact_yes:
            result.verdict = Verdict.FAIL
            result.summary = "事实层面存在不符合项（标准宽松模式）"
        elif logic_no or safety_no:
            result.verdict = Verdict.CONDITIONAL_PASS
            result.summary = "逻辑或安全层面存在部分问题（标准宽松模式）"
        else:
            result.verdict = Verdict.PASS
            result.summary = "通过（标准宽松模式）"


class StrictThreshold(ThresholdStrategy):
    """
    标准严格（安全优先）
    规则：所有项全"是"
    任一"否"或超过两项"部分" → 失败
    """

    def evaluate(self, result: ChecklistResult) -> None:
        no_count = result.count_status(CheckStatus.NO)
        partial_count = result.count_status(CheckStatus.PARTIAL)

        if result.all_yes():
            result.verdict = Verdict.PASS
            result.summary = "通过（标准严格模式）"
        elif no_count > 0 or partial_count > 2:
            result.verdict = Verdict.FAIL
            result.summary = f"{'存在否定项' if no_count > 0 else '部分项过多'}（标准严格模式）"
        else:
            result.verdict = Verdict.CONDITIONAL_PASS
            result.summary = "部分通过（标准严格模式）"


class BalancedThreshold(ThresholdStrategy):
    """
    平衡模式（推荐）
    规则：事实全"是"，逻辑/安全无"否"
    事实"否"或安全"否" → 一票否决
    """

    def evaluate(self, result: ChecklistResult) -> None:
        fact_no = result.has_status_in_dimension("fact", CheckStatus.NO)
        safety_no = result.has_status_in_dimension("safety", CheckStatus.NO)
        logic_no = result.has_status_in_dimension("logic", CheckStatus.NO)

        if fact_no or safety_no:
            result.verdict = Verdict.FAIL
            result.summary = "事实或安全层面存在严重问题（平衡模式）"
        elif logic_no:
            result.verdict = Verdict.CONDITIONAL_PASS
            result.summary = "逻辑层面存在部分问题（平衡模式）"
        else:
            result.verdict = Verdict.PASS
            result.summary = "通过（平衡模式）"


class CustomThreshold(ThresholdStrategy):
    """
    自定义阈值策略
    通过传入回调函数实现任意自定义逻辑
    """

    def __init__(self, evaluator: Callable[[ChecklistResult], tuple]):
        """
        Args:
            evaluator: 回调函数，接收 ChecklistResult，返回 (Verdict, summary)
        """
        self.evaluator = evaluator

    def evaluate(self, result: ChecklistResult) -> None:
        verdict, summary = self.evaluator(result)
        result.verdict = verdict
        result.summary = summary


# ============================================================
# 检查清单配置
# ============================================================

@dataclass
class DimensionConfig:
    """维度配置"""
    name: str       # 显示名称，如 "事实层面"
    key: str        # 标识key，如 "fact"
    items: List[str]  # 检查项列表


@dataclass
class ChecklistConfig:
    """检查清单完整配置"""
    dimensions: List[DimensionConfig]
    description: str = ""           # 清单描述
    status_options: List[str] = field(default_factory=lambda: ["是", "否", "部分"])

    @classmethod
    def from_dict(cls, data: dict) -> 'ChecklistConfig':
        """从字典创建配置"""
        dimensions = [
            DimensionConfig(**dim)
            for dim in data.get("dimensions", [])
        ]
        return cls(
            dimensions=dimensions,
            description=data.get("description", ""),
            status_options=data.get("status_options", ["是", "否", "部分"]),
        )

    @classmethod
    def from_json(cls, json_path: str) -> 'ChecklistConfig':
        """从JSON文件创建配置"""
        with open(json_path, 'r', encoding='utf-8') as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'ChecklistConfig':
        """从 YAML 文件创建配置"""
        from utils.handle_yaml import read_yaml_data
        data = read_yaml_data(yaml_path)
        if not data:
            raise ValueError(f"无法读取 YAML 配置文件: {yaml_path}")
        checklist_data = data.get('checklist', data)
        return cls.from_dict(checklist_data)

    def to_dict(self) -> dict:
        return {
            "dimensions": [
                {"name": dim.name, "key": dim.key, "items": dim.items}
                for dim in self.dimensions
            ],
            "description": self.description,
            "status_options": self.status_options,
        }


# ============================================================
# 提示词模板管理
# ============================================================

class PromptTemplate:
    """提示词模板"""

    @staticmethod
    def build(config: ChecklistConfig, actual_answer: str, expected_answer: str) -> str:
        """构建检查清单评估提示词"""

        # 构建检查项列表
        checklist_lines = []
        for dim in config.dimensions:
            checklist_lines.append(f"[{dim.name}]")
            for item in dim.items:
                checklist_lines.append(f"□ {item}（{'/'.join(config.status_options)}）")
            checklist_lines.append("")

        # 构建JSON输出格式示例
        json_example = {}
        for dim in config.dimensions:
            json_example[dim.key] = {}
            for item in dim.items:
                json_example[dim.key][item] = {"status": "是", "reason": "..."}

        checklist_text = '\n'.join(checklist_lines)

        return f"""你是一个话术质量检查员，需要对实际回复进行逐条检查。

请逐项检查，每项从以下选项中选择一项：{' / '.join(config.status_options)}

{checklist_text}
评分标准：
- "是"：完全符合标准
- "否"：明显不符合或错误
- "部分"：部分符合但存在差异

标准话术：
{expected_answer}

实际话术：
{actual_answer}

返回要求：
只返回JSON，不要返回markdown，不要返回额外解释。
JSON格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""


# ============================================================
# 检查清单评分器
# ============================================================

class ExternalModelJudge:
    """
    外部模型细粒度检查清单评分器（可扩展版本）
    """

    # 支持的阈值策略映射
    BUILT_IN_STRATEGIES = {
        "relaxed": RelaxedThreshold,
        "strict": StrictThreshold,
        "balanced": BalancedThreshold,
    }

    def __init__(
        self,
        config: Optional[ChecklistConfig] = None,
        strategy: Optional[Union[str, ThresholdStrategy]] = None,
        model_name: str = 'deepseek-v4-pro',
        auth_token: Optional[str] = None,
        base_url: Optional[str] = None,
        *,
        use_knowledge_base: bool = True,
        inject_knowledge_as_system: bool = True,
        config_path: Optional[str] = None,
        max_tokens: int = 8192,
        knowledge_file: Optional[str] = None,
    ):
        """
        初始化检查清单评分器

        Args:
            config: 检查清单配置（必须提供或通过 config_path 从 YAML 加载）
            strategy: 阈值策略，可以是策略名称(str)或自定义策略实例
            model_name: 模型名称
            auth_token: 认证 Token
            base_url: 模型接口域名
            use_knowledge_base: 是否使用知识库增强评估（默认 True）
            inject_knowledge_as_system: 是否将知识库注入系统提示词（默认 True）。
                True:  使用系统提示词注入完整知识库（评估更精准，但 Token 消耗高）
                False: 使用传统方式，提示词更简洁（评估较快，适合调试）
            config_path: YAML 配置文件路径，默认从项目 config/model_intent_checklist.yaml 加载
            max_tokens: 模型最大输出 token 数（默认 8192，防止检查项过多时思考耗尽）
            knowledge_file: 自定义知识库文件路径（可选，默认加载 config/model_knowledge_base.yaml）
        """
        # 尝试从 YAML 加载配置
        yaml_config = None
        yaml_strategy = None
        if config is None:
            if config_path is None:
                config_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'config', 'model_intent_checklist.yaml'
                )
            if not os.path.exists(config_path):
                raise FileNotFoundError(f"检查清单配置文件不存在: {config_path}")
            from utils.handle_yaml import read_yaml_data
            yaml_data = read_yaml_data(config_path)
            if not yaml_data:
                raise ValueError(f"检查清单配置文件内容为空或解析失败: {config_path}")
            checklist_data = yaml_data.get('checklist')
            if not checklist_data:
                raise ValueError(f"检查清单配置文件中缺少 'checklist' 节点: {config_path}")
            yaml_config = ChecklistConfig.from_dict(checklist_data)
            yaml_strategy = yaml_data.get('threshold_strategy')
            log.info(f"已从 YAML 加载检查清单配置: {config_path}")

        self.config = config or yaml_config
        self.max_tokens = max_tokens
        self.model = ModelHttpAction(
            model_name=model_name,
            auth_token=auth_token,
            base_url=base_url,
        )

        # 初始化知识库（可选）
        self.knowledge_base = None
        self.inject_knowledge_as_system = inject_knowledge_as_system
        # 缓存：意图 -> 系统提示词
        self._system_prompt_cache = {}
        if use_knowledge_base:
            try:
                from assert_code.knowledge_base import KnowledgeBase
                self.knowledge_base = KnowledgeBase(knowledge_file=knowledge_file)
            except Exception as e:
                log.warning(f"知识库初始化失败，将不使用知识库增强: {e}")

        # 设置阈值策略（YAML 配置优先级低于显式传入）
        effective_strategy = strategy or yaml_strategy
        if isinstance(effective_strategy, str):
            strategy_class = self.BUILT_IN_STRATEGIES.get(effective_strategy.lower())
            if not strategy_class:
                raise ValueError(f"未知的阈值策略: {effective_strategy}，可选: {list(self.BUILT_IN_STRATEGIES.keys())}")
            self.strategy = strategy_class()
        elif isinstance(effective_strategy, ThresholdStrategy):
            self.strategy = effective_strategy
        elif effective_strategy is None:
            raise ValueError("必须配置 threshold_strategy 或传入 strategy 参数")
        else:
            raise ValueError(f"strategy 必须是字符串或 ThresholdStrategy 实例")

    def _parse_response(self, text: str) -> Dict[str, Any]:
        """解析模型返回的检查清单结果"""
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise ValueError(f'无法解析检查清单结果: {text}')

        # 规范化结果
        parsed = {}
        for dim in self.config.dimensions:
            dim_data = result.get(dim.key, {})
            parsed[dim.key] = {}
            for item_name in dim.items:
                item_data = dim_data.get(item_name, {})
                if isinstance(item_data, dict):
                    parsed[dim.key][item_name] = {
                        "status": item_data.get("status", "是"),
                        "reason": item_data.get("reason", ""),
                    }
                else:
                    parsed[dim.key][item_name] = {"status": str(item_data), "reason": ""}
        return parsed

    def _apply_threshold(self, parsed: Dict[str, Any]) -> ChecklistResult:
        """应用阈值判定"""
        result = ChecklistResult()

        # 收集检查项
        for dim in self.config.dimensions:
            dim_data = parsed.get(dim.key, {})
            for item_name, item_data in dim_data.items():
                status_str = item_data.get("status", "是")
                status = CheckStatus(status_str) if status_str in ["是", "否", "部分"] else CheckStatus.YES
                result.add_item(
                    dimension=dim.key,
                    dimension_name=dim.name,
                    name=item_name,
                    status=status,
                    reason=item_data.get("reason", ""),
                )

        # 计算得分
        if result.items:
            score = sum(
                1 if item.status == CheckStatus.YES else (0.5 if item.status == CheckStatus.PARTIAL else 0)
                for item in result.items
            )
            result.score = score / len(result.items)

        # 应用阈值策略
        self.strategy.evaluate(result)

        return result

    def evaluate(self, actual_answer: str, expected_answer: str) -> ChecklistResult:
        """
        执行检查清单评估

        Args:
            actual_answer: 实际话术
            expected_answer: 标准话术

        Returns:
            检查清单结果对象
        """
        # 构建提示词
        prompt = PromptTemplate.build(self.config, actual_answer, expected_answer)

        # 调用模型（指定 max_tokens 防止检查项过多时思考耗尽）
        text = self.model.chat(prompt, desc="【检查清单评估】", max_tokens=self.max_tokens)

        # 解析结果
        parsed = self._parse_response(text)

        # 应用阈值
        result = self._apply_threshold(parsed)

        log.info(f"检查清单评估完成: verdict={result.verdict.value}, score={result.score:.2f}")
        return result

    def evaluate_with_custom_strategy(
        self,
        actual_answer: str,
        expected_answer: str,
        strategy: Callable[[ChecklistResult], tuple],
    ) -> ChecklistResult:
        """
        使用自定义策略评估（临时替换策略，不影响已有策略）

        Args:
            actual_answer: 实际话术
            expected_answer: 标准话术
            strategy: 自定义评估函数，接收 ChecklistResult，返回 (Verdict, summary)

        Returns:
            检查清单结果对象
        """
        # 保存原策略
        original_strategy = self.strategy
        # 临时替换
        self.strategy = CustomThreshold(strategy)
        try:
            result = self.evaluate(actual_answer, expected_answer)
        finally:
            # 恢复原策略
            self.strategy = original_strategy
        return result

    def _build_similarity_prompt(self, actual_answer: str, expected_answer: str) -> str:
        """构建语义相似度评估提示词"""
        return f"""你是一名语义相似度评估专家。请比较"实际输出"与"标准答案"在语义上的相似程度，并给出 0-100 的整数评分。

评分标准：
- 100 分：语义完全一致，核心信息、结论、意图完全匹配
- 80-99 分：语义高度相似，核心信息一致，仅在措辞、格式、细节描述上存在微小差异
- 60-79 分：语义基本相似，核心结论大体一致，但存在部分信息遗漏或偏差
- 40-59 分：语义部分相似，有部分重叠信息，但核心结论存在明显差异
- 20-39 分：语义相似度较低，仅有少量相关信息
- 0-19 分：语义基本不相关或完全无关

注意：评分应关注"语义"而非"字面"，即使措辞不同，只要意思一致就应给高分。

标准答案：
{expected_answer}

实际输出：
{actual_answer}

返回要求：
只返回JSON，不要返回markdown，不要返回额外解释。
JSON格式如下：
{{
  "score": <0-100整数>,
  "reason": "评分理由的简要说明"
}}
"""

    def similarity_score(self, actual_answer: str, expected_answer: str, *,
                            intent: str = None) -> 'SemanticSimilarityResult':
        """
        评估实际输出与标准答案的语义相似度，返回 0-100 的评分

        Args:
            actual_answer: 实际模型输出
            expected_answer: 标准答案
            intent: 意图分类（可选，用于注入知识库上下文）

        Returns:
            SemanticSimilarityResult 对象
        """
        # 根据配置选择提示词构建方式
        if intent and self.knowledge_base and self.inject_knowledge_as_system:
            # 使用系统提示词注入知识库（评估更精准，但 Token 消耗高）
            system_prompt = self._get_system_prompt(intent)
            user_prompt = self._build_user_prompt(actual_answer, expected_answer)
            text = self.model.chat(
                user_prompt,
                system_prompt=system_prompt,
                desc="【语义相似度评估-知识注入】",
                max_tokens=self.max_tokens,
            )
        elif intent and self.knowledge_base:
            # 知识库可用但不注入系统提示词，使用传统方式构建完整提示词
            prompt = self._build_knowledge_prompt(intent, actual_answer, expected_answer)
            text = self.model.chat(
                prompt,
                desc="【语义相似度评估-知识传统】",
                max_tokens=self.max_tokens,
            )
        else:
            # 无知识库，使用传统相似度评估
            prompt = self._build_similarity_prompt(actual_answer, expected_answer)
            text = self.model.chat(
                prompt,
                desc="【语义相似度评估】",
                max_tokens=self.max_tokens,
            )

        # 解析JSON响应
        result = {}
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

        score = result.get("score", 0) if isinstance(result, dict) else 0
        reason = result.get("reason", "") if isinstance(result, dict) else ""

        # 确保 score 为合法整数
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 0
        score = max(0, min(100, score))

        log.info(f"语义相似度评分: {score}/100, reason={reason}")
        return SemanticSimilarityResult(score=score, reason=reason)

    def _get_system_prompt(self, intent: str) -> str:
        """
        获取（或构建并缓存）系统提示词

        系统提示词包含：角色定义 + 通用规则 + 意图知识
        这部分内容稳定，可以缓存复用。

        Args:
            intent: 意图分类

        Returns:
            系统提示词字符串
        """
        # 检查缓存
        if intent in self._system_prompt_cache:
            return self._system_prompt_cache[intent]

        # 构建系统提示词
        system_prompt = self._build_system_prompt(intent)

        # 缓存
        self._system_prompt_cache[intent] = system_prompt
        return system_prompt

    def _build_system_prompt(self, intent: str) -> str:
        """
        构建系统提示词（包含角色定义、通用规则、意图知识）

        Args:
            intent: 意图分类

        Returns:
            系统提示词字符串
        """
        if self.knowledge_base is None:
            return "你是一名语义相似度评估专家。"

        # 通用规则
        common_rules = self.knowledge_base.get_common_rules()

        # 意图规则
        intent_rules = self.knowledge_base.get_intent_rules(intent)

        return f"""你是一名信贷客服话术质量评估专家。你的任务是基于领域知识，评估客服回复与标准答案的语义相似度及质量。

---
【角色定义】
你是一位熟悉信贷客服业务的专业评估员，精通金融合规、客户服务规范、话术标准等领域知识。

---
【通用评估规则】
{common_rules}

---
【当前意图评估规则】
{intent_rules}

---
【评分标准】
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
"""

    def _build_user_prompt(self, actual_answer: str, expected_answer: str) -> str:
        """
        构建用户提示词（仅包含待评估的具体内容）

        Args:
            actual_answer: 实际模型输出
            expected_answer: 标准答案

        Returns:
            用户提示词字符串
        """
        return f"""请基于上述领域知识，评估以下回复的质量并给出评分。

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

    def _build_knowledge_prompt(self, intent: str, actual_answer: str, expected_answer: str) -> str:
        """
        构建注入知识的评估提示词（兼容旧版本，无 system prompt 时回退使用）

        Args:
            intent: 意图分类
            actual_answer: 实际模型输出
            expected_answer: 标准答案

        Returns:
            注入知识的评估提示词
        """
        if self.knowledge_base is None:
            return self._build_similarity_prompt(actual_answer, expected_answer)
        return self.knowledge_base.build_eval_prompt(intent, actual_answer, expected_answer)


# ============================================================
# 语义相似度结果
# ============================================================

@dataclass
class SemanticSimilarityResult:
    """语义相似度评估结果"""
    score: int   # 0-100 的整数评分
    reason: str  # 评分理由

    def is_pass(self, threshold: int = 80) -> bool:
        """判断是否达到指定阈值"""
        return self.score >= threshold

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "reason": self.reason,
        }

    def __str__(self) -> str:
        return f"SemanticSimilarityResult(score={self.score}, reason='{self.reason}')"

    def __repr__(self) -> str:
        return self.__str__()


# ============================================================
# 快捷函数
# ============================================================

def judge_answer(
    actual_answer: str,
    expected_answer: str,
    *,
    config: Optional[ChecklistConfig] = None,
    strategy: Optional[Union[str, ThresholdStrategy]] = None,
    model_name: str = 'deepseek-v4-pro',
) -> ChecklistResult:
    """
    快捷函数：直接对回复进行细粒度检查清单评估

    Args:
        actual_answer: 实际话术
        expected_answer: 标准话术
        config: 检查清单配置，未提供时自动从 YAML 配置文件加载
        strategy: 阈值策略
        model_name: 模型名称

    Returns:
        检查清单结果
    """
    judge = ExternalModelJudge(config=config, strategy=strategy, model_name=model_name)
    return judge.evaluate(actual_answer, expected_answer)


def similarity_score(
    actual_answer: str,
    expected_answer: str,
    *,
    model_name: str = 'deepseek-v4-pro',
) -> SemanticSimilarityResult:
    """
    快捷函数：评估实际输出与标准答案的语义相似度

    Args:
        actual_answer: 实际模型输出
        expected_answer: 标准答案
        model_name: 模型名称

    Returns:
        SemanticSimilarityResult 对象
    """
    judge = ExternalModelJudge(config=None, strategy=None, model_name=model_name)
    return judge.similarity_score(actual_answer, expected_answer)


# ============================================================
# 使用示例
# ============================================================

if __name__ == '__main__':
    # ====== 示例1：从配置文件加载 ======
    print("=" * 60)
    print("示例1：从配置文件加载 + 平衡模式")
    print("=" * 60)

    judge = ExternalModelJudge(strategy="balanced")
    print(f"检查清单维度: {[dim.key for dim in judge.config.dimensions]}")
    print(f"检查项数量: {sum(len(dim.items) for dim in judge.config.dimensions)}")

    # ====== 示例2：自定义检查清单（完全自定义） ======
    print("\n" + "=" * 60)
    print("示例2：自定义检查清单")
    print("=" * 60)

    custom_config = ChecklistConfig(
        dimensions=[
            DimensionConfig(
                name="合规性",
                key="compliance",
                items=["无违规承诺", "符合监管要求"]
            ),
            DimensionConfig(
                name="准确性",
                key="accuracy",
                items=["数字准确", "逻辑无误"]
            ),
        ],
        description="自定义合规检查清单",
    )

    custom_judge = ExternalModelJudge(
        config=custom_config,
        strategy="strict",
    )
    print(f"自定义维度: {[dim.key for dim in custom_judge.config.dimensions]}")

    # ====== 示例3：使用 JSON 配置 ======
    print("\n" + "=" * 60)
    print("示例3：从JSON配置加载")
    print("=" * 60)

    # 先保存配置到JSON
    config_dict = custom_config.to_dict()
    print(f"JSON配置: {json.dumps(config_dict, ensure_ascii=False, indent=2)}")

    # 从JSON加载
    # loaded_config = ChecklistConfig.from_dict(config_dict)
    # loaded_judge = ExternalModelJudge(config=loaded_config)

    # ====== 示例4：自定义阈值策略 ======
    print("\n" + "=" * 60)
    print("示例4：自定义阈值策略")
    print("=" * 60)

    def my_custom_evaluator(result: ChecklistResult) -> tuple:
        """自定义评分：只要有任何一项为"否"就失败"""
        if result.count_status(CheckStatus.NO) > 0:
            return Verdict.FAIL, "存在不符合项（自定义策略）"
        return Verdict.PASS, "通过（自定义策略）"

    custom_strategy_judge = ExternalModelJudge(
        config=custom_config,
        strategy=CustomThreshold(my_custom_evaluator),
    )
    print(f"自定义策略类型: {type(custom_strategy_judge.strategy).__name__}")

    # ====== 示例5：临时使用不同策略评估 ======
    print("\n" + "=" * 60)
    print("示例5：临时切换策略评估（不修改原有策略）")
    print("=" * 60)

    def temp_strategy(result: ChecklistResult) -> tuple:
        """临时策略"""
        if result.count_status(CheckStatus.NO) >= 2:
            return Verdict.FAIL, "超过2项不符合"
        return Verdict.CONDITIONAL_PASS, "部分通过"

    # 假设已有 actual 和 expected
    # result = custom_judge.evaluate_with_custom_strategy(
    #     actual_answer="...",
    #     expected_answer="...",
    #     strategy=temp_strategy,
    # )
    print("可以使用 evaluate_with_custom_strategy() 临时切换策略")
