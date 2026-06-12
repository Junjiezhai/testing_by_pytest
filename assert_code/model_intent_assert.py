# -*- coding: utf-8 -*-
"""
# @File    : model_intent_assert.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
"""

import json
import os
from enum import Enum
from jsonpath import jsonpath

from assert_code.external_model_judge import ExternalModelJudge
from common.modelHttpAction import ModelHttpAction
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data


class AssertMode(Enum):
    """断言模式枚举"""
    INTENT_SIMILARITY = "intent_similarity"      # 纯意图分类：一致性评分
    INTENT_CHECKLIST = "intent_checklist"        # 纯意图分类：细粒度清单
    INTENT_WITH_POST = "intent_with_post"        # 意图分类 + 后置操作组合


class ModelIntentAssert:
    """模型意图断言工具类"""

    REPLY_RULES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'model_intent_reply_rules.yaml')

    # P0 优化：ExternalModelJudge 实例缓存
    _judge_cache = None

    @classmethod
    def _get_judge(cls) -> ExternalModelJudge:
        """
        获取（或创建）ExternalModelJudge 实例（类级别缓存）

        首次调用时创建实例并缓存，后续调用直接复用。
        避免每条用例都创建新的 ExternalModelJudge 实例，
        从而避免重复加载知识库、重复初始化模型客户端。

        环境变量控制：
            MODEL_INJECT_KNOWLEDGE_AS_SYSTEM
                - '1' / 'true' / 'True' / 未设置：注入完整知识库到系统提示词（默认）
                - '0' / 'false' / 'False'：不注入，使用传统提示词方式

        Returns:
            ExternalModelJudge 实例
        """
        if cls._judge_cache is None:
            inject = os.getenv('MODEL_INJECT_KNOWLEDGE_AS_SYSTEM', '1').strip().lower()
            inject_knowledge = inject in ('', '1', 'true', 'yes')
            cls._judge_cache = ExternalModelJudge(
                model_name='deepseek-v4-pro',
                use_knowledge_base=True,
                inject_knowledge_as_system=inject_knowledge,
            )
            mode = '完整知识库注入（系统提示词）' if inject_knowledge else '简洁提示词（不注入系统提示词）'
            log.info(f"ExternalModelJudge 实例已创建并缓存 —— 知识注入模式：{mode}")
        return cls._judge_cache

    # ============================================================
    # 断言模式管理
    # ============================================================

    @classmethod
    def get_assert_mode(cls) -> AssertMode:
        """
        获取当前断言模式
        优先级：环境变量 MODEL_ASSERT_MODE > 默认值 INTENT_SIMILARITY
        """
        mode_str = os.getenv('MODEL_ASSERT_MODE', 'intent_similarity').strip().lower()
        mode_map = {
            'intent_similarity': AssertMode.INTENT_SIMILARITY,
            'similarity': AssertMode.INTENT_SIMILARITY,
            'intent_checklist': AssertMode.INTENT_CHECKLIST,
            'checklist': AssertMode.INTENT_CHECKLIST,
            'intent_with_post': AssertMode.INTENT_WITH_POST,
            'with_post': AssertMode.INTENT_WITH_POST,
            'post': AssertMode.INTENT_WITH_POST,
        }
        mode = mode_map.get(mode_str)
        if mode is None:
            log.warning(f"不支持的断言模式: {mode_str}，使用默认模式 INTENT_SIMILARITY")
            return AssertMode.INTENT_SIMILARITY
        return mode

    @classmethod
    def _evaluate_by_mode(cls, case_info: dict, output_data, response_time: float,
                           assert_mode: AssertMode = None) -> dict:
        """
        根据断言模式分发到对应的单轮评估逻辑

        Args:
            case_info: 用例信息
            output_data: 模型返回数据
            response_time: 响应耗时
            assert_mode: 断言模式，None 时从环境变量读取

        Returns:
            评估结果字典
        """
        if assert_mode is None:
            assert_mode = cls.get_assert_mode()

        if assert_mode == AssertMode.INTENT_SIMILARITY:
            return cls._evaluate_single_turn_similarity(case_info, output_data, response_time)
        elif assert_mode == AssertMode.INTENT_CHECKLIST:
            return cls._evaluate_single_turn_checklist(case_info, output_data, response_time)
        elif assert_mode == AssertMode.INTENT_WITH_POST:
            return cls._evaluate_single_turn_with_post(case_info, output_data, response_time)
        else:
            log.warning(f"不支持的断言模式: {assert_mode}，使用默认模式")
            return cls._evaluate_single_turn_similarity(case_info, output_data, response_time)

    # ============================================================
    # 单轮对话断言 —— 一致性评分模式（原逻辑）
    # ============================================================

    @classmethod
    def _evaluate_similarity(cls, actual_answer: str, expected_answer: str, *,
                               intent: str = None) -> dict:
        """
        使用 ExternalModelJudge 评估语义相似度
        仅基于标准答案进行评估，返回单一评分结果

        Args:
            actual_answer: 实际模型输出
            expected_answer: 标准答案
            intent: 意图分类（用于注入知识库上下文）

        Returns:
            {
                'similarity_score': float,
                'is_same_meaning': bool,
                'reason': str
            }
        """
        judge = cls._get_judge()

        # 标准答案相似度（注入意图知识）
        standard_result = judge.similarity_score(actual_answer, expected_answer, intent=intent)
        return {
            'similarity_score': float(standard_result.score),
            'is_same_meaning': standard_result.score >= 80,
            'reason': standard_result.reason,
        }

    # ============================================================
    # 原有方法
    # ============================================================

    @classmethod
    def load_reply_rules(cls) -> dict:
        rules = read_yaml_data(cls.REPLY_RULES_FILE) or {}
        return rules if isinstance(rules, dict) else {}

    @classmethod
    def get_intent_rule(cls, intent: str) -> dict:
        rules = cls.load_reply_rules()
        defaults = rules.get('defaults', {}) if isinstance(rules.get('defaults', {}), dict) else {}
        intents = rules.get('intents', {}) if isinstance(rules.get('intents', {}), dict) else {}
        intent_rule = intents.get(intent, {}) if isinstance(intents.get(intent, {}), dict) else {}
        text_default = defaults.get('text', {}) if isinstance(defaults.get('text', {}), dict) else {}
        asset_default = defaults.get('asset', {}) if isinstance(defaults.get('asset', {}), dict) else {}
        text_rule = intent_rule.get('text', {}) if isinstance(intent_rule.get('text', {}), dict) else {}
        asset_rule = intent_rule.get('asset', {}) if isinstance(intent_rule.get('asset', {}), dict) else {}
        return {
            'text': {
                'threshold': text_rule.get('threshold', text_default.get('threshold', 80)),
                'comparator': text_rule.get('comparator', text_default.get('comparator', 'gte')),
            },
            'asset': {
                'allowed': asset_rule.get('allowed', asset_default.get('allowed', False)),
                'value_allowlist': asset_rule.get('value_allowlist', asset_default.get('value_allowlist', [])) or [],
                'biz_ref_id_allowlist': asset_rule.get('biz_ref_id_allowlist', asset_default.get('biz_ref_id_allowlist', [])) or [],
                'biz_ref_id_allowlist_by_value': asset_rule.get('biz_ref_id_allowlist_by_value', {}) or {},
            }
        }

    @classmethod
    def _clean_text(cls, value) -> str:
        return str(value).strip() if value is not None else ''

    @classmethod
    def _ensure_list(cls, value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @classmethod
    def _extract_reply_contents(cls, output_data) -> dict:
        reply_contents = []
        chat_type = ''
        handoff_reason = ''
        if isinstance(output_data, dict):
            data = output_data.get('data', {}) if isinstance(output_data.get('data', {}), dict) else {}
            chat_type = cls._clean_text(data.get('chatType')).upper()
            handoff_reason = cls._clean_text(data.get('handoffReason'))
            reply_contents = data.get('replyContents') or []
            if not isinstance(reply_contents, list):
                reply_contents = []

        text_values = []
        asset_values = []
        biz_ref_ids = []
        raw_items = []
        if chat_type and chat_type != 'NORMAL':
            return {
                'chat_type': chat_type,
                'handoff_reason': handoff_reason,
                'reply_contents_raw': reply_contents,
                'raw_items': raw_items,
                'text_values': text_values,
                'text_answer': '',
                'asset_values': asset_values,
                'asset_value': '',
                'biz_ref_ids': biz_ref_ids,
                'biz_ref_id': ''
            }
        for item in reply_contents:
            if not isinstance(item, dict):
                continue
            raw_items.append(item)
            item_type = cls._clean_text(item.get('type')).upper()
            value = item.get('value')
            if item_type == 'TEXT' and cls._clean_text(value):
                text_values.append(cls._clean_text(value))
            elif item_type == 'ASSET' and cls._clean_text(value):
                asset_values.append(cls._clean_text(value))
                biz_param_info = item.get('bizParamInfo') or {}
                biz_ref_id = biz_param_info.get('biz_ref_id')
                for ref_id in cls._ensure_list(biz_ref_id):
                    ref_text = cls._clean_text(ref_id)
                    if ref_text:
                        biz_ref_ids.append(ref_text)

        return {
            'chat_type': chat_type,
            'handoff_reason': handoff_reason,
            'reply_contents_raw': reply_contents,
            'raw_items': raw_items,
            'text_values': text_values,
            'text_answer': ' '.join(text_values).strip(),
            'asset_values': asset_values,
            'asset_value': asset_values[0] if asset_values else '',
            'biz_ref_ids': biz_ref_ids,
            'biz_ref_id': biz_ref_ids[0] if biz_ref_ids else ''
        }

    @classmethod
    def extract_model_answer(cls, output_data) -> str:
        """
        从信贷大模型返回结果中提取话术文本
        :param output_data: 信贷大模型接口返回
        :return:
        """
        if output_data is None:
            return ''
        if isinstance(output_data, str):
            return output_data

        reply_info = cls._extract_reply_contents(output_data=output_data)
        if reply_info.get('text_answer'):
            return reply_info['text_answer']

        answer_keys = [
            'value', 'answer', 'reply', 'content', 'message', 'text', 'response', 'result',
            'answerContent', 'replyContent', 'msgContent', 'robotAnswer', 'standardAnswer'
        ]
        for key in answer_keys:
            try:
                res = jsonpath(output_data, f'$..{key}')
                if res and str(res[0]).strip():
                    return str(res[0]).strip()
            except Exception:
                continue

        return json.dumps(output_data, ensure_ascii=False)

    @classmethod
    def extract_model_intent(cls, output_data) -> str:
        """
        从信贷大模型返回结果中提取意图
        :param output_data: 信贷大模型接口返回
        :return:
        """
        if output_data is None or isinstance(output_data, str):
            return ''

        intent_keys = ['intent', 'intentName', 'intentCode', 'intentType', 'label', 'category', 'scene']
        for key in intent_keys:
            try:
                res = jsonpath(output_data, f'$..{key}')
                if res and str(res[0]).strip():
                    return str(res[0]).strip()
            except Exception:
                continue

        return ''

    @classmethod
    def _compare_threshold(cls, score: float, threshold: float, comparator: str) -> bool:
        comparator = cls._clean_text(comparator).lower() or 'gte'
        if comparator == 'gt':
            return score > threshold
        return score >= threshold

    @classmethod
    def _is_transfer_intent(cls, intent: str) -> bool:
        return cls._clean_text(intent) == '转人工'

    @classmethod
    def _evaluate_chat_type_result(cls, intent: str, reply_info: dict) -> dict:
        chat_type = reply_info.get('chat_type') or 'NORMAL'
        chat_type_pass = True
        fail_reasons = []
        if chat_type == 'TRANSFER':
            chat_type_pass = cls._is_transfer_intent(intent)
            if not chat_type_pass:
                fail_reasons.append(f"当前意图[{intent}]不允许转人工，但chatType=TRANSFER")
        elif chat_type != 'NORMAL':
            chat_type_pass = False
            fail_reasons.append(f"chatType={chat_type} 不在允许范围 NORMAL/TRANSFER 内")
        return {
            'chat_type': chat_type,
            'handoff_reason': reply_info.get('handoff_reason', ''),
            'is_transfer': chat_type == 'TRANSFER',
            'chat_type_pass': chat_type_pass,
            'chat_type_failure_reasons': fail_reasons,
        }

    @classmethod
    def evaluate_single_turn(cls, case_info: dict, output_data, response_time: float, assert_mode: AssertMode = None) -> dict:
        """
        单轮问答评估（支持断言模式切换）
        :param case_info: 用例信息
        :param output_data: 信贷大模型返回
        :param response_time: 响应耗时
        :param assert_mode: 断言模式，None 时从环境变量读取
        :return:
        """
        if assert_mode is None:
            assert_mode = cls.get_assert_mode()

        # 断言模式分发
        if assert_mode == AssertMode.INTENT_CHECKLIST:
            return cls._evaluate_single_turn_checklist(case_info, output_data, response_time)
        elif assert_mode == AssertMode.INTENT_WITH_POST:
            return cls._evaluate_single_turn_with_post(case_info, output_data, response_time)

        # 默认：一致性评分模式（原逻辑）
        reply_info = cls._extract_reply_contents(output_data=output_data)
        actual_answer = cls.extract_model_answer(output_data=output_data)
        actual_intent = cls.extract_model_intent(output_data=output_data)
        expected_answer = case_info['expected_answer']
        reference_answer = cls._clean_text(case_info.get('reference_answer')) or expected_answer
        rule_intent = actual_intent or case_info['intent']
        intent_rule = cls.get_intent_rule(rule_intent)
        text_threshold = float(intent_rule['text'].get('threshold', case_info['similarity_threshold']))
        text_comparator = cls._clean_text(intent_rule['text'].get('comparator', 'gte')) or 'gte'
        asset_allowed = bool(intent_rule['asset'].get('allowed', False))
        asset_values_allowlist = [cls._clean_text(item) for item in cls._ensure_list(intent_rule['asset'].get('value_allowlist', [])) if cls._clean_text(item)]
        biz_ref_id_allowlist = [cls._clean_text(item) for item in cls._ensure_list(intent_rule['asset'].get('biz_ref_id_allowlist', [])) if cls._clean_text(item)]

        chat_type_eval = cls._evaluate_chat_type_result(case_info['intent'], reply_info)
        if chat_type_eval['is_transfer']:
            similarity_score = 100 if chat_type_eval['chat_type_pass'] else 0
            text_pass = chat_type_eval['chat_type_pass']
            similarity_res = {
                'similarity_score': similarity_score,
                'is_same_meaning': chat_type_eval['chat_type_pass'],
                'reason': 'chatType=TRANSFER，模型已转人工处理'
            }
        else:
            answer_for_eval = reply_info.get('text_answer') or actual_answer
            similarity_res = cls._evaluate_similarity(
                actual_answer=answer_for_eval,
                expected_answer=expected_answer,
                intent=case_info['intent']
            )
            similarity_score = round(similarity_res['similarity_score'], 2)
            text_pass = cls._compare_threshold(similarity_score, text_threshold, text_comparator)

        asset_present = bool(reply_info.get('asset_values'))
        asset_value = reply_info.get('asset_value', '')
        biz_ref_id = reply_info.get('biz_ref_id', '')
        asset_value_pass = True
        biz_ref_id_pass = True
        asset_allow_pass = True
        fail_reasons = []
        # 根据 value 进行针对性的 biz_ref_id 校验
        biz_ref_id_allowlist_by_value = intent_rule['asset'].get('biz_ref_id_allowlist_by_value', {})

        if not chat_type_eval['chat_type_pass']:
            fail_reasons.extend(chat_type_eval['chat_type_failure_reasons'])
        if asset_present:
            asset_allow_pass = asset_allowed
            asset_value_pass = asset_value in asset_values_allowlist if asset_values_allowlist else False
            # 根据 ASSET value 进行针对性的 biz_ref_id 校验
            if biz_ref_id_allowlist_by_value and asset_value in biz_ref_id_allowlist_by_value:
                specific_biz_ref_list = [cls._clean_text(item) for item in cls._ensure_list(biz_ref_id_allowlist_by_value[asset_value]) if cls._clean_text(item)]
                biz_ref_id_pass = biz_ref_id in specific_biz_ref_list
            elif biz_ref_id_allowlist:
                biz_ref_id_pass = biz_ref_id in biz_ref_id_allowlist
            else:
                biz_ref_id_pass = True
            if not asset_allow_pass:
                fail_reasons.append(f"当前意图[{rule_intent}]不允许输出ASSET，但实际返回了ASSET")
            if not asset_values_allowlist:
                fail_reasons.append(f"当前意图[{rule_intent}]未配置ASSET.value允许范围")
            elif not asset_value_pass:
                fail_reasons.append(f"ASSET.value={asset_value} 不在允许范围内")
            if not biz_ref_id_pass:
                if biz_ref_id_allowlist_by_value and asset_value in biz_ref_id_allowlist_by_value:
                    fail_reasons.append(f"biz_ref_id={biz_ref_id} 不在ASSET.value={asset_value}的允许范围内")
                else:
                    fail_reasons.append(f"biz_ref_id={biz_ref_id} 不在允许范围内")
        if not text_pass:
            fail_reasons.append(f"TEXT评分 {similarity_score} 未达到阈值 {text_threshold}({text_comparator})")

        is_pass = chat_type_eval['chat_type_pass'] and text_pass and asset_allow_pass and asset_value_pass and biz_ref_id_pass
        report_row = {
            'case_id': case_info['case_id'],
            'case_type': case_info['case_type'],
            'case_desc': case_info['case_desc'],
            'intent': case_info['intent'],
            'actual_intent': actual_intent,
            'question': case_info['question'],
            'expected_answer': expected_answer,
            'actual_answer': actual_answer,
            'chat_type': chat_type_eval['chat_type'],
            'handoff_reason': chat_type_eval['handoff_reason'],
            'chat_type_pass': chat_type_eval['chat_type_pass'],
            'reply_contents_raw': json.dumps(reply_info.get('reply_contents_raw'), ensure_ascii=False),
            'text_values': json.dumps(reply_info.get('text_values'), ensure_ascii=False),
            'asset_values': json.dumps(reply_info.get('asset_values'), ensure_ascii=False),
            'biz_ref_ids': json.dumps(reply_info.get('biz_ref_ids'), ensure_ascii=False),
            'is_same_meaning': similarity_res.get('is_same_meaning'),
            'similarity_score': similarity_score,
            'similarity_reason': similarity_res.get('reason'),
            'similarity_threshold': case_info['similarity_threshold'],
            'text_threshold': text_threshold,
            'text_comparator': text_comparator,
            'text_pass': text_pass,
            'asset_present': asset_present,
            'asset_allowed': asset_allowed,
            'asset_value': asset_value,
            'asset_value_pass': asset_value_pass,
            'biz_ref_id': biz_ref_id,
            'biz_ref_id_pass': biz_ref_id_pass,
            'fail_reasons': fail_reasons,
            'failure_reason': '；'.join(fail_reasons),
            'similarity_pass': text_pass,
            'response_time': round(response_time, 3),
            'is_pass': is_pass,
            'assert_detail': {
                'chat_type': chat_type_eval['chat_type'],
                'handoff_reason': chat_type_eval['handoff_reason'],
                'chat_type_pass': chat_type_eval['chat_type_pass'],
                'text_pass': text_pass,
                'text_threshold': text_threshold,
                'text_comparator': text_comparator,
                'similarity_score': similarity_score,
                'similarity_reason': similarity_res.get('reason'),
                'asset_present': asset_present,
                'asset_allowed': asset_allowed,
                'asset_value': asset_value,
                'asset_value_pass': asset_value_pass,
                'biz_ref_id': biz_ref_id,
                'biz_ref_id_pass': biz_ref_id_pass,
                'fail_reasons': fail_reasons,
            },
            'output_data': json.dumps(output_data, ensure_ascii=False)
        }
        log.info(f"模型评估结果：{report_row}")
        return report_row

    @classmethod
    def evaluate_asset_result(cls, intent: str, reply_info: dict) -> dict:
        intent_rule = cls.get_intent_rule(intent)
        asset_allowed = bool(intent_rule['asset'].get('allowed', False))
        asset_values_allowlist = [cls._clean_text(item) for item in cls._ensure_list(intent_rule['asset'].get('value_allowlist', [])) if cls._clean_text(item)]
        biz_ref_id_allowlist = [cls._clean_text(item) for item in cls._ensure_list(intent_rule['asset'].get('biz_ref_id_allowlist', [])) if cls._clean_text(item)]
        biz_ref_id_allowlist_by_value = intent_rule['asset'].get('biz_ref_id_allowlist_by_value', {})
        asset_present = bool(reply_info.get('asset_values'))
        asset_value = reply_info.get('asset_value', '')
        biz_ref_id = reply_info.get('biz_ref_id', '')
        asset_allow_pass = True
        asset_value_pass = True
        biz_ref_id_pass = True
        fail_reasons = []
        if asset_present:
            asset_allow_pass = asset_allowed
            asset_value_pass = asset_value in asset_values_allowlist if asset_values_allowlist else False
            # 根据 ASSET value 进行针对性的 biz_ref_id 校验
            if biz_ref_id_allowlist_by_value and asset_value in biz_ref_id_allowlist_by_value:
                specific_biz_ref_list = [cls._clean_text(item) for item in cls._ensure_list(biz_ref_id_allowlist_by_value[asset_value]) if cls._clean_text(item)]
                biz_ref_id_pass = biz_ref_id in specific_biz_ref_list
            elif biz_ref_id_allowlist:
                biz_ref_id_pass = biz_ref_id in biz_ref_id_allowlist
            else:
                biz_ref_id_pass = True
            if not asset_allow_pass:
                fail_reasons.append(f"当前意图[{intent}]不允许输出ASSET，但实际返回了ASSET")
            if not asset_values_allowlist:
                fail_reasons.append(f"当前意图[{intent}]未配置ASSET.value允许范围")
            elif not asset_value_pass:
                fail_reasons.append(f"ASSET.value={asset_value} 不在允许范围内")
            if not biz_ref_id_pass:
                if biz_ref_id_allowlist_by_value and asset_value in biz_ref_id_allowlist_by_value:
                    fail_reasons.append(f"biz_ref_id={biz_ref_id} 不在ASSET.value={asset_value}的允许范围内")
                else:
                    fail_reasons.append(f"biz_ref_id={biz_ref_id} 不在允许范围内")
        return {
            'asset_present': asset_present,
            'asset_allowed': asset_allowed,
            'asset_value': asset_value,
            'asset_value_pass': asset_value_pass,
            'biz_ref_id': biz_ref_id,
            'biz_ref_id_pass': biz_ref_id_pass,
            'asset_allow_pass': asset_allow_pass,
            'asset_pass': asset_allow_pass and asset_value_pass and biz_ref_id_pass,
            'asset_failure_reasons': fail_reasons,
        }

    @classmethod
    def evaluate_multi_turn_round(cls, round_info: dict, output_data, context_rounds: list, response_time: float, similarity_threshold: float, assert_mode: AssertMode = None) -> dict:
        """
        多轮单轮评估（已统一为一次性多维度评分）

        注意：此方法现在返回占位结果，实际的多维度评估在 test_multi_turn_dialog_consistency 中
        通过 MultiTurnEvaluator.evaluate_single 统一进行。

        :param round_info: 轮次信息
        :param output_data: 模型返回
        :param context_rounds: 上下文轮次
        :param response_time: 响应耗时
        :param similarity_threshold: 相似度阈值
        :param assert_mode: 断言模式，None 时从环境变量读取
        :return: 占位结果
        """
        # 提取基本信息
        actual_answer = cls.extract_model_answer(output_data=output_data) if output_data else ''
        expected_answer = round_info.get('expected_answer', '')
        round_intent = round_info.get('round_intent', '')

        # 提取回复信息（用于展示，chatType/ASSET断言在汇总阶段统一进行）
        reply_info = cls._extract_reply_contents(output_data=output_data) if output_data else {}
        chat_type = reply_info.get('chat_type', 'NORMAL') if reply_info else 'NORMAL'
        handoff_reason = reply_info.get('handoff_reason', '') if reply_info else ''

        return {
            'round': round_info.get('round', 0),
            'question': round_info.get('question', ''),
            'expected_answer': expected_answer,
            'reference_answer': cls._clean_text(round_info.get('reference_answer')) or expected_answer,
            'actual_answer': actual_answer,
            'round_intent': round_intent,
            'actual_intent': '',
            'chat_type': chat_type,
            'handoff_reason': handoff_reason,
            'chat_type_pass': True,  # 占位：汇总阶段统一断言
            'previous_intent': round_info.get('previous_intent', ''),
            'context_assert_type': round_info.get('context_assert_type', 'normal'),
            'expect_refuse': bool(round_info.get('expect_refuse')),
            'standard_similarity_score': 0,
            'reference_similarity_score': 0,
            'similarity_score': 0,
            'similarity_pass': True,
            'similarity_reason': '等待一次性多维度评估',
            'intent_pass': True,
            'intent_reason': '',
            'context_carry_pass': True,
            'intent_pollution_pass': True,
            'user_correction_pass': True,
            'risk_refusal_pass': True,
            'return_to_business_pass': True,
            'context_reason': '等待一次性多维度评估',
            'asset_present': False,  # 占位：汇总阶段统一断言
            'asset_allowed': False,
            'asset_value': '',
            'asset_value_pass': True,
            'biz_ref_id': '',
            'biz_ref_id_pass': True,
            'asset_allow_pass': True,
            'asset_pass': True,  # 占位：汇总阶段统一断言
            'asset_failure_reasons': [],
            'assert_items': [],
            'failed_assert_items': [],
            'failure_suggestions': [],
            'should_assert': round_info.get('should_assert', True),
            'response_time': round(response_time, 3),
            'round_pass': True,
            'failure_reason': '等待一次性多维度评估',
            'request_data': round_info.get('request_data'),
            'output_data': output_data,
        }

    @classmethod
    def evaluate_answer(cls, actual_answer: str, expected_answer: str, similarity_threshold: float, reference_answer: str = '') -> dict:
        """
        单句答案相似度评估
        :param actual_answer: 实际回复
        :param expected_answer: 标准回复
        :param similarity_threshold: 相似度阈值
        :param reference_answer: 外部模型参考答案（已废弃，保留参数用于兼容）
        :return:
        """
        similarity_res = cls._evaluate_similarity(
            actual_answer=actual_answer,
            expected_answer=expected_answer,
            intent=''  # evaluate_answer 是通用方法，不绑定具体意图
        )
        similarity_score = round(similarity_res['similarity_score'], 2)
        return {
            'expected_answer': expected_answer,
            'actual_answer': actual_answer,
            'is_same_meaning': similarity_res.get('is_same_meaning'),
            'similarity_score': similarity_score,
            'similarity_reason': similarity_res.get('reason'),
            'similarity_pass': similarity_score >= similarity_threshold
        }

    @classmethod
    def evaluate_multi_turn_enhanced(cls, case_info: dict, round_rows: list,
                                     round_eval_results: list = None,
                                     enable_llm_judge: bool = True,
                                     enable_state_validation: bool = True,
                                     enable_consistency_check: bool = True,
                                     llm_judge_model: str = None,
                                     state_validation_mode: str = 'strict') -> dict:
        """
        多轮增强评估

        在 evaluate_multi_turn_round 基础上增加：
        - LLM Judge 评估（G1/G2/Q1-Q5）
        - 会话状态转移合规性验证
        - 信息一致性自动检查

        Args:
            case_info: 用例信息
            round_rows: 多轮对话数据
            round_eval_results: 逐轮评估结果（来自 evaluate_multi_turn_round），可选
            enable_llm_judge: 是否启用 LLM Judge
            enable_state_validation: 是否启用状态转移验证
            enable_consistency_check: 是否启用信息一致性检查
            llm_judge_model: LLM Judge 使用的模型名称
            state_validation_mode: 状态转移验证模式

        Returns:
            增强评估结果字典
        """
        try:
            from assert_code.multi_turn_enhanced_evaluator import MultiTurnEnhancedEvaluator
            evaluator = MultiTurnEnhancedEvaluator(
                enable_llm_judge=enable_llm_judge,
                enable_state_validation=enable_state_validation,
                enable_consistency_check=enable_consistency_check,
                llm_judge_model=llm_judge_model,
                state_validation_mode=state_validation_mode,
            )
            return evaluator.evaluate(case_info, round_rows)
        except Exception as e:
            log.warning(f"【增强评估】初始化失败：{e}")
            import traceback
            log.warning(traceback.format_exc())
            return None

    @classmethod
    def assert_model_result(cls, report_row: dict) -> None:
        """
        模型评估结果断言
        :param report_row: 评估明细
        :return:
        """
        assert report_row['is_pass'] is True, f"模型断言失败：{report_row.get('failure_reason') or report_row.get('similarity_reason') or report_row.get('similarity_score')}"

    # ============================================================
    # 单轮断言扩展：细粒度清单模式
    # ============================================================

    @classmethod
    def _evaluate_single_turn_checklist(cls, case_info: dict, output_data, response_time: float) -> dict:
        """
        单轮：细粒度清单断言模式
        调用 ExternalModelJudge 进行多维度检查清单评估，并联动混淆矩阵
        """
        reply_info = cls._extract_reply_contents(output_data=output_data)
        actual_answer = cls.extract_model_answer(output_data=output_data)
        actual_intent = cls.extract_model_intent(output_data=output_data)
        expected_answer = case_info['expected_answer']
        reference_answer = cls._clean_text(case_info.get('reference_answer')) or expected_answer

        # 会话类型评估
        chat_type_eval = cls._evaluate_chat_type_result(case_info['intent'], reply_info)

        # 使用 ExternalModelJudge 进行检查清单评估（细粒度清单模式不需要知识库）
        judge = ExternalModelJudge(model_name='deepseek-v4-pro', max_tokens=8192, use_knowledge_base=False)
        try:
            checklist_result = judge.evaluate(actual_answer, expected_answer)
            is_pass = checklist_result.verdict.value in ['通过', '条件通过']
            score = checklist_result.score * 100  # 映射到 0-100
            checklist_detail = checklist_result.to_dict()
        except Exception as e:
            log.error(f"检查清单评估异常: {e}")
            is_pass = False
            score = 0.0
            checklist_detail = {'error': str(e)}

        # 收集意图数据用于混淆矩阵
        cls._collect_intent_for_confusion_matrix(case_info['intent'], actual_intent)

        report_row = {
            'case_id': case_info['case_id'],
            'case_type': case_info['case_type'],
            'case_desc': case_info['case_desc'],
            'intent': case_info['intent'],
            'actual_intent': actual_intent,
            'question': case_info['question'],
            'expected_answer': expected_answer,
            'reference_answer': reference_answer,
            'actual_answer': actual_answer,
            'chat_type': chat_type_eval['chat_type'],
            'handoff_reason': chat_type_eval['handoff_reason'],
            'chat_type_pass': chat_type_eval['chat_type_pass'],
            'assert_mode': 'intent_checklist',
            'checklist_result': checklist_detail,
            'similarity_score': score,
            'similarity_reason': checklist_detail.get('summary', ''),
            'similarity_threshold': case_info['similarity_threshold'],
            'similarity_pass': is_pass,
            'is_pass': is_pass,
            'response_time': round(response_time, 3),
            'failure_reason': checklist_detail.get('summary', '') if not is_pass else '',
            'output_data': json.dumps(output_data, ensure_ascii=False)
        }
        log.info(f"检查清单评估结果: verdict={'通过' if is_pass else '失败'}, score={score:.2f}")
        return report_row

    # ============================================================
    # 单轮断言扩展：意图分类 + 后置操作组合
    # ============================================================

    @classmethod
    def _evaluate_single_turn_with_post(cls, case_info: dict, output_data, response_time: float) -> dict:
        """
        单轮：意图分类 + 后置操作组合断言
        先执行意图相似度评估，再叠加后置操作（ASSET、转人工等）校验
        """
        # 第一步：执行意图相似度评估
        similarity_result = cls.evaluate_single_turn(case_info, output_data, response_time, assert_mode=AssertMode.INTENT_SIMILARITY)

        # 第二步：执行后置操作断言
        reply_info = cls._extract_reply_contents(output_data=output_data)
        post_result = cls._assert_post_operations(reply_info, case_info['intent'])

        # 综合结果
        is_pass = similarity_result['is_pass'] and post_result['post_pass']

        # 合并失败原因
        fail_reasons = []
        if not similarity_result['is_pass']:
            fail_reasons.append(f"意图评估失败：{similarity_result.get('failure_reason', '')}")
        if not post_result['post_pass']:
            fail_reasons.extend(post_result.get('post_failure_reasons', []))

        report_row = dict(similarity_result)
        report_row['assert_mode'] = 'intent_with_post'
        report_row['post_assert'] = post_result
        report_row['is_pass'] = is_pass
        report_row['failure_reason'] = '；'.join(fail_reasons) if fail_reasons else ''

        return report_row

    # ============================================================
    # 后置操作断言抽象
    # ============================================================

    @classmethod
    def _assert_post_operations(cls, reply_info: dict, intent: str) -> dict:
        """
        后置操作断言抽象（ASSET校验、转人工校验等）
        支持横向扩展，新增后置操作只需在此添加逻辑

        Args:
            reply_info: 模型回复信息（_extract_reply_contents 的结果）
            intent: 期望意图

        Returns:
            {
                'post_pass': bool,
                'post_failure_reasons': list[str],
                'chat_type_pass': bool,
                'asset_pass': bool,
                # ... 可扩展更多断言项
            }
        """
        fail_reasons = []

        # 1. 会话类型断言（转人工校验）
        chat_type = reply_info.get('chat_type', 'NORMAL')
        chat_type_pass = True
        if chat_type == 'TRANSFER' and not cls._is_transfer_intent(intent):
            chat_type_pass = False
            fail_reasons.append(f"意图[{intent}]不允许转人工，但chatType=TRANSFER")
        elif chat_type not in ['NORMAL', 'TRANSFER']:
            chat_type_pass = False
            fail_reasons.append(f"chatType={chat_type} 不在允许范围 NORMAL/TRANSFER 内")

        # 2. ASSET 卡片断言
        asset_result = cls.evaluate_asset_result(intent, reply_info)
        asset_pass = asset_result['asset_pass']
        if not asset_pass:
            fail_reasons.extend(asset_result['asset_failure_reasons'])

        # 综合结果
        post_pass = chat_type_pass and asset_pass

        return {
            'post_pass': post_pass,
            'post_failure_reasons': fail_reasons,
            'chat_type_pass': chat_type_pass,
            'asset_pass': asset_pass,
            'asset_detail': asset_result,
        }

    # ============================================================
    # 混淆矩阵数据收集
    # ============================================================

    _CONFUSION_MATRIX_DATA = []  # 类级别数据存储：[(expected_intent, actual_intent), ...]

    @classmethod
    def _collect_intent_for_confusion_matrix(cls, expected_intent: str, actual_intent: str):
        """
        收集意图数据用于混淆矩阵计算
        """
        cls._CONFUSION_MATRIX_DATA.append((expected_intent, actual_intent))

    @classmethod
    def get_confusion_matrix_data(cls) -> list:
        """
        获取混淆矩阵原始数据
        :return: [(expected_intent, actual_intent), ...]
        """
        return cls._CONFUSION_MATRIX_DATA.copy()

    @classmethod
    def clear_confusion_matrix_data(cls):
        """
        清空混淆矩阵数据
        """
        cls._CONFUSION_MATRIX_DATA.clear()

    @classmethod
    def generate_confusion_matrix(cls, save_path: str = None) -> dict:
        """
        生成意图识别混淆矩阵
        :param save_path: 混淆矩阵图片保存路径
        :return: 包含 matrix, labels, metrics 的字典
        """
        if not cls._CONFUSION_MATRIX_DATA:
            return {'matrix': [], 'labels': [], 'metrics': {}}

        y_true = [item[0] for item in cls._CONFUSION_MATRIX_DATA]
        y_pred = [item[1] for item in cls._CONFUSION_MATRIX_DATA]

        from assert_code.intent_confusion_matrix import draw_confusion_matrix
        result = draw_confusion_matrix(
            y_true=y_true,
            y_pred=y_pred,
            title="意图识别混淆矩阵",
            save_path=save_path,
            normalize='true',
            show=False,
        )
        return result

    # ============================================================
    # 多轮断言预留扩展
    # ============================================================

    @classmethod
    def _evaluate_multi_turn_round_checklist(cls, round_info: dict, output_data, context_rounds: list, response_time: float, similarity_threshold: float) -> dict:
        """
        多轮：细粒度清单断言模式（预留扩展）
        TODO: 实现多轮细粒度清单评估逻辑
        """
        log.warning("多轮细粒度清单断言模式暂未实现，使用默认相似度模式")
        # 回退到默认的相似度评估逻辑
        return cls.evaluate_multi_turn_round(round_info, output_data, context_rounds, response_time, similarity_threshold, assert_mode=AssertMode.INTENT_SIMILARITY)

    @classmethod
    def _evaluate_multi_turn_round_with_post(cls, round_info: dict, output_data, context_rounds: list, response_time: float, similarity_threshold: float) -> dict:
        """
        多轮：意图分类 + 后置操作组合断言（预留扩展）
        TODO: 实现多轮组合断言评估逻辑
        """
        log.warning("多轮组合断言模式暂未实现，使用默认相似度模式")
        # 回退到默认的相似度评估逻辑
        return cls.evaluate_multi_turn_round(round_info, output_data, context_rounds, response_time, similarity_threshold, assert_mode=AssertMode.INTENT_SIMILARITY)
