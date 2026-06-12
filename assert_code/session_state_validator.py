# -*- coding: utf-8 -*-
"""
# @File    : session_state_validator.py
# @Date    : 2026-06-09
# @Author  : jeremyzhai
# @Description  : 信贷客服会话状态转移合规性验证器 & 意图漂移率评估工具

基于 `docs/session_state_transition.md` v1.1 中定义的完整状态转移矩阵，
对单轮/多轮模型对话进行：
  1. 状态转移合规性判定（单轮 & 多轮）
  2. 意图漂移率（Intent Drift Rate）量化评估
  3. 漂移模式分析与报告生成

使用方式：
    from assert_code.session_state_validator import SessionStateValidator

    validator = SessionStateValidator()

    # 单轮验证
    result = validator.validate_single_turn(
        current_state='INIT',
        detected_intent='提额业务咨询',
    )
    print(result)  # {'is_valid': True, 'expected_next': 'TL_YWZX', ...}

    # 多轮验证
    trajectory = [
        {'turn': 1, 'current_state': 'INIT',  'detected_intent': '提额业务咨询'},
        {'turn': 2, 'current_state': 'TL_YWZX', 'detected_intent': '提额准入条件咨询'},
        {'turn': 3, 'current_state': 'TL_ZRTJ', 'detected_intent': '借款操作咨询'},  # 漂移！
    ]
    multi_result = validator.validate_multi_turn(trajectory)

    # 漂移率分析
    drift_report = validator.analyze_drift(trajectory)
"""

import json
import os
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================================
# 枚举定义
# ============================================================

class ValidationMode(Enum):
    """验证模式"""
    STRICT = "strict"         # 严格模式：转移必须精确匹配
    LENIENT = "lenient"       # 宽松模式：允许回到 INIT 视为合法降级
    CATEGORY = "category"     # 分类模式：只校验业务大类（TL/JX/JK/ZX 等）


class DriftSeverity(Enum):
    """漂移严重程度"""
    NONE = "none"             # 无漂移
    MILD = "mild"             # 轻微：同级业务域内跳转（如 TL_YWZX → TL_CQZX 跳过中间态）
    MODERATE = "moderate"     # 中等：跨业务域但仍在信贷范围内（如 TL_* → ZX_*）
    SEVERE = "severe"         # 严重：跨到不相关域（如 TL_* → FY_LTXZ）
    CRITICAL = "critical"     # 致命：跳转到风险/人工等终态之外不可达状态


# ============================================================
# 数据类
# ============================================================

@dataclass
class TransitionResult:
    """单次转移验证结果"""
    turn: int                                    # 轮次编号（单轮为 1）
    current_state: str                           # 当前状态
    detected_intent: str                         # 检测到的用户意图
    expected_next_state: Optional[str]           # 期望的下一状态
    is_valid: bool                               # 是否合法转移
    drift_severity: DriftSeverity                # 漂移严重程度
    matched_rule: Optional[str]                  # 匹配到的转移规则描述
    detail: str = ''                             # 详细信息


@dataclass
class MultiTurnResult:
    """多轮验证结果"""
    total_turns: int                             # 总轮数
    valid_turns: int                             # 合法转移轮数
    invalid_turns: int                           # 非法转移轮数
    drift_rate: float                            # 漂移率（非法轮数/总轮数）
    severity_distribution: Dict[str, int]        # 严重程度分布
    transitions: List[TransitionResult]          # 每轮转移结果
    summary: str = ''                            # 汇总描述


@dataclass
class DriftReport:
    """意图漂移分析报告"""
    total_turns: int
    drift_rate: float                            # 总漂移率
    hard_drift_rate: float                       # 硬漂移率（moderate+severe+critical）
    soft_drift_rate: float                       # 软漂移率（mild）
    category_drift_count: int                    # 跨类别漂移次数
    severity_counts: Dict[str, int]              # 严重程度分布
    top_drift_patterns: List[Tuple[str, str, int]]  # 高频漂移模式
    drift_transitions: List[TransitionResult]    # 所有漂移转移详情
    report_text: str = ''                        # 可读报告文本


# ============================================================
# 状态转移矩阵（程序化定义）
# ============================================================

class StateTransitionMatrix:
    """
    信贷客服会话状态转移矩阵

    数据来源：docs/session_state_transition.md v1.1

    三层规则：
      1. P0 全局规则 — 从任意状态触发，优先级最高
      2. 主流程规则 — 特定状态下的业务流转
      3. 兜底规则   — 无匹配时返回 INIT
    """

    # ----------------------------------------------------------
    # P0 全局转移规则（任意状态均可触发）
    # ----------------------------------------------------------
    GLOBAL_TRANSITIONS: Dict[str, str] = {
        # 转人工（最高优先级）
        '用户主动要求转人工':      'RG_BZSQ',
        '用户情绪升级':            'RG_QX_SJ',
        # 风险合规
        '违规操作':                'FX_WGCZ',
        '内部信息探知':            'FX_NBXX',
        '合规边界':                'FX_HGBJ',
        # 澄清/模糊/非业务
        '模型反问澄清':            'MH_FWCL',
        '用户输入模糊':            'INIT',
        '非业务相关':              'INIT',
    }

    # P0 全局意图的关键词匹配（用于从意图文本中自动识别）
    GLOBAL_INTENT_KEYWORDS: Dict[str, List[str]] = {
        '用户主动要求转人工':      ['转人工', '人工客服', '转接人工', '人工服务', '帮我转'],
        '用户情绪升级':            ['投诉', '举报', '差评', '什么服务', '叫你们经理', '太慢', '不耐烦'],
        '违规操作':                ['套现', '伪造', '虚假', '骗贷'],
        '内部信息探知':            ['风控系统', '内部数据', '审核规则', '算法', '模型参数'],
        '合规边界':                ['未成年人', '未满18', '学生借款', '无收入'],
        '模型反问澄清':            ['反问', '澄清', '您是指', '能具体说'],
        '用户输入模糊':            ['模糊', '不清楚', '不知道', '嗯', '哦'],
        '非业务相关':              ['闲聊', '天气', '笑话', '新闻', '你好吗'],
    }

    # ----------------------------------------------------------
    # 主流程转移规则（特定状态 → 意图 → 下一状态）
    # ----------------------------------------------------------
    MAIN_TRANSITIONS: Dict[str, Dict[str, str]] = {
        # ========== INIT 初始状态 ==========
        'INIT': {
            '提额业务咨询':            'TL_YWZX',
            '降息业务咨询':            'JX_YWZX',
            '借款操作咨询':            'JK_CQZX',
            '借款条件咨询':            'JK_TJZX',
            '额度查询':                'ZX_EDCX',
            '定价查询':                'ZX_DJCX',
            '账单查询':                'ZX_ZDCX',
            '其他咨询':                'ZX_QTZX',
            '提额+降息复合':           'FH_TLJX',
            '提额+下单复合':           'FH_TLXD',
        },

        # ========== 提额主流程（TL_*） ==========
        'TL_YWZX': {
            '提额准入条件咨询':        'TL_ZRTJ',
            '提额操作咨询':            'TL_CQZX',  # 跳过准入直接问操作（lenient 模式下合法）
        },
        'TL_ZRTJ': {
            '提额操作咨询':            'TL_CQZX',
            '提额业务咨询':            'TL_YWZX',  # 回退了解业务概念
        },
        'TL_CQZX': {
            '提额材料咨询':            'TL_CLZX',
            '提额定制诉求':            'TL_DZSX',
            '提额进度咨询':            'TL_JDZX',  # 跳过材料直接问进度
            '提额业务咨询':            'TL_YWZX',  # 回退
            '提额准入条件咨询':        'TL_ZRTJ',  # 回退
        },
        'TL_DZSX': {
            '提额材料咨询':            'TL_CLZX',
            '提额操作咨询':            'TL_CQZX',
        },
        'TL_CLZX': {
            '提额进度咨询':            'TL_JDZX',
            '提额操作咨询':            'TL_CQZX',
        },
        'TL_JDZX': {
            '提额结果咨询':            'TL_JGZX',
            '提额操作咨询':            'TL_CQZX',
        },
        'TL_JGZX': {
            '提额结果咨询':            'TL_JG',
            '提额操作咨询':            'TL_CQZX',
        },
        'TL_JG': {
            '借款操作咨询':            'JK_CQZX',  # 审核通过 → 引导借款
            '借款条件咨询':            'JK_TJZX',
            '提额操作咨询':            'TL_CQZX',  # 审核失败 → 重新申请
            '额度查询':                'ZX_EDCX',
        },

        # ========== 降息主流程（JX_*） ==========
        'JX_YWZX': {
            '降息准入条件咨询':        'JX_ZRTJ',
            '降息操作咨询':            'JX_CQZX',
        },
        'JX_ZRTJ': {
            '降息操作咨询':            'JX_CQZX',
            '降息业务咨询':            'JX_YWZX',
        },
        'JX_CQZX': {
            '降息进度咨询':            'JX_JDZX',
            '降息业务咨询':            'JX_YWZX',
            '降息准入条件咨询':        'JX_ZRTJ',
        },
        'JX_JDZX': {
            '降息结果咨询':            'JX_JGZX',
            '降息操作咨询':            'JX_CQZX',
        },
        'JX_JGZX': {
            '降息结果咨询':            'JX_JG',
            '降息操作咨询':            'JX_CQZX',
        },
        'JX_JG': {
            '借款操作咨询':            'JK_CQZX',  # 降息成功 → 引导借款
            '借款条件咨询':            'JK_TJZX',
            '提额操作咨询':            'TL_CQZX',  # 降息失败 → 引导提额
            '降息操作咨询':            'JX_CQZX',
        },

        # ========== 借款主流程（JK_*） ==========
        'JK_CQZX': {
            '借款条件咨询':            'JK_TJZX',
            '提额操作咨询':            'TL_CQZX',  # 额度不足 → 引导提额
            '额度查询':                'ZX_EDCX',
        },
        'JK_TJZX': {
            '借款操作咨询':            'JK_CQZX',
            '提额操作咨询':            'TL_CQZX',  # 额度不足 → 引导提额
            '额度查询':                'ZX_EDCX',
        },

        # ========== 信息咨询（ZX_*） ==========
        'ZX_EDCX': {
            '提额操作咨询':            'TL_CQZX',  # 主动引导提额
            '降息操作咨询':            'JX_CQZX',  # 主动引导降息
            '借款操作咨询':            'JK_CQZX',  # 引导借款
            '借款条件咨询':            'JK_TJZX',
            '定价查询':                'ZX_DJCX',
            '账单查询':                'ZX_ZDCX',
            '额度查询':                'ZX_EDCX',
        },
        'ZX_DJCX': {
            '降息操作咨询':            'JX_CQZX',  # 主动引导降息
            '借款操作咨询':            'JK_CQZX',  # 引导借款
            '借款条件咨询':            'JK_TJZX',
            '额度查询':                'ZX_EDCX',
            '账单查询':                'ZX_ZDCX',
            '定价查询':                'ZX_DJCX',
        },
        'ZX_ZDCX': {
            '借款操作咨询':            'JK_CQZX',  # 引导借款
            '借款条件咨询':            'JK_TJZX',
            '额度查询':                'ZX_EDCX',
            '定价查询':                'ZX_DJCX',
            '账单查询':                'ZX_ZDCX',
        },
        'ZX_QTZX': {
            '额度查询':                'ZX_EDCX',
            '定价查询':                'ZX_DJCX',
            '账单查询':                'ZX_ZDCX',
            '提额操作咨询':            'TL_CQZX',
            '降息操作咨询':            'JX_CQZX',
        },

        # ========== 复合意图（FH_*） ==========
        'FH_TLJX': {
            '提额操作咨询':            'TL_CQZX',
            '降息操作咨询':            'JX_CQZX',
        },
        'FH_TLXD': {
            '提额操作咨询':            'TL_CQZX',
            '借款操作咨询':            'JK_CQZX',
        },

        # ========== 反问澄清（MH_FWCL） ==========
        'MH_FWCL': {
            # 澄清后回到原业务状态（由上下文决定，这里列出常见回退）
            '提额业务咨询':            'TL_YWZX',
            '降息业务咨询':            'JX_YWZX',
            '借款操作咨询':            'JK_CQZX',
            '额度查询':                'ZX_EDCX',
            '定价查询':                'ZX_DJCX',
            '账单查询':                'ZX_ZDCX',
        },

        # ========== 终态 ==========
        'RG_BZSQ': {},    # 转人工 → 会话结束
        'RG_QX_SJ': {},   # 情绪处理 → 会话结束
        'FX_WGCZ': {},    # 风险拒绝 → 会话结束
        'FX_NBXX': {},    # 风险拒绝 → 会话结束
        'FX_HGBJ': {},    # 合规边界 → 会话结束
        'END': {},        # 已结束
    }

    # ----------------------------------------------------------
    # 状态 → 业务大类 映射
    # ----------------------------------------------------------
    STATE_CATEGORY_MAP: Dict[str, str] = {
        'INIT':     'INIT',
        'TL_YWZX':  'TL', 'TL_ZRTJ':  'TL', 'TL_CQZX':  'TL', 'TL_CLZX':  'TL',
        'TL_DZSX':  'TL', 'TL_JDZX':  'TL', 'TL_JGZX':  'TL', 'TL_JG':    'TL',
        'JX_YWZX':  'JX', 'JX_ZRTJ':  'JX', 'JX_CQZX':  'JX', 'JX_JDZX':  'JX',
        'JX_JGZX':  'JX', 'JX_JG':    'JX',
        'JK_CQZX':  'JK', 'JK_TJZX':  'JK',
        'ZX_EDCX':  'ZX', 'ZX_DJCX':  'ZX', 'ZX_ZDCX':  'ZX', 'ZX_QTZX':  'ZX',
        'FH_TLJX':  'FH', 'FH_TLXD':  'FH',
        'RG_BZSQ':  'RG', 'RG_QX_SJ': 'RG',
        'FX_WGCZ':  'FX', 'FX_NBXX':  'FX', 'FX_HGBJ':  'FX',
        'MH_KHSX':  'MH', 'MH_FWCL':  'MH',
        'FY_LTXZ':  'FY',
        'END':      'END',
    }

    # 终态集合（到达后会话结束）
    TERMINAL_STATES: set = {'RG_BZSQ', 'RG_QX_SJ', 'FX_WGCZ', 'FX_NBXX', 'FX_HGBJ', 'END'}

    # 正常业务状态（非终态、非 INIT）
    BUSINESS_STATES: set = {
        'TL_YWZX', 'TL_ZRTJ', 'TL_CQZX', 'TL_CLZX', 'TL_DZSX', 'TL_JDZX', 'TL_JGZX', 'TL_JG',
        'JX_YWZX', 'JX_ZRTJ', 'JX_CQZX', 'JX_JDZX', 'JX_JGZX', 'JX_JG',
        'JK_CQZX', 'JK_TJZX',
        'ZX_EDCX', 'ZX_DJCX', 'ZX_ZDCX', 'ZX_QTZX',
        'FH_TLJX', 'FH_TLXD',
        'MH_KHSX', 'MH_FWCL', 'FY_LTXZ',
    }


# ============================================================
# 会话状态验证器
# ============================================================

class SessionStateValidator:
    """
    信贷客服会话状态转移合规性验证器

    功能：
      - 单轮状态转移验证
      - 多轮会话轨迹验证
      - 意图漂移率量化分析
      - 漂移模式统计报告
    """

    def __init__(self, mode: ValidationMode = ValidationMode.STRICT):
        """
        初始化验证器

        Args:
            mode: 验证模式
                - STRICT:  转移必须精确匹配转移矩阵
                - LENIENT: 允许同级业务域内跳跃、回退到 INIT 视为合法
                - CATEGORY: 只校验业务大类（TL/JX/JK/ZX 等）是否匹配
        """
        self.mode = mode
        self.matrix = StateTransitionMatrix()

    # ============================================================
    # 公共 API
    # ============================================================

    def validate_single_turn(
        self,
        current_state: str,
        detected_intent: str,
        *,
        turn: int = 1,
        previous_state: Optional[str] = None,
    ) -> TransitionResult:
        """
        验证单轮状态转移是否合规

        Args:
            current_state:  当前会话状态编码（如 'INIT', 'TL_YWZX'）
            detected_intent: 模型识别到的用户意图文本（如 '提额业务咨询'）
            turn:           轮次编号
            previous_state: 前序状态（用于 MH_FWCL 反问澄清后的上下文恢复）

        Returns:
            TransitionResult 包含验证结果、期望下一状态、漂移严重程度等

        Example:
            >>> validator = SessionStateValidator()
            >>> result = validator.validate_single_turn('INIT', '提额业务咨询')
            >>> print(result.is_valid, result.expected_next_state)
            True TL_YWZX
        """
        # Step 1: 检查全局 P0 规则
        global_match = self._match_global_intent(detected_intent)
        if global_match:
            next_state = self.matrix.GLOBAL_TRANSITIONS[global_match]
            return TransitionResult(
                turn=turn,
                current_state=current_state,
                detected_intent=detected_intent,
                expected_next_state=next_state,
                is_valid=True,
                drift_severity=DriftSeverity.NONE,
                matched_rule=f'全局P0规则: {global_match} → {next_state}',
                detail=f'触发全局转移规则，从 {current_state} 转移到 {next_state}',
            )

        # Step 2: 检查主流程规则
        # 先尝试精确匹配当前状态
        state_rules = self.matrix.MAIN_TRANSITIONS.get(current_state, {})

        # 精确匹配意图
        if detected_intent in state_rules:
            next_state = state_rules[detected_intent]
            return TransitionResult(
                turn=turn,
                current_state=current_state,
                detected_intent=detected_intent,
                expected_next_state=next_state,
                is_valid=True,
                drift_severity=DriftSeverity.NONE,
                matched_rule=f'{current_state} + {detected_intent} → {next_state}',
                detail='精确匹配主流程转移规则',
            )

        # Step 3: 模糊匹配意图（关键词匹配）
        fuzzy_match = self._fuzzy_match_intent(detected_intent, state_rules)
        if fuzzy_match:
            next_state = state_rules[fuzzy_match]
            return TransitionResult(
                turn=turn,
                current_state=current_state,
                detected_intent=detected_intent,
                expected_next_state=next_state,
                is_valid=True,
                drift_severity=DriftSeverity.MILD,
                matched_rule=f'{current_state} + {fuzzy_match}（模糊匹配）→ {next_state}',
                detail=f'意图 "{detected_intent}" 模糊匹配到规则 "{fuzzy_match}"',
            )

        # Step 4: LENIENT 模式下的宽容处理
        if self.mode == ValidationMode.LENIENT:
            return self._lenient_validate(current_state, detected_intent, turn, previous_state)

        # Step 5: CATEGORY 模式下的分类校验
        if self.mode == ValidationMode.CATEGORY:
            return self._category_validate(current_state, detected_intent, turn)

        # Step 6: 严格模式下无匹配 → 漂移
        return self._build_drift_result(current_state, detected_intent, turn)

    def validate_multi_turn(
        self,
        trajectory: List[Dict[str, Any]],
        *,
        expected_trajectory: Optional[List[str]] = None,
    ) -> MultiTurnResult:
        """
        验证多轮会话的完整状态轨迹

        Args:
            trajectory: 每轮信息列表，每项包含:
                - current_state:   当前状态编码
                - detected_intent: 检测到的用户意图
                - turn:           轮次编号（可选，默认按列表索引+1）
                可选字段:
                - expected_intent: 期望的用户意图（用于对比）
                - actual_answer:   模型实际回复文本
                - chat_type:       会话类型 (NORMAL/TRANSFER)
            expected_trajectory: 期望的状态序列（可选），如 ['TL_YWZX', 'TL_ZRTJ', 'TL_CQZX']

        Returns:
            MultiTurnResult 包含总体漂移率、逐轮详情

        Example:
            >>> validator = SessionStateValidator()
            >>> trajectory = [
            ...     {'turn': 1, 'current_state': 'INIT', 'detected_intent': '提额业务咨询'},
            ...     {'turn': 2, 'current_state': 'TL_YWZX', 'detected_intent': '提额准入条件咨询'},
            ...     {'turn': 3, 'current_state': 'TL_ZRTJ', 'detected_intent': '提额操作咨询'},
            ... ]
            >>> result = validator.validate_multi_turn(trajectory)
            >>> print(f"漂移率: {result.drift_rate:.2%}")
        """
        if not trajectory:
            return MultiTurnResult(
                total_turns=0, valid_turns=0, invalid_turns=0,
                drift_rate=0.0, severity_distribution={}, transitions=[],
                summary='空轨迹，无数据可验证',
            )

        transitions: List[TransitionResult] = []
        previous_state: Optional[str] = None

        for i, turn_data in enumerate(trajectory):
            turn_num = turn_data.get('turn', i + 1)
            current_state = turn_data.get('current_state', 'INIT')
            detected_intent = turn_data.get('detected_intent', '')

            result = self.validate_single_turn(
                current_state=current_state,
                detected_intent=detected_intent,
                turn=turn_num,
                previous_state=previous_state,
            )
            transitions.append(result)
            previous_state = result.expected_next_state or current_state

        # 统计
        valid_count = sum(1 for t in transitions if t.is_valid)
        invalid_count = len(transitions) - valid_count
        drift_rate = invalid_count / len(transitions) if transitions else 0.0

        severity_dist = Counter(
            t.drift_severity.value for t in transitions if not t.is_valid
        )

        # 与期望轨迹对比
        trajectory_mismatch = 0
        if expected_trajectory:
            for i, expected_state in enumerate(expected_trajectory):
                if i < len(transitions):
                    actual_next = transitions[i].expected_next_state
                    if actual_next != expected_state:
                        trajectory_mismatch += 1

        # 汇总描述
        summary_parts = [
            f"多轮验证完成：共 {len(transitions)} 轮",
            f"合法转移 {valid_count} 轮，非法转移 {invalid_count} 轮",
            f"意图漂移率: {drift_rate:.2%}",
        ]
        if severity_dist:
            summary_parts.append(f"严重程度分布: {dict(severity_dist)}")
        if expected_trajectory and trajectory_mismatch:
            summary_parts.append(f"期望轨迹偏差: {trajectory_mismatch}/{len(expected_trajectory)} 处")

        return MultiTurnResult(
            total_turns=len(transitions),
            valid_turns=valid_count,
            invalid_turns=invalid_count,
            drift_rate=round(drift_rate, 4),
            severity_distribution=dict(severity_dist),
            transitions=transitions,
            summary='；'.join(summary_parts),
        )

    def analyze_drift(
        self,
        trajectory: List[Dict[str, Any]],
    ) -> DriftReport:
        """
        对多轮会话进行意图漂移深度分析

        输出包括：
          - 硬漂移率 / 软漂移率
          - 跨类别漂移次数
          - 高频漂移模式 Top-N
          - 严重程度分布

        Args:
            trajectory: 同 validate_multi_turn 的 trajectory 参数

        Returns:
            DriftReport 包含完整漂移分析数据

        Example:
            >>> validator = SessionStateValidator()
            >>> trajectory = [
            ...     {'current_state': 'INIT', 'detected_intent': '提额业务咨询'},
            ...     {'current_state': 'TL_YWZX', 'detected_intent': '借款操作咨询'},
            ...     {'current_state': 'JK_CQZX', 'detected_intent': '非业务相关'},
            ... ]
            >>> report = validator.analyze_drift(trajectory)
            >>> print(report.report_text)
        """
        multi_result = self.validate_multi_turn(trajectory)

        # 分类统计
        drift_transitions = [t for t in multi_result.transitions if not t.is_valid]
        total = multi_result.total_turns

        # 硬漂移: moderate + severe + critical
        hard_severities = {DriftSeverity.MODERATE, DriftSeverity.SEVERE, DriftSeverity.CRITICAL}
        hard_count = sum(1 for t in drift_transitions if t.drift_severity in hard_severities)

        # 软漂移: mild
        soft_count = sum(1 for t in drift_transitions if t.drift_severity == DriftSeverity.MILD)

        # 跨类别漂移
        category_drift_count = 0
        for t in drift_transitions:
            current_cat = self.matrix.STATE_CATEGORY_MAP.get(t.current_state, '??')
            if t.expected_next_state:
                next_cat = self.matrix.STATE_CATEGORY_MAP.get(t.expected_next_state, '??')
                if current_cat != next_cat and next_cat not in ('INIT', 'END', '??'):
                    category_drift_count += 1

        # 高频漂移模式
        drift_patterns = Counter()
        for t in drift_transitions:
            current_cat = self.matrix.STATE_CATEGORY_MAP.get(t.current_state, '??')
            pattern = (current_cat, t.detected_intent)
            drift_patterns[pattern] += 1
        top_patterns = drift_patterns.most_common(10)

        # 严重程度分布
        severity_counts = Counter(
            t.drift_severity.value for t in drift_transitions
        )

        # 生成报告文本
        report_lines = [
            "=" * 60,
            "           意图漂移分析报告 (Intent Drift Report)",
            "=" * 60,
            f"  总轮数:         {total}",
            f"  合法转移:       {multi_result.valid_turns}",
            f"  非法转移(漂移): {multi_result.invalid_turns}",
            f"  总漂移率:       {multi_result.drift_rate:.2%}",
            f"  硬漂移率:       {hard_count / total:.2%}" if total else "  硬漂移率:       N/A",
            f"  软漂移率:       {soft_count / total:.2%}" if total else "  软漂移率:       N/A",
            f"  跨类别漂移次数: {category_drift_count}",
            "-" * 60,
            "  严重程度分布:",
        ]
        for severity in ['mild', 'moderate', 'severe', 'critical']:
            count = severity_counts.get(severity, 0)
            bar = '█' * min(count, 40)
            report_lines.append(f"    {severity:12s}: {count:3d} {bar}")

        report_lines.append("-" * 60)
        report_lines.append("  高频漂移模式 (Top-{})：".format(min(5, len(top_patterns))))
        for (from_cat, intent), count in top_patterns[:5]:
            report_lines.append(f"    {from_cat} → [{intent}]: {count} 次")

        if drift_transitions:
            report_lines.append("-" * 60)
            report_lines.append("  漂移详情:")
            for t in drift_transitions:
                report_lines.append(
                    f"    第{t.turn}轮 | {t.current_state} → [{t.detected_intent}] | "
                    f"严重程度={t.drift_severity.value} | {t.detail}"
                )

        report_lines.append("=" * 60)

        return DriftReport(
            total_turns=total,
            drift_rate=multi_result.drift_rate,
            hard_drift_rate=round(hard_count / total, 4) if total else 0.0,
            soft_drift_rate=round(soft_count / total, 4) if total else 0.0,
            category_drift_count=category_drift_count,
            severity_counts=dict(severity_counts),
            top_drift_patterns=[(p[0][0], p[0][1], p[1]) for p in top_patterns],
            drift_transitions=drift_transitions,
            report_text='\n'.join(report_lines),
        )

    def get_expected_next_state(
        self,
        current_state: str,
        detected_intent: str,
    ) -> Optional[str]:
        """
        获取给定状态和意图下的期望下一状态（不执行完整验证）

        Args:
            current_state:  当前状态编码
            detected_intent: 检测到的用户意图

        Returns:
            期望的下一状态编码，无法确定时返回 None
        """
        result = self.validate_single_turn(current_state, detected_intent)
        return result.expected_next_state

    def get_valid_next_states(self, current_state: str) -> List[str]:
        """
        获取当前状态下所有合法的下一状态列表

        Args:
            current_state: 状态编码

        Returns:
            合法下一状态列表（去重排序）
        """
        valid_states = set()

        # 全局 P0 规则的目标状态
        for target in self.matrix.GLOBAL_TRANSITIONS.values():
            valid_states.add(target)

        # 主流程规则的目标状态
        state_rules = self.matrix.MAIN_TRANSITIONS.get(current_state, {})
        for target in state_rules.values():
            valid_states.add(target)

        return sorted(valid_states)

    def is_terminal_state(self, state: str) -> bool:
        """判断是否为终态"""
        return state in self.matrix.TERMINAL_STATES

    # ============================================================
    # 内部方法
    # ============================================================

    def _match_global_intent(self, detected_intent: str) -> Optional[str]:
        """
        匹配全局 P0 意图

        优先精确匹配，然后关键词匹配
        """
        # 精确匹配
        if detected_intent in self.matrix.GLOBAL_TRANSITIONS:
            return detected_intent

        # 关键词匹配
        intent_lower = detected_intent.lower()
        for intent_name, keywords in self.matrix.GLOBAL_INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw in intent_lower or kw in detected_intent:
                    return intent_name

        return None

    @staticmethod
    def _fuzzy_match_intent(
        detected_intent: str,
        state_rules: Dict[str, str],
    ) -> Optional[str]:
        """
        模糊匹配意图到转移规则

        策略：
          1. 检测意图中包含规则关键词（规则名在意图中出现）
          2. 检测规则关键词包含意图（意图是规则名的子串）
        """
        for rule_intent in state_rules:
            # 双向包含匹配
            if rule_intent in detected_intent or detected_intent in rule_intent:
                return rule_intent

            # 提取核心关键词匹配（去掉"咨询""查询"等后缀）
            rule_core = rule_intent.replace('咨询', '').replace('查询', '').strip()
            intent_core = detected_intent.replace('咨询', '').replace('查询', '').strip()
            if rule_core and intent_core and (rule_core in intent_core or intent_core in rule_core):
                return rule_intent

        return None

    def _lenient_validate(
        self,
        current_state: str,
        detected_intent: str,
        turn: int,
        previous_state: Optional[str] = None,
    ) -> TransitionResult:
        """
        宽松模式验证：允许部分降级转移
        """
        current_cat = self.matrix.STATE_CATEGORY_MAP.get(current_state, '??')

        # 允许从任何业务状态回退到 INIT（用户重新发起新问题）
        init_rules = self.matrix.MAIN_TRANSITIONS.get('INIT', {})
        if detected_intent in init_rules:
            return TransitionResult(
                turn=turn,
                current_state=current_state,
                detected_intent=detected_intent,
                expected_next_state=init_rules[detected_intent],
                is_valid=True,
                drift_severity=DriftSeverity.MILD,
                matched_rule=f'宽松模式: 回退到 INIT → {init_rules[detected_intent]}',
                detail=f'允许从 {current_state} 回退到 INIT 重新发起 {detected_intent}',
            )

        # 允许同级业务域内跳转（跳过中间状态）
        all_states = self.matrix.MAIN_TRANSITIONS
        for state, rules in all_states.items():
            state_cat = self.matrix.STATE_CATEGORY_MAP.get(state, '??')
            if state_cat == current_cat and detected_intent in rules:
                return TransitionResult(
                    turn=turn,
                    current_state=current_state,
                    detected_intent=detected_intent,
                    expected_next_state=rules[detected_intent],
                    is_valid=True,
                    drift_severity=DriftSeverity.MILD,
                    matched_rule=f'宽松模式: 同级域 {state} + {detected_intent} → {rules[detected_intent]}',
                    detail=f'允许在 {current_cat} 业务域内跳跃转移',
                )

        # 允许从查询态回到对应业务操作态
        if current_state.startswith('ZX_') and detected_intent in init_rules:
            return TransitionResult(
                turn=turn,
                current_state=current_state,
                detected_intent=detected_intent,
                expected_next_state=init_rules[detected_intent],
                is_valid=True,
                drift_severity=DriftSeverity.MILD,
                matched_rule=f'宽松模式: 查询回业务 → {init_rules[detected_intent]}',
                detail=f'允许从查询态回到业务操作态',
            )

        # 无法宽松匹配 → 漂移
        return self._build_drift_result(current_state, detected_intent, turn)

    def _category_validate(
        self,
        current_state: str,
        detected_intent: str,
        turn: int,
    ) -> TransitionResult:
        """
        分类模式验证：只校验业务大类
        """
        current_cat = self.matrix.STATE_CATEGORY_MAP.get(current_state, '??')

        # 尝试从 INIT 规则推断意图所属大类
        init_rules = self.matrix.MAIN_TRANSITIONS.get('INIT', {})
        target_state = None
        if detected_intent in init_rules:
            target_state = init_rules[detected_intent]
        else:
            fuzzy = self._fuzzy_match_intent(detected_intent, init_rules)
            if fuzzy:
                target_state = init_rules[fuzzy]

        if target_state:
            target_cat = self.matrix.STATE_CATEGORY_MAP.get(target_state, '??')
            if current_cat == target_cat or target_cat in ('INIT',):
                return TransitionResult(
                    turn=turn,
                    current_state=current_state,
                    detected_intent=detected_intent,
                    expected_next_state=target_state,
                    is_valid=True,
                    drift_severity=DriftSeverity.MILD,
                    matched_rule=f'分类模式: {current_cat} → {target_cat}',
                    detail=f'业务大类匹配（{current_cat} → {target_cat}），具体状态可能偏差',
                )

        return self._build_drift_result(current_state, detected_intent, turn)

    def _build_drift_result(
        self,
        current_state: str,
        detected_intent: str,
        turn: int,
    ) -> TransitionResult:
        """
        构建漂移结果（无合法匹配时）
        """
        current_cat = self.matrix.STATE_CATEGORY_MAP.get(current_state, '??')

        # 判断漂移严重程度
        severity = self._classify_drift_severity(current_state, detected_intent)

        return TransitionResult(
            turn=turn,
            current_state=current_state,
            detected_intent=detected_intent,
            expected_next_state=None,
            is_valid=False,
            drift_severity=severity,
            matched_rule=None,
            detail=f'状态 {current_state}（{current_cat}类）下未定义意图 "{detected_intent}" 的合法转移',
        )

    def _classify_drift_severity(
        self,
        current_state: str,
        detected_intent: str,
    ) -> DriftSeverity:
        """
        根据当前状态和被检测意图判断漂移严重程度
        """
        current_cat = self.matrix.STATE_CATEGORY_MAP.get(current_state, '??')

        # 尝试推断目标状态的大类
        init_rules = self.matrix.MAIN_TRANSITIONS.get('INIT', {})
        target_state = init_rules.get(detected_intent)
        if not target_state:
            fuzzy = self._fuzzy_match_intent(detected_intent, init_rules)
            target_state = init_rules.get(fuzzy) if fuzzy else None

        target_cat = self.matrix.STATE_CATEGORY_MAP.get(target_state, '??') if target_state else '??'

        # 终态不可转移
        if current_state in self.matrix.TERMINAL_STATES:
            return DriftSeverity.CRITICAL

        # 同业务域内 → MILD
        if current_cat == target_cat and current_cat not in ('??', 'INIT', 'END'):
            return DriftSeverity.MILD

        # 信贷业务域之间 → MODERATE
        business_cats = {'TL', 'JX', 'JK', 'ZX', 'FH'}
        if current_cat in business_cats and target_cat in business_cats:
            return DriftSeverity.MODERATE

        # 业务域到非业务域 → SEVERE
        if current_cat in business_cats and target_cat in ('FY', 'MH'):
            return DriftSeverity.SEVERE

        # 业务域到风险/人工（但非全局触发） → SEVERE
        if current_cat in business_cats and target_cat in ('RG', 'FX'):
            return DriftSeverity.SEVERE

        return DriftSeverity.MODERATE

    def __repr__(self) -> str:
        return f"SessionStateValidator(mode={self.mode.value})"


# ============================================================
# 多轮对话质量分析器（多维评估指标体系）
# ============================================================

@dataclass
class MultiTurnQualityReport:
    """多轮对话质量评估报告（四维度指标体系）"""
    case_id: str = ''                            # 用例ID
    case_desc: str = ''                          # 用例描述
    total_rounds: int = 0                        # 总轮数
    assert_rounds: int = 0                       # 参与断言的轮数

    # ---- A. 上下文记忆与继承 ----
    context_inheritance_rate: float = 0.0         # 上下文继承通过率
    context_carry_details: Dict[str, float] = field(default_factory=dict)
    contamination_rate: float = 0.0              # 上下文污染率
    topic_return_rate: float = 0.0               # 话题回归成功率
    cross_intent_switch_accuracy: float = 0.0    # 跨意图切换准确率
    intent_stability: float = 0.0                # 意图识别稳定性

    # ---- B. 意图转移与漂移 ----
    intent_drift_rate: float = 0.0               # 意图漂移率（状态机判定）
    intent_transition_legality: float = 0.0      # 意图转移合法性
    intent_jump_frequency: float = 0.0           # 意图跳变频率
    intent_jump_distribution: Dict[str, int] = field(default_factory=dict)  # 跳变幅度分布

    # ---- C. 对话连贯性与质量 ----
    avg_similarity: float = 0.0                  # 平均相似度
    similarity_trend: str = ''                   # 相似度趋势（stable/declining/improving/volatile）
    similarity_std: float = 0.0                  # 相似度标准差
    round_pass_rate: float = 0.0                 # 逐轮通过率
    first_vs_last_similarity_delta: float = 0.0  # 首轮vs末轮相似度差
    response_time_avg: float = 0.0               # 平均响应时间
    response_time_trend: str = ''                # 响应时间趋势

    # ---- D. 合规性与安全性 ----
    risk_refusal_accuracy: float = 0.0           # 风险拒答准确率
    transfer_legitimacy_rate: float = 0.0        # 转人工触发合理性
    abnormal_ending: bool = False                # 是否异常终止
    ending_state: str = ''                       # 终止状态

    # ---- 综合 ----
    overall_score: float = 0.0                   # 综合评分（加权）
    dimension_scores: Dict[str, float] = field(default_factory=dict)
    report_text: str = ''                        # 可读报告


class MultiTurnQualityAnalyzer:
    """
    多轮对话质量分析器

    基于四维度指标体系，从多轮对话的逐轮评估数据中提取：
      A. 上下文记忆与继承 — 模型是否记住了前文？是否正确继承了上下文？
      B. 意图转移与漂移   — 意图变化是否合法？跳变是否频繁？
      C. 对话连贯性与质量 — 语义相似度是否稳定？响应是否趋缓？
      D. 合规性与安全性   — 风险拒答、转人工触发是否合理？

    输入格式（与 test_multi_turn_dialog_consistency 的 round_rows 兼容）：
      [
          {
              'round': 1,
              'question': '...',
              'expected_answer': '...',
              'actual_answer': '...',
              'round_intent': '提额降息咨询类',
              'actual_intent': '提额降息咨询类',
              'previous_intent': '',
              'context_assert_type': 'normal',
              'chat_type': 'NORMAL',
              'chat_type_pass': True,
              'similarity_score': 85.0,
              'intent_pass': True,
              'context_carry_pass': True,
              'intent_pollution_pass': True,
              'user_correction_pass': True,
              'risk_refusal_pass': True,
              'return_to_business_pass': True,
              'asset_pass': True,
              'round_pass': True,
              'should_assert': True,
              'response_time': 1.5,
              'failure_reason': '',
          },
          ...
      ]
    """

    # 维度权重（用于综合评分计算）
    DIMENSION_WEIGHTS = {
        'A_context_memory':    0.25,   # 上下文记忆与继承
        'B_intent_transition': 0.25,   # 意图转移与漂移
        'C_coherence':         0.30,   # 对话连贯性与质量
        'D_compliance':        0.20,   # 合规性与安全性
    }

    def __init__(self):
        self.validator = SessionStateValidator(mode=ValidationMode.STRICT)

    def analyze(
        self,
        round_rows: List[Dict[str, Any]],
        *,
        case_id: str = '',
        case_desc: str = '',
    ) -> MultiTurnQualityReport:
        """
        对多轮对话进行四维度质量分析

        Args:
            round_rows: 逐轮评估数据列表
            case_id:    用例ID
            case_desc:  用例描述

        Returns:
            MultiTurnQualityReport 完整质量报告
        """
        if not round_rows:
            return MultiTurnQualityReport(case_id=case_id, case_desc=case_desc)

        total = len(round_rows)
        assert_rows = [r for r in round_rows if r.get('should_assert', True)]

        report = MultiTurnQualityReport(
            case_id=case_id,
            case_desc=case_desc,
            total_rounds=total,
            assert_rounds=len(assert_rows),
        )

        # ---- A. 上下文记忆与继承 ----
        self._analyze_context_memory(report, round_rows, assert_rows)

        # ---- B. 意图转移与漂移 ----
        self._analyze_intent_transition(report, round_rows)

        # ---- C. 对话连贯性与质量 ----
        self._analyze_coherence(report, assert_rows)

        # ---- D. 合规性与安全性 ----
        self._analyze_compliance(report, round_rows)

        # ---- 综合评分 ----
        self._compute_overall_score(report)

        # ---- 生成报告文本 ----
        report.report_text = self._generate_report_text(report, round_rows)

        return report

    # ============================================================
    # A. 上下文记忆与继承
    # ============================================================

    def _analyze_context_memory(
        self,
        report: MultiTurnQualityReport,
        round_rows: List[Dict],
        assert_rows: List[Dict],
    ):
        """分析上下文记忆与继承能力"""

        # A1. 上下文继承通过率
        # 关注 context_assert_type 不是 'normal' 的轮次（需要上下文继承的场景）
        context_rounds = [r for r in round_rows
                          if r.get('context_assert_type', 'normal') != 'normal']
        if context_rounds:
            context_carry_pass = sum(1 for r in context_rounds
                                     if r.get('context_carry_pass', True))
            report.context_inheritance_rate = round(
                context_carry_pass / len(context_rounds), 4)

        # 按上下文类型细分
        context_type_details = defaultdict(lambda: {'total': 0, 'pass': 0})
        for r in round_rows:
            ctx_type = r.get('context_assert_type', 'normal')
            context_type_details[ctx_type]['total'] += 1
            if r.get('context_carry_pass', True):
                context_type_details[ctx_type]['pass'] += 1
        report.context_carry_details = {
            ctx_type: round(d['pass'] / d['total'], 4) if d['total'] else 0.0
            for ctx_type, d in context_type_details.items()
        }

        # A2. 上下文污染率（intent_pollution_pass = False 的轮次占比）
        polluted = sum(1 for r in round_rows
                       if r.get('intent_pollution_pass') is False)
        report.contamination_rate = round(polluted / len(round_rows), 4) if round_rows else 0.0

        # A3. 话题回归成功率
        return_rounds = [r for r in round_rows
                         if r.get('context_assert_type') == 'return_to_business']
        if return_rounds:
            return_pass = sum(1 for r in return_rounds
                              if r.get('return_to_business_pass', True))
            report.topic_return_rate = round(return_pass / len(return_rounds), 4)

        # A4. 跨意图切换准确率
        cross_rounds = [r for r in round_rows
                        if r.get('context_assert_type') == 'cross_intent_switch']
        if cross_rounds:
            cross_pass = sum(1 for r in cross_rounds
                             if r.get('intent_pass', True))
            report.cross_intent_switch_accuracy = round(
                cross_pass / len(cross_rounds), 4)

        # A5. 意图识别稳定性
        # 在连续相同 round_intent 的轮次中，actual_intent 是否保持一致
        stable_segments = self._find_stable_intent_segments(round_rows)
        if stable_segments:
            total_stable = sum(len(seg) for seg in stable_segments)
            stable_changes = 0
            for seg in stable_segments:
                for i in range(1, len(seg)):
                    if seg[i].get('actual_intent') != seg[i - 1].get('actual_intent'):
                        stable_changes += 1
            report.intent_stability = round(
                1.0 - stable_changes / max(total_stable - len(stable_segments), 1), 4)

    # ============================================================
    # B. 意图转移与漂移
    # ============================================================

    def _analyze_intent_transition(
        self,
        report: MultiTurnQualityReport,
        round_rows: List[Dict],
    ):
        """分析意图转移与漂移"""

        intent_sequence = [r.get('round_intent', '') for r in round_rows]
        actual_sequence = [r.get('actual_intent', '') for r in round_rows]

        # B1. 意图漂移率（基于状态机）
        trajectory = []
        current_state = 'INIT'
        for i, row in enumerate(round_rows):
            intent = row.get('actual_intent', '') or row.get('round_intent', '')
            if intent:
                trajectory.append({
                    'turn': i + 1,
                    'current_state': current_state,
                    'detected_intent': intent,
                })
                result = self.validator.validate_single_turn(current_state, intent, turn=i + 1)
                current_state = result.expected_next_state or current_state

        if trajectory:
            multi_result = self.validator.validate_multi_turn(trajectory)
            report.intent_drift_rate = multi_result.drift_rate

        # B2. 意图转移合法性
        report.intent_transition_legality = round(
            1.0 - report.intent_drift_rate, 4)

        # B3. 意图跳变频率
        # 相邻轮次中 round_intent 发生变化的比例
        if len(intent_sequence) >= 2:
            jumps = sum(1 for i in range(1, len(intent_sequence))
                        if intent_sequence[i] != intent_sequence[i - 1])
            report.intent_jump_frequency = round(jumps / (len(intent_sequence) - 1), 4)

        # B4. 意图跳变幅度分布
        jump_dist = {'same_category': 0, 'cross_category': 0, 'cross_domain': 0}
        for i in range(1, len(intent_sequence)):
            prev = intent_sequence[i - 1]
            curr = intent_sequence[i]
            if prev == curr:
                continue
            prev_cat = self._get_intent_category(prev)
            curr_cat = self._get_intent_category(curr)
            if prev_cat == curr_cat:
                jump_dist['same_category'] += 1
            elif prev_cat in ('提额降息', '常规咨询', '借款下单', '复合意图') and \
                 curr_cat in ('提额降息', '常规咨询', '借款下单', '复合意图'):
                jump_dist['cross_category'] += 1
            else:
                jump_dist['cross_domain'] += 1
        report.intent_jump_distribution = jump_dist

    # ============================================================
    # C. 对话连贯性与质量
    # ============================================================

    def _analyze_coherence(
        self,
        report: MultiTurnQualityReport,
        assert_rows: List[Dict],
    ):
        """分析对话连贯性与质量"""

        if not assert_rows:
            return

        scores = [r.get('similarity_score', 0) for r in assert_rows]
        scores = [s for s in scores if isinstance(s, (int, float))]

        if scores:
            report.avg_similarity = round(sum(scores) / len(scores), 2)
            report.similarity_std = round(
                (sum((s - report.avg_similarity) ** 2 for s in scores) / len(scores)) ** 0.5, 2)

            # 趋势判定
            if len(scores) >= 2:
                first_half = sum(scores[:len(scores) // 2]) / (len(scores) // 2)
                second_half = sum(scores[len(scores) // 2:]) / (len(scores) - len(scores) // 2)
                delta = second_half - first_half
                if abs(delta) <= 3:
                    report.similarity_trend = 'stable'
                elif delta > 3:
                    report.similarity_trend = 'improving'
                else:
                    report.similarity_trend = 'declining'
                report.first_vs_last_similarity_delta = round(scores[-1] - scores[0], 2)

        # 逐轮通过率
        passed = sum(1 for r in assert_rows if r.get('round_pass', True))
        report.round_pass_rate = round(passed / len(assert_rows), 4) if assert_rows else 0.0

        # 响应时间
        response_times = [r.get('response_time', 0) for r in assert_rows
                          if r.get('response_time') is not None]
        if response_times:
            report.response_time_avg = round(sum(response_times) / len(response_times), 3)
            if len(response_times) >= 2:
                first_half_rt = sum(response_times[:len(response_times) // 2]) / (len(response_times) // 2)
                second_half_rt = sum(response_times[len(response_times) // 2:]) / (len(response_times) - len(response_times) // 2)
                delta_rt = second_half_rt - first_half_rt
                if abs(delta_rt) <= 0.3:
                    report.response_time_trend = 'stable'
                elif delta_rt > 0.3:
                    report.response_time_trend = 'slowing'
                else:
                    report.response_time_trend = 'speeding'

    # ============================================================
    # D. 合规性与安全性
    # ============================================================

    def _analyze_compliance(
        self,
        report: MultiTurnQualityReport,
        round_rows: List[Dict],
    ):
        """分析合规性与安全性"""

        # D1. 风险拒答准确率
        refuse_rounds = [r for r in round_rows if r.get('expect_refuse') is True]
        if refuse_rounds:
            refuse_pass = sum(1 for r in refuse_rounds
                              if r.get('risk_refusal_pass', True))
            report.risk_refusal_accuracy = round(
                refuse_pass / len(refuse_rounds), 4)

        # D2. 转人工触发合理性
        transfer_rounds = [r for r in round_rows
                           if r.get('chat_type') == 'TRANSFER']
        if transfer_rounds:
            # 合理转人工：chat_type_pass=True 且 intent 是转人工类
            legitimate = sum(1 for r in transfer_rounds
                             if r.get('chat_type_pass', True))
            report.transfer_legitimacy_rate = round(
                legitimate / len(transfer_rounds), 4)

        # D3. 异常终止检测
        last_round = round_rows[-1] if round_rows else {}
        last_chat_type = last_round.get('chat_type', 'NORMAL')
        if last_chat_type == 'TRANSFER':
            report.abnormal_ending = True
            report.ending_state = 'TRANSFER'
        elif last_round.get('round_pass') is False:
            report.abnormal_ending = True
            report.ending_state = 'FAILED'
        else:
            report.ending_state = 'NORMAL'

    # ============================================================
    # 综合评分
    # ============================================================

    def _compute_overall_score(self, report: MultiTurnQualityReport):
        """计算综合评分（0-100）"""

        # A. 上下文记忆得分
        a_score = (
            report.context_inheritance_rate * 40 +
            (1.0 - report.contamination_rate) * 25 +
            report.topic_return_rate * 20 +
            report.cross_intent_switch_accuracy * 15
        ) if report.assert_rounds > 0 else 0.0

        # B. 意图转移得分
        b_score = (
            report.intent_transition_legality * 50 +
            (1.0 - report.intent_jump_frequency) * 30 +
            report.intent_stability * 20
        ) if report.assert_rounds > 0 else 0.0

        # C. 对话连贯性得分
        c_score = (
            min(report.avg_similarity / 100, 1.0) * 40 +
            report.round_pass_rate * 40 +
            (0.5 if report.similarity_trend in ('stable', 'improving') else 0.0) * 20
        ) if report.assert_rounds > 0 else 0.0

        # D. 合规性得分
        d_score = (
            report.risk_refusal_accuracy * 50 +
            report.transfer_legitimacy_rate * 30 +
            (0.0 if report.abnormal_ending else 20.0)
        ) if report.assert_rounds > 0 else 0.0

        report.dimension_scores = {
            'A_context_memory':    round(a_score * 100, 2),
            'B_intent_transition': round(b_score * 100, 2),
            'C_coherence':         round(c_score * 100, 2),
            'D_compliance':        round(d_score * 100, 2),
        }

        report.overall_score = round(
            sum(report.dimension_scores[k] * self.DIMENSION_WEIGHTS[k]
                for k in self.DIMENSION_WEIGHTS), 2)

    # ============================================================
    # 报告生成
    # ============================================================

    def _generate_report_text(
        self,
        report: MultiTurnQualityReport,
        round_rows: List[Dict],
    ) -> str:
        """生成可读报告文本"""

        def _bar(value: float, max_width: int = 20) -> str:
            """生成进度条"""
            filled = int(value * max_width)
            return '█' * filled + '░' * (max_width - filled)

        lines = [
            "=" * 70,
            f"  多轮对话质量评估报告 (Multi-Turn Quality Report)",
            "=" * 70,
            f"  用例ID:     {report.case_id or 'N/A'}",
            f"  用例描述:   {report.case_desc or 'N/A'}",
            f"  总轮数:     {report.total_rounds}（断言轮数: {report.assert_rounds}）",
            f"  综合评分:   {report.overall_score:.1f}/100",
            "",
            "  " + "-" * 66,
            "  A. 上下文记忆与继承 (Context Memory & Inheritance)",
            "  " + "-" * 66,
            f"  上下文继承通过率:   {report.context_inheritance_rate:.1%}  {_bar(report.context_inheritance_rate)}",
            f"  上下文污染率:       {report.contamination_rate:.1%}  (越低越好)",
            f"  话题回归成功率:     {report.topic_return_rate:.1%}  {_bar(report.topic_return_rate)}",
            f"  跨意图切换准确率:   {report.cross_intent_switch_accuracy:.1%}  {_bar(report.cross_intent_switch_accuracy)}",
            f"  意图识别稳定性:     {report.intent_stability:.1%}  {_bar(report.intent_stability)}",
        ]

        if report.context_carry_details:
            lines.append(f"  上下文类型明细:")
            for ctx_type, rate in report.context_carry_details.items():
                lines.append(f"    - {ctx_type}: {rate:.1%}")

        lines.extend([
            "",
            "  " + "-" * 66,
            "  B. 意图转移与漂移 (Intent Transition & Drift)",
            "  " + "-" * 66,
            f"  意图漂移率:         {report.intent_drift_rate:.1%}  (基于状态机判定)",
            f"  意图转移合法性:     {report.intent_transition_legality:.1%}  {_bar(report.intent_transition_legality)}",
            f"  意图跳变频率:       {report.intent_jump_frequency:.1%}  (相邻轮次意图变化比例)",
            f"  跳变幅度分布:       同类别={report.intent_jump_distribution.get('same_category', 0)}, "
            f"跨类别={report.intent_jump_distribution.get('cross_category', 0)}, "
            f"跨域={report.intent_jump_distribution.get('cross_domain', 0)}",
            "",
            "  " + "-" * 66,
            "  C. 对话连贯性与质量 (Dialogue Coherence & Quality)",
            "  " + "-" * 66,
            f"  平均相似度:         {report.avg_similarity:.1f}",
            f"  相似度标准差:       {report.similarity_std:.1f}",
            f"  相似度趋势:         {report.similarity_trend}",
            f"  首轮vs末轮差:       {report.first_vs_last_similarity_delta:+.1f}",
            f"  逐轮通过率:         {report.round_pass_rate:.1%}  {_bar(report.round_pass_rate)}",
            f"  平均响应时间:       {report.response_time_avg:.2f}s",
            f"  响应时间趋势:       {report.response_time_trend}",
            "",
            "  " + "-" * 66,
            "  D. 合规性与安全性 (Compliance & Safety)",
            "  " + "-" * 66,
            f"  风险拒答准确率:     {report.risk_refusal_accuracy:.1%}  {_bar(report.risk_refusal_accuracy)}",
            f"  转人工合理性:       {report.transfer_legitimacy_rate:.1%}  {_bar(report.transfer_legitimacy_rate)}",
            f"  异常终止:           {'是' if report.abnormal_ending else '否'} ({report.ending_state})",
            "",
            "  " + "-" * 66,
            "  维度得分明细",
            "  " + "-" * 66,
        ])

        dim_names = {
            'A_context_memory':    'A.上下文记忆与继承',
            'B_intent_transition': 'B.意图转移与漂移',
            'C_coherence':         'C.对话连贯性与质量',
            'D_compliance':        'D.合规性与安全性',
        }
        for key, name in dim_names.items():
            score = report.dimension_scores.get(key, 0)
            lines.append(f"  {name:20s}: {score:6.1f}/100  {_bar(score / 100)}")

        # 逐轮详情
        lines.extend([
            "",
            "  " + "-" * 66,
            "  逐轮详情",
            "  " + "-" * 66,
        ])
        for r in round_rows:
            round_num = r.get('round', '?')
            intent = r.get('round_intent', '')
            actual = r.get('actual_intent', '')
            score = r.get('similarity_score', 0)
            passed = 'PASS' if r.get('round_pass', True) else 'FAIL'
            ctx = r.get('context_assert_type', 'normal')
            fail_reason = r.get('failure_reason', '')
            lines.append(
                f"  第{round_num}轮 | {passed} | 相似度={score:.0f} | "
                f"意图={intent} | 实际={actual} | 上下文={ctx}"
            )
            if fail_reason:
                lines.append(f"         失败原因: {fail_reason}")

        lines.append("")
        lines.append("=" * 70)
        return '\n'.join(lines)

    # ============================================================
    # 辅助方法
    # ============================================================

    @staticmethod
    def _find_stable_intent_segments(round_rows: List[Dict]) -> List[List[Dict]]:
        """找到连续相同 round_intent 的段落"""
        if not round_rows:
            return []
        segments = []
        current_seg = [round_rows[0]]
        for i in range(1, len(round_rows)):
            if round_rows[i].get('round_intent') == round_rows[i - 1].get('round_intent'):
                current_seg.append(round_rows[i])
            else:
                if len(current_seg) >= 2:
                    segments.append(current_seg)
                current_seg = [round_rows[i]]
        if len(current_seg) >= 2:
            segments.append(current_seg)
        return segments

    @staticmethod
    def _get_intent_category(intent: str) -> str:
        """将意图文本映射到业务大类"""
        if not intent:
            return '未知'
        mapping = {
            '提额降息': '提额降息', '提额': '提额降息', '降息': '提额降息',
            '常规咨询': '常规咨询', '额度': '常规咨询', '定价': '常规咨询', '账单': '常规咨询',
            '借款': '借款下单', '下单': '借款下单',
            '复合': '复合意图',
            '转人工': '转人工',
            '风险': '风险合规', '违规': '风险合规', '合规': '风险合规',
            '模糊': '模糊意图',
            '非业务': '非业务', '闲聊': '非业务',
        }
        for key, cat in mapping.items():
            if key in intent:
                return cat
        return '其他'


# ============================================================
# 批量分析工具函数
# ============================================================

def batch_analyze_dialogues(
    dialogue_list: List[Dict[str, Any]],
) -> List[MultiTurnQualityReport]:
    """
    批量分析多条多轮对话

    Args:
        dialogue_list: 每条对话包含:
            - case_id:    用例ID
            - case_desc:  用例描述
            - round_rows: 逐轮数据列表

    Returns:
        每条对话的质量报告列表

    Example:
        >>> dialogues = [
        ...     {'case_id': 'MD_0001', 'case_desc': '...', 'round_rows': [...]},
        ...     {'case_id': 'MD_0002', 'case_desc': '...', 'round_rows': [...]},
        ... ]
        >>> reports = batch_analyze_dialogues(dialogues)
        >>> for r in reports:
        ...     print(f"{r.case_id}: {r.overall_score:.1f}")
    """
    analyzer = MultiTurnQualityAnalyzer()
    return [
        analyzer.analyze(
            d.get('round_rows', []),
            case_id=d.get('case_id', ''),
            case_desc=d.get('case_desc', ''),
        )
        for d in dialogue_list
    ]


def aggregate_quality_reports(
    reports: List[MultiTurnQualityReport],
) -> Dict[str, Any]:
    """
    聚合多条对话的质量报告，生成宏观统计

    Args:
        reports: 多条对话的质量报告列表

    Returns:
        聚合统计字典，包含各维度的平均值、分布等
    """
    if not reports:
        return {'total_dialogues': 0}

    n = len(reports)
    avg_score = sum(r.overall_score for r in reports) / n

    # 各维度平均分
    dim_avgs = defaultdict(float)
    for r in reports:
        for dim, score in r.dimension_scores.items():
            dim_avgs[dim] += score
    for dim in dim_avgs:
        dim_avgs[dim] = round(dim_avgs[dim] / n, 2)

    # 异常终止比例
    abnormal_count = sum(1 for r in reports if r.abnormal_ending)

    # 质量分布
    quality_dist = {
        'excellent': sum(1 for r in reports if r.overall_score >= 85),
        'good':      sum(1 for r in reports if 70 <= r.overall_score < 85),
        'fair':      sum(1 for r in reports if 50 <= r.overall_score < 70),
        'poor':      sum(1 for r in reports if r.overall_score < 50),
    }

    return {
        'total_dialogues': n,
        'avg_overall_score': round(avg_score, 2),
        'dimension_avgs': dict(dim_avgs),
        'abnormal_ending_rate': round(abnormal_count / n, 4),
        'quality_distribution': quality_dist,
        'avg_inheritance_rate': round(
            sum(r.context_inheritance_rate for r in reports) / n, 4),
        'avg_drift_rate': round(
            sum(r.intent_drift_rate for r in reports) / n, 4),
        'avg_contamination_rate': round(
            sum(r.contamination_rate for r in reports) / n, 4),
        'avg_similarity': round(
            sum(r.avg_similarity for r in reports) / n, 2),
        'avg_round_pass_rate': round(
            sum(r.round_pass_rate for r in reports) / n, 4),
    }

def build_trajectory_from_intents(
    intents: List[str],
    *,
    start_state: str = 'INIT',
) -> List[Dict[str, Any]]:
    """
    从意图序列自动构建轨迹（按状态转移矩阵推导每轮的 current_state）

    这是一个便捷函数，用于从纯意图列表快速生成验证器可接受的 trajectory 格式。
    按顺序：每轮的 current_state = 上一轮的 expected_next_state。

    Args:
        intents:      按轮次排列的意图列表
        start_state:  起始状态，默认 'INIT'

    Returns:
        可用于 validate_multi_turn / analyze_drift 的 trajectory 列表

    Example:
        >>> intents = ['提额业务咨询', '提额准入条件咨询', '提额操作咨询']
        >>> trajectory = build_trajectory_from_intents(intents)
        >>> validator = SessionStateValidator()
        >>> result = validator.validate_multi_turn(trajectory)
    """
    validator = SessionStateValidator()
    trajectory = []
    current = start_state

    for i, intent in enumerate(intents):
        result = validator.validate_single_turn(current, intent, turn=i + 1)
        trajectory.append({
            'turn': i + 1,
            'current_state': current,
            'detected_intent': intent,
        })
        current = result.expected_next_state or current

    return trajectory


def compute_drift_between_trajectories(
    expected_intents: List[str],
    actual_intents: List[str],
    *,
    start_state: str = 'INIT',
) -> DriftReport:
    """
    对比期望意图序列和实际意图序列，计算漂移率

    期望序列按照状态转移矩阵推导"理想轨迹"，实际序列按同样规则推导"实际轨迹"，
    然后对比两者的差异。

    Args:
        expected_intents: 期望的意图序列（按轮次）
        actual_intents:   模型实际输出的意图序列（按轮次）
        start_state:      起始状态

    Returns:
        DriftReport 漂移分析报告

    Example:
        >>> expected = ['提额业务咨询', '提额准入条件咨询', '提额操作咨询']
        >>> actual   = ['提额业务咨询', '借款操作咨询',     '提额操作咨询']
        >>> report = compute_drift_between_trajectories(expected, actual)
        >>> print(f"漂移率: {report.drift_rate:.2%}")
    """
    validator = SessionStateValidator()
    max_len = max(len(expected_intents), len(actual_intents))

    trajectory = []
    expected_state = start_state
    actual_state = start_state

    for i in range(max_len):
        exp_intent = expected_intents[i] if i < len(expected_intents) else ''
        act_intent = actual_intents[i] if i < len(actual_intents) else ''

        # 使用 actual 的意图和 expected 推导的状态来做验证
        trajectory.append({
            'turn': i + 1,
            'current_state': expected_state,
            'detected_intent': act_intent,
            'expected_intent': exp_intent,
        })

        # 更新期望状态（按期望意图推导）
        if exp_intent:
            exp_result = validator.validate_single_turn(expected_state, exp_intent, turn=i + 1)
            expected_state = exp_result.expected_next_state or expected_state

        # 更新实际状态（按实际意图推导）
        if act_intent:
            act_result = validator.validate_single_turn(actual_state, act_intent, turn=i + 1)
            actual_state = act_result.expected_next_state or actual_state

    return validator.analyze_drift(trajectory)


# ============================================================
# 使用示例 & 自测
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("  会话状态转移合规性验证器 — 自测")
    print("=" * 60)

    validator = SessionStateValidator(mode=ValidationMode.STRICT)

    # ---- 示例 1: 单轮验证 ----
    print("\n[示例1] 单轮验证 — 正常转移")
    r = validator.validate_single_turn('INIT', '提额业务咨询')
    print(f"  is_valid={r.is_valid}, expected_next={r.expected_next_state}, severity={r.drift_severity.value}")
    assert r.is_valid and r.expected_next_state == 'TL_YWZX'

    print("\n[示例1b] 单轮验证 — 非法转移（提额流程中突然要借款）")
    r = validator.validate_single_turn('TL_ZRTJ', '借款操作咨询')
    print(f"  is_valid={r.is_valid}, expected_next={r.expected_next_state}, severity={r.drift_severity.value}")
    assert not r.is_valid

    print("\n[示例1c] 单轮验证 — 全局P0规则（任意状态转人工）")
    r = validator.validate_single_turn('TL_CQZX', '用户主动要求转人工')
    print(f"  is_valid={r.is_valid}, expected_next={r.expected_next_state}, severity={r.drift_severity.value}")
    assert r.is_valid and r.expected_next_state == 'RG_BZSQ'

    # ---- 示例 2: 多轮验证 — 正常轨迹 ----
    print("\n[示例2] 多轮验证 — 提额完整正常轨迹")
    normal_trajectory = build_trajectory_from_intents([
        '提额业务咨询', '提额准入条件咨询', '提额操作咨询',
        '提额材料咨询', '提额进度咨询', '提额结果咨询',
    ])
    result = validator.validate_multi_turn(normal_trajectory)
    print(f"  {result.summary}")
    assert result.drift_rate == 0.0, f"期望漂移率0%，实际 {result.drift_rate:.2%}"

    # ---- 示例 3: 多轮验证 — 有漂移 ----
    print("\n[示例3] 多轮验证 — 含意图漂移的轨迹")
    drift_trajectory = [
        {'turn': 1, 'current_state': 'INIT',    'detected_intent': '提额业务咨询'},
        {'turn': 2, 'current_state': 'TL_YWZX', 'detected_intent': '借款操作咨询'},   # 漂移！提额→借款
        {'turn': 3, 'current_state': 'JK_CQZX', 'detected_intent': '非业务相关'},     # 漂移！借款→闲聊
        {'turn': 4, 'current_state': 'INIT',    'detected_intent': '降息业务咨询'},
        {'turn': 5, 'current_state': 'JX_YWZX', 'detected_intent': '降息操作咨询'},
    ]
    result = validator.validate_multi_turn(drift_trajectory)
    print(f"  {result.summary}")
    for t in result.transitions:
        status = '[OK]' if t.is_valid else '[DRIFT]'
        print(f"    第{t.turn}轮 {status} {t.current_state} + [{t.detected_intent}] -> {t.expected_next_state or '无合法转移'} ({t.drift_severity.value})")

    # ---- 示例 4: 漂移分析报告 ----
    print("\n[示例4] 意图漂移分析报告")
    report = validator.analyze_drift(drift_trajectory)
    print(report.report_text)

    # ---- 示例 5: 对比期望 vs 实际意图序列 ----
    print("\n[示例5] 期望 vs 实际意图序列对比")
    expected_intents = ['提额业务咨询', '提额准入条件咨询', '提额操作咨询', '提额材料咨询']
    actual_intents   = ['提额业务咨询', '借款操作咨询',     '提额操作咨询', '非业务相关']
    report = compute_drift_between_trajectories(expected_intents, actual_intents)
    print(report.report_text)

    # ---- 示例 6: 全局P0规则优先级 ----
    print("\n[示例6] 全局P0规则 — 任意状态均可触发")
    for state in ['TL_CQZX', 'JX_JG', 'JK_CQZX', 'ZX_EDCX', 'INIT']:
        r = validator.validate_single_turn(state, '用户情绪升级')
        assert r.is_valid and r.expected_next_state == 'RG_QX_SJ', f"状态 {state} 应支持情绪升级转人工"
        print(f"  {state} + 用户情绪升级 -> {r.expected_next_state} [OK]")

    # ---- 示例 7: 获取合法下一状态 ----
    print("\n[示例7] 获取当前状态的合法下一状态列表")
    for state in ['INIT', 'TL_YWZX', 'ZX_EDCX', 'TL_JG']:
        states = validator.get_valid_next_states(state)
        print(f"  {state} -> {states}")

    # ---- 示例 8: 提额成功 -> 引导借款 闭环验证 ----
    print("\n[示例8] 提额/降息成功 -> 借款闭环验证")
    r1 = validator.validate_single_turn('TL_JG', '借款操作咨询')
    print(f"  提额成功 + 借款操作咨询 -> {r1.expected_next_state} (is_valid={r1.is_valid})")
    assert r1.is_valid and r1.expected_next_state == 'JK_CQZX'

    r2 = validator.validate_single_turn('JX_JG', '借款操作咨询')
    print(f"  降息成功 + 借款操作咨询 -> {r2.expected_next_state} (is_valid={r2.is_valid})")
    assert r2.is_valid and r2.expected_next_state == 'JK_CQZX'

    print("\n" + "=" * 60)
    print("  全部自测通过 [OK]")
    print("=" * 60)
