# -*- coding: utf-8 -*-
"""
# @File    : model_intent_assert.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
"""

import json
import os
from jsonpath import jsonpath

from common.modelHttpAction import ModelHttpAction
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data


class ModelIntentAssert:
    REPLY_RULES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'model_intent_reply_rules.yaml')

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
        return cls._clean_text(intent) == '转人工类'

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
    def evaluate_single_turn(cls, case_info: dict, output_data, response_time: float) -> dict:
        """
        单轮问答评估
        :param case_info: 用例信息
        :param output_data: 信贷大模型返回
        :param response_time: 响应耗时
        :return:
        """
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
            standard_similarity_res = {'is_same_meaning': chat_type_eval['chat_type_pass'], 'similarity_score': 100 if chat_type_eval['chat_type_pass'] else 0, 'reason': 'chatType=TRANSFER，模型已转人工处理'}
            reference_similarity_res = standard_similarity_res
            standard_similarity_score = float(standard_similarity_res['similarity_score'])
            reference_similarity_score = float(reference_similarity_res['similarity_score'])
            similarity_score = standard_similarity_score
            text_pass = chat_type_eval['chat_type_pass']
        else:
            evaluator = ModelHttpAction()
            answer_for_eval = reply_info.get('text_answer') or actual_answer
            similarity_res = evaluator.get_dual_sentence_similarity(
                actual_answer=answer_for_eval,
                expected_answer=expected_answer,
                reference_answer=reference_answer
            )
            standard_similarity_res = similarity_res['standard']
            reference_similarity_res = similarity_res['reference']
            standard_similarity_score = float(standard_similarity_res.get('similarity_score') or 0)
            reference_similarity_score = float(reference_similarity_res.get('similarity_score') or 0)
            similarity_score = round(max(standard_similarity_score, reference_similarity_score), 2)
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
            'is_same_meaning': standard_similarity_res.get('is_same_meaning') and reference_similarity_res.get('is_same_meaning'),
            'standard_similarity_score': standard_similarity_score,
            'standard_similarity_reason': standard_similarity_res.get('reason'),
            'reference_answer': reference_answer,
            'reference_similarity_score': reference_similarity_score,
            'reference_similarity_reason': reference_similarity_res.get('reason'),
            'similarity_score': similarity_score,
            'similarity_reason': f"标准答案评分={standard_similarity_score}；参考答案评分={reference_similarity_score}",
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
                'standard_similarity_score': standard_similarity_score,
                'reference_similarity_score': reference_similarity_score,
                'avg_similarity_score': similarity_score,
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
    def get_multi_turn_assert_switches(cls) -> dict:
        return {
            'enable_intent_assert': os.getenv('MODEL_ENABLE_INTENT_ASSERT', '1') == '1',
            'enable_context_assert': os.getenv('MODEL_ENABLE_CONTEXT_ASSERT', '1') == '1',
            'enable_risk_assert': os.getenv('MODEL_ENABLE_RISK_ASSERT', '1') == '1',
            'enable_asset_assert': os.getenv('MODEL_ENABLE_ASSET_ASSERT', '1') == '1',
            'require_all_assert_rounds_pass': os.getenv('MODEL_REQUIRE_ALL_ASSERT_ROUNDS_PASS', '1') == '1',
            'require_last_round_pass': os.getenv('MODEL_REQUIRE_LAST_ROUND_PASS', '1') == '1',
        }

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
    def evaluate_multi_turn_round(cls, round_info: dict, output_data, context_rounds: list, response_time: float, similarity_threshold: float) -> dict:
        reply_info = cls._extract_reply_contents(output_data=output_data)
        actual_answer = cls.extract_model_answer(output_data=output_data)
        expected_answer = round_info['expected_answer']
        reference_answer = cls._clean_text(round_info.get('reference_answer')) or expected_answer
        round_intent = round_info.get('round_intent', '')
        chat_type_eval = cls._evaluate_chat_type_result(round_intent, reply_info)
        if chat_type_eval['is_transfer']:
            standard_similarity_res = {'is_same_meaning': chat_type_eval['chat_type_pass'], 'similarity_score': 100 if chat_type_eval['chat_type_pass'] else 0, 'reason': 'chatType=TRANSFER，模型已转人工处理'}
            reference_similarity_res = standard_similarity_res
            standard_similarity_score = float(standard_similarity_res['similarity_score'])
            reference_similarity_score = float(reference_similarity_res['similarity_score'])
            similarity_score = standard_similarity_score
            similarity_pass = chat_type_eval['chat_type_pass']
            intent_eval = {'actual_intent': '转人工类' if chat_type_eval['chat_type_pass'] else '', 'intent_pass': chat_type_eval['chat_type_pass'], 'reason': 'chatType=TRANSFER，仅允许转人工类意图'}
            context_eval = {'context_carry_pass': True, 'intent_pollution_pass': True, 'user_correction_pass': True, 'risk_refusal_pass': True, 'return_to_business_pass': True, 'reason': 'chatType=TRANSFER，跳过上下文模型评估'}
        else:
            evaluator = ModelHttpAction()
            model_eval = evaluator.get_multi_turn_round_evaluation(
                context_rounds=context_rounds,
                current_question=round_info['question'],
                actual_answer=actual_answer,
                expected_answer=expected_answer,
                reference_answer=reference_answer,
                expected_intent=round_intent,
                previous_intent=round_info.get('previous_intent', ''),
                context_assert_type=round_info.get('context_assert_type', 'normal'),
                expect_refuse=bool(round_info.get('expect_refuse'))
            )
            standard_similarity_res = model_eval['standard']
            reference_similarity_res = model_eval['reference']
            standard_similarity_score = float(standard_similarity_res.get('similarity_score') or 0)
            reference_similarity_score = float(reference_similarity_res.get('similarity_score') or 0)
            similarity_score = round(max(standard_similarity_score, reference_similarity_score), 2)
            similarity_pass = similarity_score >= similarity_threshold
            intent_eval = model_eval['intent']
            context_eval = model_eval['context']
        asset_eval = cls.evaluate_asset_result(round_intent, reply_info)
        switches = cls.get_multi_turn_assert_switches()
        context_keys = ['context_carry_pass', 'intent_pollution_pass', 'user_correction_pass', 'return_to_business_pass']
        context_pass = all(context_eval.get(key) for key in context_keys)
        risk_pass = (not round_info.get('expect_refuse')) or bool(context_eval.get('risk_refusal_pass'))
        fail_reasons = []
        assert_items = [
            {
                'dimension': '话术相似度',
                'enabled': True,
                'pass': similarity_pass,
                'evidence': f"平均分={similarity_score}，阈值={similarity_threshold}；标准答案分={standard_similarity_score}；参考答案分={reference_similarity_score}",
                'reason': standard_similarity_res.get('reason') or reference_similarity_res.get('reason') or '',
                'suggestion': '优先检查标准答案/参考答案是否覆盖当前轮关键条件；若模型回复业务正确但表达差异大，可补充reference_answer。'
            },
            {
                'dimension': '意图识别',
                'enabled': switches['enable_intent_assert'],
                'pass': bool(intent_eval.get('intent_pass')),
                'evidence': f"期望意图={round_intent}，实际意图={intent_eval.get('actual_intent')}",
                'reason': intent_eval.get('reason') or '',
                'suggestion': '检查round_intent是否配置准确；如果实际意图应被接受，需要补充意图规则或调整用例期望。'
            },
            {
                'dimension': '上下文承接',
                'enabled': switches['enable_context_assert'],
                'pass': context_pass,
                'evidence': f"上下文类型={round_info.get('context_assert_type', 'normal')}，上一轮意图={round_info.get('previous_intent', '')}，承接={context_eval.get('context_carry_pass')}，污染={context_eval.get('intent_pollution_pass')}，改口={context_eval.get('user_correction_pass')}，回归业务={context_eval.get('return_to_business_pass')}",
                'reason': context_eval.get('reason') or '',
                'suggestion': '重点检查当前轮问题是否依赖上一轮、省略主语或跨意图切换；必要时把上一轮关键槽位写进标准答案。'
            },
            {
                'dimension': '风险拒答',
                'enabled': switches['enable_risk_assert'] and bool(round_info.get('expect_refuse')),
                'pass': risk_pass,
                'evidence': f"是否期望拒答={bool(round_info.get('expect_refuse'))}，拒答断言={context_eval.get('risk_refusal_pass')}",
                'reason': context_eval.get('reason') or '',
                'suggestion': '风险合规轮应明确配置expect_refuse=Y、round_intent=风险合规禁答类，并在标准答案中要求拒绝违规/隐私/内部规则内容。'
            },
            {
                'dimension': 'ASSET卡片',
                'enabled': switches['enable_asset_assert'],
                'pass': bool(asset_eval['asset_pass']),
                'evidence': f"ASSET存在={asset_eval.get('asset_present')}，允许={asset_eval.get('asset_allowed')}，value={asset_eval.get('asset_value')}，biz_ref_id={asset_eval.get('biz_ref_id')}",
                'reason': '；'.join(asset_eval.get('asset_failure_reasons') or []),
                'suggestion': '检查config/model_intent_reply_rules.yaml中该意图是否允许ASSET，以及value_allowlist/biz_ref_id_allowlist是否包含实际返回值。'
            }
        ]
        assert_items.insert(0, {
            'dimension': '会话类型',
            'enabled': True,
            'pass': chat_type_eval['chat_type_pass'],
            'evidence': f"chatType={chat_type_eval['chat_type']}，handoffReason={chat_type_eval['handoff_reason']}，期望意图={round_intent}",
            'reason': '；'.join(chat_type_eval['chat_type_failure_reasons']) or '会话类型符合预期',
            'suggestion': 'chatType=TRANSFER仅允许转人工类意图；其他意图应保持NORMAL并返回replyContents。'
        })
        failed_assert_items = [item for item in assert_items if item['enabled'] and not item['pass']]
        if not chat_type_eval['chat_type_pass']:
            fail_reasons.extend(chat_type_eval['chat_type_failure_reasons'])
        if not similarity_pass:
            fail_reasons.append(f"话术平均评分 {similarity_score} 低于阈值 {similarity_threshold}")
        if switches['enable_intent_assert'] and not intent_eval.get('intent_pass'):
            fail_reasons.append(f"当前轮意图不正确：{intent_eval.get('reason')}")
        if switches['enable_context_assert'] and not context_pass:
            fail_reasons.append(f"上下文断言失败：{context_eval.get('reason')}")
        if switches['enable_risk_assert'] and round_info.get('expect_refuse') and not context_eval.get('risk_refusal_pass'):
            fail_reasons.append(f"风险问题未正确拒答：{context_eval.get('reason')}")
        if switches['enable_asset_assert'] and not asset_eval['asset_pass']:
            fail_reasons.extend(asset_eval['asset_failure_reasons'])
        round_pass = not fail_reasons
        return {
            'round': round_info['round'],
            'question': round_info['question'],
            'expected_answer': expected_answer,
            'reference_answer': reference_answer,
            'actual_answer': actual_answer,
            'round_intent': round_intent,
            'actual_intent': intent_eval.get('actual_intent'),
            'chat_type': chat_type_eval['chat_type'],
            'handoff_reason': chat_type_eval['handoff_reason'],
            'chat_type_pass': chat_type_eval['chat_type_pass'],
            'previous_intent': round_info.get('previous_intent', ''),
            'context_assert_type': round_info.get('context_assert_type', 'normal'),
            'expect_refuse': bool(round_info.get('expect_refuse')),
            'standard_similarity_score': standard_similarity_score,
            'standard_similarity_reason': standard_similarity_res.get('reason'),
            'reference_similarity_score': reference_similarity_score,
            'reference_similarity_reason': reference_similarity_res.get('reason'),
            'similarity_score': similarity_score,
            'similarity_pass': similarity_pass,
            'similarity_reason': f"标准答案评分={standard_similarity_score}；参考答案评分={reference_similarity_score}",
            'intent_pass': intent_eval.get('intent_pass'),
            'intent_reason': intent_eval.get('reason'),
            'context_carry_pass': context_eval.get('context_carry_pass'),
            'intent_pollution_pass': context_eval.get('intent_pollution_pass'),
            'user_correction_pass': context_eval.get('user_correction_pass'),
            'risk_refusal_pass': context_eval.get('risk_refusal_pass'),
            'return_to_business_pass': context_eval.get('return_to_business_pass'),
            'context_reason': context_eval.get('reason'),
            **asset_eval,
            'assert_items': assert_items,
            'failed_assert_items': failed_assert_items,
            'failure_suggestions': [item['suggestion'] for item in failed_assert_items],
            'should_assert': round_info.get('should_assert', True),
            'response_time': round(response_time, 3),
            'round_pass': round_pass,
            'failure_reason': '；'.join(fail_reasons),
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
        :param reference_answer: 外部模型参考答案
        :return:
        """
        evaluator = ModelHttpAction()
        reference_answer = cls._clean_text(reference_answer) or expected_answer
        similarity_res = evaluator.get_dual_sentence_similarity(
            actual_answer=actual_answer,
            expected_answer=expected_answer,
            reference_answer=reference_answer
        )
        standard_similarity_res = similarity_res['standard']
        reference_similarity_res = similarity_res['reference']
        standard_similarity_score = float(standard_similarity_res.get('similarity_score') or 0)
        reference_similarity_score = float(reference_similarity_res.get('similarity_score') or 0)
        similarity_score = round(max(standard_similarity_score, reference_similarity_score), 2)
        return {
            'expected_answer': expected_answer,
            'reference_answer': reference_answer,
            'actual_answer': actual_answer,
            'is_same_meaning': standard_similarity_res.get('is_same_meaning') and reference_similarity_res.get('is_same_meaning'),
            'standard_similarity_score': standard_similarity_score,
            'standard_similarity_reason': standard_similarity_res.get('reason'),
            'reference_similarity_score': reference_similarity_score,
            'reference_similarity_reason': reference_similarity_res.get('reason'),
            'similarity_score': similarity_score,
            'similarity_reason': f"标准答案评分={standard_similarity_score}；参考答案评分={reference_similarity_score}",
            'similarity_pass': similarity_score >= similarity_threshold
        }

    @classmethod
    def assert_model_result(cls, report_row: dict) -> None:
        """
        模型评估结果断言
        :param report_row: 评估明细
        :return:
        """
        assert report_row['is_pass'] is True, f"模型断言失败：{report_row.get('failure_reason') or report_row.get('similarity_reason') or report_row.get('similarity_score')}"
