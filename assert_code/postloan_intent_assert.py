# -*- coding: utf-8 -*-
"""
# @File    : postloan_intent_assert.py
# @Date    : 2026-06-17
# @Author  : jeremyzhai
# @Description : 贷后催收场景意图识别断言工具
#
# 核心设计：
#   - 继承 ModelIntentAssert，复用基础断言能力
#   - 使用独立的贷后知识库和回复规则配置
#   - 支持贷后 6 大意图、16 个核心拆分的映射校验
#   - 增加话术合规性检查（禁用词、禁忌语）
#
# 与信贷场景的差异：
#   - 知识库：config/postloan_knowledge_base.yaml（独立）
#   - 回复规则：config/postloan_intent_reply_rules.yaml（独立）
#   - 意图体系：6大意图、16个核心拆分（与信贷不同）
#   - 合规重点：催收合规、禁用词过滤、情绪安抚
"""

import json
import os

from assert_code.model_intent_assert import ModelIntentAssert, AssertMode
from assert_code.knowledge_base import KnowledgeBase
from utils.handle_log import log


class PostloanIntentAssert(ModelIntentAssert):
    """
    贷后催收场景意图识别断言工具

    继承 ModelIntentAssert，但使用完全独立的：
    - 知识库（config/postloan_knowledge_base.yaml）
    - 回复规则（config/postloan_intent_reply_rules.yaml）
    """

    # ============================================================
    # 独立配置路径
    # ============================================================
    POSTLOAN_KNOWLEDGE_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'postloan_knowledge_base.yaml'
    )
    POSTLOAN_REPLY_RULES_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'postloan_intent_reply_rules.yaml'
    )

    # ============================================================
    # 贷后专用检查清单配置路径
    # ============================================================
    POSTLOAN_CHECKLIST_CONFIG_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'postloan_intent_checklist.yaml'
    )

    # ============================================================
    # 意图映射表（核心拆分 → 主意图）
    # 用于将用例中的核心拆分映射到主意图，进行标准化断言
    # ============================================================
    INTENT_MAP = {
        # 风险合规禁答
        '违规操作': '风险合规禁答',
        '信息探知': '风险合规禁答',
        # 转人工
        '标准诉求': '转人工',
        '投诉类': '转人工',
        # 贷后协商
        '还款减免': '贷后协商',
        '还款减压': '贷后协商',
        '协商还': '贷后协商',
        '泛协商': '贷后协商',
        # 贷后咨询
        '还款咨询': '贷后咨询',
        '征信咨询': '贷后咨询',
        # 非贷后咨询
        '退款咨询': '非贷后咨询',
        '借款额度咨询': '非贷后咨询',
        '账户咨询': '非贷后咨询',
        '其他咨询': '非贷后咨询',
        # 未知意图
        '模糊意图': '未知意图',
        '闲聊': '未知意图',
    }

    # ============================================================
    # 贷后话术禁用词列表
    # ============================================================
    FORBIDDEN_WORDS = [
        '威胁', '恐吓', '辱骂', '骂', '混蛋', '垃圾', '滚',
        '泄露', '曝光', '通讯录', '联系人', '家人', '亲戚',
        '承诺减免', '一定减免', '保证减免', '承诺停催', '一定停催',
        '保证停催', '承诺延期', '一定延期', '保证延期',
        '起诉', '法院', '公安', '警察', '逮捕', '坐牢', '拘留',
        '上门', '堵门', '堵人', '抓人',
    ]

    # ============================================================
    # 知识库和配置加载
    # ============================================================

    _postloan_kb = None
    _postloan_rules = None

    @classmethod
    def _get_postloan_knowledge(cls):
        """获取贷后专用知识库（独立实例）"""
        if cls._postloan_kb is None:
            cls._postloan_kb = KnowledgeBase(knowledge_file=cls.POSTLOAN_KNOWLEDGE_FILE)
            log.info(f"贷后知识库已加载：{cls.POSTLOAN_KNOWLEDGE_FILE}")
        return cls._postloan_kb

    @classmethod
    def _get_postloan_rules(cls):
        """获取贷后专用回复规则"""
        if cls._postloan_rules is None:
            from utils.handle_yaml import read_yaml_data
            cls._postloan_rules = read_yaml_data(cls.POSTLOAN_REPLY_RULES_FILE) or {}
            log.info(f"贷后回复规则已加载：{cls.POSTLOAN_REPLY_RULES_FILE}")
        return cls._postloan_rules

    @classmethod
    def load_reply_rules(cls) -> dict:
        """加载贷后专用回复规则（覆盖父类方法）"""
        return cls._get_postloan_rules()

    @classmethod
    def get_intent_rule(cls, intent: str) -> dict:
        """
        获取贷后意图规则（支持核心拆分映射到主意图）

        Args:
            intent: 意图名称（可以是核心拆分，如"还款减免"）

        Returns:
            意图规则字典
        """
        # 将核心拆分映射到主意图
        mapped_intent = cls.INTENT_MAP.get(intent, intent)

        rules = cls._get_postloan_rules()
        defaults = rules.get('defaults', {}) if isinstance(rules.get('defaults', {}), dict) else {}
        intents = rules.get('intents', {}) if isinstance(rules.get('intents', {}), dict) else {}
        intent_rule = intents.get(mapped_intent, {}) if isinstance(intents.get(mapped_intent, {}), dict) else {}

        text_default = defaults.get('text', {}) if isinstance(defaults.get('text', {}), dict) else {}
        asset_default = defaults.get('asset', {}) if isinstance(defaults.get('asset', {}), dict) else {}
        text_rule = intent_rule.get('text', {}) if isinstance(intent_rule.get('text', {}), dict) else {}
        asset_rule = intent_rule.get('asset', {}) if isinstance(intent_rule.get('asset', {}), dict) else {}

        return {
            'text': {
                'threshold': text_rule.get('threshold', text_default.get('threshold', 70)),
                'comparator': text_rule.get('comparator', text_default.get('comparator', 'gte')),
            },
            'asset': {
                'allowed': asset_rule.get('allowed', asset_default.get('allowed', False)),
                'value_allowlist': asset_rule.get('value_allowlist', asset_default.get('value_allowlist', [])) or [],
                'biz_ref_id_allowlist': asset_rule.get('biz_ref_id_allowlist', asset_default.get('biz_ref_id_allowlist', [])) or [],
                'biz_ref_id_allowlist_by_value': asset_rule.get('biz_ref_id_allowlist_by_value', {}),
            }
        }

    # ============================================================
    # 贷后单轮评估主入口
    # ============================================================

    @classmethod
    def evaluate_postloan_single_turn(cls, case_info: dict, output_data, response_time: float,
                                       assert_mode: AssertMode = None) -> dict:
        """
        贷后单轮评估主入口 —— 支持三种模式切换

        评估维度：
        1. 意图识别正确性（核心拆分 → 主意图映射校验）
        2. chatType 合规性（TRANSFER 仅在"转人工"时允许）
        3. 话术合规性（禁用词、禁忌语检查，使用贷后知识库）
        4. 语义相似度（使用贷后专用 threshold）
        5. ASSET 卡片合规性（使用贷后专用 biz_ref_id 白名单）

        Args:
            case_info: 用例信息
            output_data: 模型返回数据
            response_time: 响应耗时
            assert_mode: 断言模式（None 时从环境变量读取）

        Returns:
            评估报告字典
        """
        if assert_mode is None:
            assert_mode = cls.get_assert_mode()

        if assert_mode == AssertMode.INTENT_SIMILARITY:
            return cls._evaluate_postloan_similarity(case_info, output_data, response_time)
        elif assert_mode == AssertMode.INTENT_CHECKLIST:
            return cls._evaluate_postloan_checklist(case_info, output_data, response_time)
        elif assert_mode == AssertMode.INTENT_WITH_POST:
            return cls._evaluate_postloan_with_post(case_info, output_data, response_time)
        else:
            log.warning(f"不支持的断言模式: {assert_mode}，使用默认模式 INTENT_SIMILARITY")
            return cls._evaluate_postloan_similarity(case_info, output_data, response_time)

    @classmethod
    def _evaluate_postloan_similarity(cls, case_info: dict, output_data, response_time: float) -> dict:
        """贷后场景：一致性评分"""
        report = super().evaluate_single_turn(
            case_info, output_data, response_time,
            assert_mode=AssertMode.INTENT_SIMILARITY
        )
        return cls._apply_postloan_checks(report, case_info, output_data)

    @classmethod
    def _evaluate_postloan_checklist(cls, case_info: dict, output_data, response_time: float) -> dict:
        """贷后场景：细粒度清单"""
        report = super().evaluate_single_turn(
            case_info, output_data, response_time,
            assert_mode=AssertMode.INTENT_CHECKLIST
        )
        return cls._apply_postloan_checks(report, case_info, output_data)

    @classmethod
    def _evaluate_single_turn_checklist(cls, case_info: dict, output_data, response_time: float) -> dict:
        """
        贷后场景：重写父类的细粒度清单评估，使用贷后专用配置
        """
        return super()._evaluate_single_turn_checklist(
            case_info, output_data, response_time,
            config_path=cls.POSTLOAN_CHECKLIST_CONFIG_FILE
        )

    # ============================================================
    # 贷后意图识别校验
    # ============================================================

    @classmethod
    def _check_postloan_intent(cls, expected_intent: str, output_data) -> dict:
        """
        校验贷后意图识别正确性

        将核心拆分映射到主意图后，与模型返回的意图进行对比。

        Args:
            expected_intent: 期望意图（可以是核心拆分，如"还款减免"）
            output_data: 模型返回数据

        Returns:
            {
                'is_match': bool,
                'expected_intent': str,
                'actual_intent': str,
                'expected_mapped': str,
                'actual_mapped': str,
                'failure_reason': str
            }
        """
        actual_intent = cls.extract_model_intent(output_data)

        # 标准化意图名称（核心拆分 → 主意图）
        expected_mapped = cls.INTENT_MAP.get(expected_intent, expected_intent)
        actual_mapped = cls.INTENT_MAP.get(actual_intent, actual_intent)

        is_match = expected_mapped == actual_mapped or actual_intent == ''

        return {
            'is_match': is_match,
            'expected_intent': expected_intent,
            'actual_intent': actual_intent,
            'expected_mapped': expected_mapped,
            'actual_mapped': actual_mapped,
            'failure_reason': (
                f'意图识别错误：期望[{expected_intent}](映射到主意图[{expected_mapped}])，'
                f'实际[{actual_intent}](映射到主意图[{actual_mapped}])'
                if not is_match else ''
            )
        }

    # ============================================================
    # 贷后话术合规性校验
    # ============================================================

    @classmethod
    def _check_postloan_compliance(cls, intent: str, actual_answer: str) -> dict:
        """
        校验贷后话术合规性

        检查点：
        1. 禁用词检查（威胁、恐吓、辱骂等）
        2. 知识库合规性校验

        Args:
            intent: 期望意图
            actual_answer: 模型实际回复

        Returns:
            {
                'is_pass': bool,
                'found_forbidden': list,
                'failure_reasons': list,
                'intent_rules': str
            }
        """
        # 禁用词检查
        found_forbidden = []
        for word in cls.FORBIDDEN_WORDS:
            if word in actual_answer:
                found_forbidden.append(word)

        # 知识库合规性检查
        kb = cls._get_postloan_knowledge()
        intent_rules = kb.get_intent_rules(intent) if intent else ''

        is_pass = len(found_forbidden) == 0

        return {
            'is_pass': is_pass,
            'found_forbidden': found_forbidden,
            'failure_reasons': [f'发现禁用词：{word}' for word in found_forbidden] if found_forbidden else [],
            'intent_rules': intent_rules
        }

    # ============================================================
    # 贷后批量评估（支持批量断言模式）
    # ============================================================

    @classmethod
    def evaluate_postloan_single_turn_batch(cls, case_info: dict, output_data,
                                            response_time: float) -> dict:
        """
        贷后单轮评估（批量模式简化版）

        批量模式下，只做本地断言（意图识别 + chatType + ASSET），
        语义评估统一推迟到批量断言阶段执行。

        Args:
            case_info: 用例信息
            output_data: 模型返回数据
            response_time: 响应耗时

        Returns:
            评估报告字典
        """
        # 提取基本信息
        reply_info = cls._extract_reply_contents(output_data=output_data)
        actual_answer = cls.extract_model_answer(output_data=output_data)
        actual_intent = cls.extract_model_intent(output_data=output_data)

        # 意图识别校验
        intent_check = cls._check_postloan_intent(case_info.get('intent', ''), output_data)

        # chatType 校验
        chat_type_eval = cls._evaluate_chat_type_result(case_info.get('intent', ''), reply_info)

        # ASSET 校验
        asset_eval = cls.evaluate_asset_result(case_info.get('intent', ''), reply_info)

        # 话术合规性校验
        compliance_check = cls._check_postloan_compliance(case_info.get('intent', ''), actual_answer)

        # 综合判定
        is_pass = (
            intent_check['is_match'] and
            chat_type_eval['chat_type_pass'] and
            asset_eval['asset_pass'] and
            compliance_check['is_pass']
        )

        # 收集失败原因
        fail_reasons = []
        if not intent_check['is_match']:
            fail_reasons.append(intent_check['failure_reason'])
        if not chat_type_eval['chat_type_pass']:
            fail_reasons.extend(chat_type_eval['chat_type_failure_reasons'])
        if not asset_eval['asset_pass']:
            fail_reasons.extend(asset_eval['asset_failure_reasons'])
        if not compliance_check['is_pass']:
            fail_reasons.extend(compliance_check['failure_reasons'])

        return {
            'case_id': case_info.get('case_id', ''),
            'intent': case_info.get('intent', ''),
            'actual_intent': actual_intent,
            'actual_answer': actual_answer,
            'chat_type': chat_type_eval['chat_type'],
            'chat_type_pass': chat_type_eval['chat_type_pass'],
            'postloan_intent_match': intent_check,
            'postloan_compliance_check': compliance_check,
            'asset_present': asset_eval['asset_present'],
            'asset_allowed': asset_eval['asset_allowed'],
            'asset_value': asset_eval['asset_value'],
            'asset_value_pass': asset_eval['asset_value_pass'],
            'biz_ref_id': asset_eval['biz_ref_id'],
            'biz_ref_id_pass': asset_eval['biz_ref_id_pass'],
            'is_pass': is_pass,
            'fail_reasons': fail_reasons,
            'failure_reason': '；'.join(fail_reasons) if fail_reasons else '',
            'response_time': round(response_time, 3),
        }
