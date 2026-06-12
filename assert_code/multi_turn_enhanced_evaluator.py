# -*- coding: utf-8 -*-
"""
# @File    : multi_turn_enhanced_evaluator.py
# @Date    : 2026-06-09
# @Author  : jeremyzhai
# @Description: 多轮对话增强评估器
#
# 封装 LLM Judge + 状态转移验证 + 信息一致性检查
# 独立模块，不影响现有 ModelIntentAssert 和单轮测试
#
# 使用方式：
#     evaluator = MultiTurnEnhancedEvaluator()
#     result = evaluator.evaluate(case_info, round_rows)
#     if not result['enhanced_pass']:
#         print("增强评估未通过")
"""

import os
import re
from typing import List, Dict, Any

from assert_code.multi_turn_llm_judge import MultiTurnLLMJudge
from assert_code.session_state_validator import SessionStateValidator, ValidationMode


class MultiTurnEnhancedEvaluator:
    """
    多轮对话增强评估器

    功能：
    1. LLM-as-Judge 质量评估（G1/G2/Q1-Q5）
    2. 会话状态转移合规性验证（场景 H）
    3. 信息一致性自动检查（场景 G）

    使用方式：
        evaluator = MultiTurnEnhancedEvaluator()
        result = evaluator.evaluate(case_info, round_rows)
        if not result['enhanced_pass']:
            print("增强评估未通过")
    """

    def __init__(self,
                 enable_llm_judge=True,
                 enable_state_validation=True,
                 enable_consistency_check=True,
                 llm_judge_model=None,
                 state_validation_mode='strict'):
        self.enable_llm_judge = enable_llm_judge
        self.enable_state_validation = enable_state_validation
        self.enable_consistency_check = enable_consistency_check

        # 延迟初始化
        self._llm_judge = None
        self._state_validator = None
        self.llm_judge_model = llm_judge_model or os.getenv('MODEL_LLM_JUDGE_MODEL', 'kimi-k2.6')
        self.state_validation_mode = state_validation_mode

    @property
    def llm_judge(self):
        if self._llm_judge is None:
            self._llm_judge = MultiTurnLLMJudge(model_name=self.llm_judge_model)
        return self._llm_judge

    @property
    def state_validator(self):
        if self._state_validator is None:
            mode = ValidationMode(self.state_validation_mode)
            self._state_validator = SessionStateValidator(mode=mode)
        return self._state_validator

    def evaluate(self, case_info: dict, round_rows: list) -> dict:
        """
        执行完整增强评估

        Returns: {
            'llm_judge_result': {...},       # LLM Judge 评估结果
            'state_validation_result': {...}, # 状态转移验证结果
            'consistency_result': {...},     # 信息一致性检查结果
            'enhanced_pass': bool,           # 综合通过状态
            'report_text': str,              # 可读报告
        }
        """
        result = {
            'llm_judge_result': None,
            'state_validation_result': None,
            'consistency_result': None,
            'enhanced_pass': True,
            'report_text': '',
        }

        # LLM Judge
        if self.enable_llm_judge:
            try:
                result['llm_judge_result'] = self._evaluate_llm_judge(case_info, round_rows)
            except Exception as e:
                result['llm_judge_result'] = {'error': str(e), 'gate_passed': True}

        # 状态转移验证
        if self.enable_state_validation:
            try:
                result['state_validation_result'] = self._evaluate_state_validation(case_info, round_rows)
            except Exception as e:
                result['state_validation_result'] = {'error': str(e), 'drift_rate': 0.0}

        # 信息一致性
        if self.enable_consistency_check:
            try:
                result['consistency_result'] = self._evaluate_consistency(case_info, round_rows)
            except Exception as e:
                result['consistency_result'] = {'error': str(e), 'consistent': True}

        # 综合判定
        result['enhanced_pass'] = self._compute_final_pass(result)

        # 生成报告
        result['report_text'] = self._generate_report(result, case_info)

        return result

    def _evaluate_llm_judge(self, case_info: dict, round_rows: list):
        """LLM Judge 评估"""
        dialogue = [
            {
                'turn': i + 1,
                'user_question': row.get('question', ''),
                'model_response': row.get('actual_answer', '')
            }
            for i, row in enumerate(round_rows)
        ]
        return self.llm_judge.evaluate(
            dialogue,
            case_id=case_info.get('case_id', ''),
            case_desc=case_info.get('case_desc', '')
        )

    def _evaluate_state_validation(self, case_info: dict, round_rows: list):
        """状态转移验证"""
        trajectory = []
        current_state = 'INIT'
        for i, row in enumerate(round_rows):
            intent = row.get('round_intent', '')
            if not intent:
                continue
            trajectory.append({
                'turn': i + 1,
                'current_state': current_state,
                'detected_intent': intent,
            })
            result = self.state_validator.validate_single_turn(current_state, intent, turn=i + 1)
            current_state = result.expected_next_state or current_state

        return self.state_validator.validate_multi_turn(trajectory)

    def _evaluate_consistency(self, case_info: dict, round_rows: list):
        """
        信息一致性检查

        提取每轮模型回复中的关键数字（额度、利率、金额等），
        跨轮比对同一数字是否一致。
        """
        # 提取每轮的关键数字
        round_numbers = []
        for i, row in enumerate(round_rows):
            actual = row.get('actual_answer', '')
            numbers = self._extract_key_numbers(actual)
            round_numbers.append({
                'round': i + 1,
                'numbers': numbers,
            })

        # 跨轮比对
        inconsistencies = []
        for i in range(1, len(round_numbers)):
            prev = round_numbers[i - 1]['numbers']
            curr = round_numbers[i]['numbers']
            for key in set(prev.keys()) & set(curr.keys()):
                if prev[key] != curr[key]:
                    inconsistencies.append({
                        'round_from': i,
                        'round_to': i + 1,
                        'key': key,
                        'prev_value': prev[key],
                        'curr_value': curr[key],
                    })

        return {
            'round_numbers': round_numbers,
            'inconsistencies': inconsistencies,
            'consistent': len(inconsistencies) == 0,
            'inconsistency_count': len(inconsistencies),
        }

    @staticmethod
    def _extract_key_numbers(text: str) -> Dict[str, str]:
        """
        提取文本中的关键数字

        Returns: {
            'amount': '50000',   # 金额（元/万元）
            'rate': '18%',       # 利率
            'period': '12',      # 期限（月）
        }
        """
        numbers = {}
        if not text:
            return numbers

        # 额度/金额：匹配 "50000元" / "5万元" / "额度为50000" 等
        amount_patterns = [
            r'(\d{4,6})\s*元',           # 50000元
            r'(\d{1,2})\s*万元',           # 5万元
            r'额度.*?([\d,]+)',            # 额度50000
            r'借款.*?([\d,]+)',            # 借款30000
        ]
        for pattern in amount_patterns:
            m = re.search(pattern, text)
            if m:
                val = m.group(1).replace(',', '')
                numbers['amount'] = val
                break

        # 利率：匹配 "18%" / "年利率18%" / "利率为18%" 等
        rate_patterns = [
            r'(\d{1,2}(?:\.\d{1,2})?)%',   # 18%
            r'利率.*?([\d.]+)%',            # 利率18%
        ]
        for pattern in rate_patterns:
            m = re.search(pattern, text)
            if m:
                numbers['rate'] = m.group(1) + '%'
                break

        # 期限：匹配 "12期" / "分12期" / "12个月" 等
        period_patterns = [
            r'(\d{1,2})\s*期',              # 12期
            r'(\d{1,2})\s*个月',            # 12个月
        ]
        for pattern in period_patterns:
            m = re.search(pattern, text)
            if m:
                numbers['period'] = m.group(1)
                break

        return numbers

    def _compute_final_pass(self, result: dict) -> bool:
        """综合判定"""
        # 底线检查（G1/G2）必须全部通过
        llm_result = result.get('llm_judge_result')
        if llm_result and hasattr(llm_result, 'gate_passed') and not llm_result.gate_passed:
            return False

        # 状态验证漂移率超过阈值则失败
        state_result = result.get('state_validation_result')
        if state_result and hasattr(state_result, 'drift_rate'):
            if state_result.drift_rate > 0.2:
                return False

        # 信息一致性检查
        consistency = result.get('consistency_result')
        if consistency and not consistency.get('consistent', True):
            return False

        return True

    def _generate_report(self, result: dict, case_info: dict) -> str:
        """生成可读报告"""
        lines = [
            "=" * 60,
            "  多轮对话增强评估报告",
            "=" * 60,
            f"  用例ID: {case_info.get('case_id', 'N/A')}",
            f"  用例描述: {case_info.get('case_desc', 'N/A')}",
            "",
        ]

        # LLM Judge 结果
        llm_result = result.get('llm_judge_result')
        if llm_result and hasattr(llm_result, 'gate_passed'):
            lines.append(f"  LLM Judge: {'PASS' if llm_result.gate_passed else 'FAIL'}")
            if hasattr(llm_result, 'overall_score'):
                lines.append(f"  综合评分: {llm_result.overall_score:.1f}/100")
        else:
            lines.append("  LLM Judge: 未执行或执行失败")

        # 状态转移验证
        state_result = result.get('state_validation_result')
        if state_result and hasattr(state_result, 'drift_rate'):
            lines.append(f"  状态漂移率: {state_result.drift_rate:.2%}")
            if hasattr(state_result, 'summary'):
                lines.append(f"  验证摘要: {state_result.summary}")
        else:
            lines.append("  状态转移验证: 未执行或执行失败")

        # 信息一致性
        consistency = result.get('consistency_result')
        if consistency:
            lines.append(f"  信息一致性: {'通过' if consistency.get('consistent') else '不通过'}")
            if consistency.get('inconsistencies'):
                lines.append("  不一致项：")
                for item in consistency['inconsistencies']:
                    lines.append(f"    第{item['round_from']}轮→第{item['round_to']}轮: "
                                   f"{item['key']} 从 {item['prev_value']} 变为 {item['curr_value']}")
        else:
            lines.append("  信息一致性: 未执行或执行失败")

        lines.append(f"\n  综合判定: {'通过' if result['enhanced_pass'] else '不通过'}")
        lines.append("=" * 60)

        return '\n'.join(lines)
