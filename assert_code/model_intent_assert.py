# -*- coding: utf-8 -*-
"""
# @File    : model_intent_assert.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
"""

import json
from jsonpath import jsonpath

from common.modelHttpAction import ModelHttpAction
from utils.handle_log import log


class ModelIntentAssert:
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
    def evaluate_single_turn(cls, case_info: dict, output_data, response_time: float) -> dict:
        """
        单轮问答评估
        :param case_info: 用例信息
        :param output_data: 信贷大模型返回
        :param response_time: 响应耗时
        :return:
        """
        actual_answer = cls.extract_model_answer(output_data=output_data)
        actual_intent = cls.extract_model_intent(output_data=output_data)
        expected_answer = case_info['expected_answer']

        evaluator = ModelHttpAction()
        similarity_res = evaluator.get_sentence_similarity(sentence_a=actual_answer, sentence_b=expected_answer)
        similarity_score = float(similarity_res.get('similarity_score') or 0)
        similarity_pass = similarity_score >= case_info['similarity_threshold']
        is_pass = similarity_pass

        report_row = {
            'case_id': case_info['case_id'],
            'case_type': case_info['case_type'],
            'case_desc': case_info['case_desc'],
            'intent': case_info['intent'],
            'actual_intent': actual_intent,
            'question': case_info['question'],
            'expected_answer': expected_answer,
            'actual_answer': actual_answer,
            'is_same_meaning': similarity_res.get('is_same_meaning'),
            'similarity_score': similarity_score,
            'similarity_reason': similarity_res.get('reason'),
            'similarity_threshold': case_info['similarity_threshold'],
            'similarity_pass': similarity_pass,
            'response_time': round(response_time, 3),
            'is_pass': is_pass,
            'output_data': json.dumps(output_data, ensure_ascii=False)
        }
        log.info(f"模型评估结果：{report_row}")
        return report_row

    @classmethod
    def evaluate_answer(cls, actual_answer: str, expected_answer: str, similarity_threshold: float) -> dict:
        """
        单句答案相似度评估
        :param actual_answer: 实际回复
        :param expected_answer: 标准回复
        :param similarity_threshold: 相似度阈值
        :return:
        """
        evaluator = ModelHttpAction()
        similarity_res = evaluator.get_sentence_similarity(sentence_a=actual_answer, sentence_b=expected_answer)
        similarity_score = float(similarity_res.get('similarity_score') or 0)
        return {
            'expected_answer': expected_answer,
            'actual_answer': actual_answer,
            'is_same_meaning': similarity_res.get('is_same_meaning'),
            'similarity_score': similarity_score,
            'similarity_reason': similarity_res.get('reason'),
            'similarity_pass': similarity_score >= similarity_threshold
        }

    @classmethod
    def assert_model_result(cls, report_row: dict) -> None:
        """
        模型评估结果断言
        :param report_row: 评估明细
        :return:
        """
        assert report_row['similarity_pass'] is True, f"话术相似度低于阈值，评分：{report_row['similarity_score']}，原因：{report_row['similarity_reason']}"
