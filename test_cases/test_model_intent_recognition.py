# -*- coding: utf-8 -*-
"""
# @File    : test_model_intent_recognition.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
"""

import csv
import io
import json
import os
import random
import sys
import time

Base_Path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(Base_Path)

import allure
import pytest

from assert_code.model_intent_assert import ModelIntentAssert
from script_code.model_intent_recognition_exec import ModelIntentRecognition
from utils.handle_log import log
from utils.handle_model_cases import assemble_model_case_params, get_model_case_desc, ModelCaseHandler


MODEL_REPORT_ROWS = []

# uid 池加载与分配
_UID_POOL = None
_USED_UIDS = set()


def _load_uid_pool() -> list:
    """从 case_data/credited_uids_pool.csv 加载 uid 池"""
    global _UID_POOL
    if _UID_POOL is not None:
        return _UID_POOL
    uid_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'case_data', 'credited_uids_pool.csv')
    if not os.path.exists(uid_file):
        _UID_POOL = []
        return _UID_POOL
    with open(uid_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        _UID_POOL = [row['uid'].strip() for row in reader if row.get('uid', '').strip()]
    return _UID_POOL


def get_random_uid() -> str:
    """从 uid 池中随机获取一个未使用的 uid"""
    global _USED_UIDS
    pool = _load_uid_pool()
    available = [uid for uid in pool if uid not in _USED_UIDS]
    if not available:
        return '4130948'
    uid = random.choice(available)
    _USED_UIDS.add(uid)
    return uid


def build_summary_log(report_rows: list) -> str:
    """
    构造模型测试汇总日志
    :param report_rows: 明细结果
    :return:
    """
    total = len(report_rows)
    pass_count = len([row for row in report_rows if row.get('is_pass') is True])
    failed_count = len([row for row in report_rows if row.get('is_pass') is False])
    similarity_list = [float(row.get('similarity_score', 0)) for row in report_rows]
    response_time_list = sorted([float(row.get('response_time', 0)) for row in report_rows])
    avg_similarity = round(sum(similarity_list) / total, 2) if total else 0
    avg_response_time = round(sum(response_time_list) / total, 2) if total else 0
    p90_response_time = response_time_list[int(total * 0.9) - 1] if total else 0
    p95_response_time = response_time_list[int(total * 0.95) - 1] if total else 0
    max_response_time = max(response_time_list) if total else 0
    min_response_time = min(response_time_list) if total else 0
    failed_cases = [
        f"{row.get('case_id')} | {row.get('case_desc')} | 结果={row.get('failure_reason') or row.get('similarity_reason') or row.get('similarity_score')}"
        for row in report_rows if row.get('is_pass') is False
    ]

    log_lines = [
        "==============【信贷大模型测试汇总】==============",
        f"【总用例数】：{total}",
        f"【通过数】：{pass_count}",
        f"【失败数】：{failed_count}",
        f"【通过率】：{round(pass_count / total * 100, 2) if total else 0}%",
        f"【平均相似度】：{avg_similarity}",
        f"【平均响应耗时】：{avg_response_time}s",
        f"【P90响应耗时】：{p90_response_time}s",
        f"【P95响应耗时】：{p95_response_time}s",
        f"【最大响应耗时】：{max_response_time}s",
        f"【最小响应耗时】：{min_response_time}s",
        f"【失败用例】：{failed_cases if failed_cases else '无'}"
    ]
    return '\n'.join(log_lines)


def attach_model_report(report_rows: list) -> None:
    """
    将模型测试汇总和明细挂载到Allure报告
    :param report_rows: 明细结果
    :return:
    """
    if not report_rows:
        allure.attach('当前无模型测试结果', '模型测试汇总', allure.attachment_type.TEXT)
        return

    summary_log = build_summary_log(report_rows=report_rows)
    report_file = ModelCaseHandler.save_model_report(report_rows=report_rows)
    failed_report_csv_file = ModelCaseHandler.save_model_failed_report_csv(report_rows=report_rows)
    summary_file = ModelCaseHandler.save_model_summary(report_rows=report_rows)
    log.info(f"\n{summary_log}")
    log.info(f"模型测试明细Excel报告：{report_file}")
    log.info(f"失败测试用例明细CSV报告：{failed_report_csv_file}")
    log.info(f"模型测试汇总报告：{summary_file}")
    allure.attach(summary_log, '模型测试汇总', allure.attachment_type.TEXT)
    allure.attach.file(failed_report_csv_file, name='失败测试用例明细报表CSV', attachment_type=allure.attachment_type.CSV)
    allure.attach(f'Excel明细报表本地路径：{report_file}', '模型测试明细Excel路径', allure.attachment_type.TEXT)
    allure.attach.file(summary_file, name='模型测试汇总JSON', attachment_type=allure.attachment_type.JSON)


def build_multi_turn_actual_dialog(round_rows: list) -> str:
    dialog_lines = []
    for row in round_rows:
        dialog_lines.extend([
            f"------ 第{row['round']}轮 ------",
            f"用户问题：{row['question']}",
            f"模型回复：{row['actual_answer']}",
            f"响应耗时：{row['response_time']}s"
        ])
    return '\n'.join(dialog_lines)


def build_multi_turn_assert_dialog(round_rows: list) -> str:
    dialog_lines = []
    for row in round_rows:
        dialog_lines.extend([
            f"------ 第{row['round']}轮 ------",
            f"用户问题：{row['question']}",
            f"标准答案：{row['expected_answer']}",
            f"外部模型参考答案：{row.get('reference_answer') or ''}",
            f"期望意图：{row.get('round_intent')}",
            f"是否断言：{row.get('should_assert')}"
        ])
    return '\n'.join(dialog_lines)


def build_multi_turn_eval_body(round_rows: list, report_row: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'case_id', 'case_type', 'case_desc', 'intent', 'round', 'question', 'expected_answer',
        'reference_answer', 'actual_answer', 'round_intent', 'actual_intent', 'context_assert_type',
        'response_time', 'standard_similarity_score', 'reference_similarity_score', 'similarity_score',
        'similarity_pass', 'intent_pass', 'context_carry_pass', 'intent_pollution_pass',
        'risk_refusal_pass', 'return_to_business_pass', 'asset_pass', 'round_pass', 'failure_reason',
        'failed_dimensions', 'failure_suggestions', 'case_avg_score', 'similarity_threshold', 'case_result'
    ])
    writer.writeheader()
    for row in round_rows:
        writer.writerow({
            'case_id': report_row['case_id'],
            'case_type': report_row['case_type'],
            'case_desc': report_row['case_desc'],
            'intent': report_row['intent'],
            'round': row['round'],
            'question': row['question'],
            'expected_answer': row['expected_answer'],
            'reference_answer': row.get('reference_answer'),
            'actual_answer': row['actual_answer'],
            'round_intent': row.get('round_intent'),
            'actual_intent': row.get('actual_intent'),
            'context_assert_type': row.get('context_assert_type'),
            'response_time': row['response_time'],
            'standard_similarity_score': row.get('standard_similarity_score'),
            'reference_similarity_score': row.get('reference_similarity_score'),
            'similarity_score': row['similarity_score'],
            'similarity_pass': row['similarity_pass'],
            'intent_pass': row.get('intent_pass'),
            'context_carry_pass': row.get('context_carry_pass'),
            'intent_pollution_pass': row.get('intent_pollution_pass'),
            'risk_refusal_pass': row.get('risk_refusal_pass'),
            'return_to_business_pass': row.get('return_to_business_pass'),
            'asset_pass': row.get('asset_pass'),
            'round_pass': row.get('round_pass'),
            'failure_reason': row.get('failure_reason'),
            'failed_dimensions': '；'.join([item.get('dimension', '') for item in row.get('failed_assert_items') or []]),
            'failure_suggestions': '；'.join(row.get('failure_suggestions') or []),
            'case_avg_score': report_row['similarity_score'],
            'similarity_threshold': report_row['similarity_threshold'],
            'case_result': report_row['is_pass']
        })
    return output.getvalue()


def build_exec_log(case_info: dict, msg_info: dict, exec_res: dict, report_row: dict, response_time: float) -> str:
    """
    构造Allure展示用执行日志
    :param case_info: 用例信息
    :param msg_info: 模型请求信息
    :param exec_res: 模型执行结果
    :param report_row: 评估结果
    :param response_time: 响应耗时
    :return:
    """
    log_lines = [
        f"==============【当前环境：env={case_info['env']}, group={case_info['group']}】信贷大模型测试 =============",
        f"【用例编号】：{case_info['case_id']}",
        f"【测试场景】：{case_info['case_desc']}",
        f"【意图分类】：{case_info['intent']}",
        f"【实际意图】：{report_row.get('actual_intent')}",
        f"【chatType】：{report_row.get('chat_type')}",
        f"【handoffReason】：{report_row.get('handoff_reason')}",
        f"【chatType断言】：{report_row.get('chat_type_pass')}",
        f"【用户问题】：{case_info['question']}",
        f"【断言话术-标准答案】：{case_info['expected_answer']}",
        f"【断言话术-外部模型参考答案】：{report_row.get('reference_answer')}",
        f"【replyContents】：{report_row.get('reply_contents_raw')}",
        f"【TEXT输出】：{report_row.get('text_values')}",
        f"【ASSET输出】：{report_row.get('asset_values')}",
        f"【biz_ref_id】：{report_row.get('biz_ref_ids')}",
        f"【模型请求msg_info】：{json.dumps(msg_info, ensure_ascii=False)}",
        f"【模型请求request_data】：{json.dumps(exec_res.get('request_data'), ensure_ascii=False)}",
        f"【模型完整返回】：{json.dumps(exec_res.get('output_data'), ensure_ascii=False)}",
        f"【模型有效出参value】：{report_row['actual_answer']}",
        f"【外部模型相似度评分】：{report_row['similarity_score']}",
        f"【外部模型评估原因】：{report_row['similarity_reason']}",
        f"【TEXT阈值】：{report_row.get('text_comparator')} {report_row.get('text_threshold')}",
        f"【TEXT断言】：{report_row.get('text_pass')}",
        f"【ASSET是否允许】：{report_row.get('asset_allowed')}",
        f"【ASSET value断言】：{report_row.get('asset_value_pass')} ({report_row.get('asset_value')})",
        f"【biz_ref_id断言】：{report_row.get('biz_ref_id_pass')} ({report_row.get('biz_ref_id')})",
        f"【失败原因】：{report_row.get('failure_reason')}",
        f"【响应耗时】：{round(response_time, 3)}s",
        f"【相似度断言】：实际={report_row['similarity_score']}，阈值={report_row['similarity_threshold']}，结果={report_row['similarity_pass']}",
        f"【最终结果】：{report_row['is_pass']}"
    ]
    return '\n'.join(log_lines)


@allure.feature('信贷大模型')
@pytest.mark.model_intent_recognition
class TestModelIntentRecognition:
    @allure.story('单轮意图识别与话术应答')
    @pytest.mark.model_single_turn
    @pytest.mark.parametrize(*(assemble_model_case_params(case_type='single_turn')),
                             ids=get_model_case_desc(case_type='single_turn'))
    def test_single_turn_intent_recognition(self, case_info: dict) -> None:
        """
        【信贷大模型--单轮意图识别与话术应答】
        :param case_info: 用例信息
        :return: None
        """
        if not case_info:
            pytest.skip('当前未配置single_turn类型用例')
        allure.dynamic.parent_suite('单轮意图识别与话术应答')
        allure.dynamic.suite(case_info['intent'])
        allure.dynamic.label('intent', case_info['intent'])

        log.info(f"\n==============【当前环境：env={case_info['env']}, group={case_info['group']}】信贷大模型单轮测试 =============\n")
        model = ModelIntentRecognition(env=case_info['env'], group=case_info['group'])
        msg_info = {
            'uid': get_random_uid(),
            'content': case_info['question']
        }

        start_time = time.time()
        exec_res = model.send_msg_to_model(msg_info=msg_info)
        response_time = time.time() - start_time

        report_row = ModelIntentAssert.evaluate_single_turn(
            case_info=case_info,
            output_data=exec_res.get('output_data'),
            response_time=response_time
        )
        MODEL_REPORT_ROWS.append(report_row)
        ModelCaseHandler.save_model_rows([report_row])

        exec_log = build_exec_log(case_info=case_info, msg_info=msg_info, exec_res=exec_res, report_row=report_row, response_time=response_time)
        log.info(f"\n{exec_log}")
        allure.attach(json.dumps(case_info, ensure_ascii=False, indent=2), '用例信息', allure.attachment_type.JSON)
        allure.attach(exec_log, '执行日志', allure.attachment_type.TEXT)
        allure.attach(json.dumps(exec_res.get('request_data'), ensure_ascii=False, indent=2), '信贷大模型请求入参', allure.attachment_type.JSON)
        allure.attach(json.dumps(exec_res.get('output_data'), ensure_ascii=False, indent=2), '信贷大模型完整返回', allure.attachment_type.JSON)
        allure.attach(json.dumps(report_row, ensure_ascii=False, indent=2), '模型评估明细', allure.attachment_type.JSON)
        allure.attach(json.dumps(report_row.get('assert_detail'), ensure_ascii=False, indent=2), '断言明细', allure.attachment_type.JSON)
        allure.attach(report_row.get('failure_reason') or '无', '失败原因', allure.attachment_type.TEXT)
        assert_answer_text = '\n'.join([
            f"【标准答案】：{report_row['expected_answer']}",
            f"【外部模型参考答案】：{report_row.get('reference_answer') or ''}"
        ])
        allure.attach(report_row['actual_answer'], '信贷大模型实际话术', allure.attachment_type.TEXT)
        allure.attach(assert_answer_text, '断言话术', allure.attachment_type.TEXT)

        ModelIntentAssert.assert_model_result(report_row=report_row)

    @allure.story('多轮对话上下文连贯性')
    @pytest.mark.model_multi_turn
    @pytest.mark.parametrize(*(assemble_model_case_params(case_type='multi_turn')),
                             ids=get_model_case_desc(case_type='multi_turn'))
    def test_multi_turn_dialog_consistency(self, case_info: dict) -> None:
        """
        【信贷大模型--多轮对话上下文连贯性】
        :param case_info: 用例信息
        :return: None
        """
        if not case_info:
            pytest.skip('当前未配置multi_turn类型用例')
        remark_suite = case_info.get('remark') or case_info.get('case_type') or '未分类'
        allure.dynamic.parent_suite('多轮对话')
        allure.dynamic.suite(remark_suite)
        allure.dynamic.sub_suite(case_info['intent'])
        allure.dynamic.label('remark', remark_suite)
        allure.dynamic.label('intent', case_info['intent'])

        log.info(f"\n==============【当前环境：env={case_info['env']}, group={case_info['group']}】信贷大模型多轮测试 =============\n")
        model = ModelIntentRecognition(env=case_info['env'], group=case_info['group'])
        questions = case_info['questions']
        expected_answers = case_info['expected_answers']
        reference_answers = case_info.get('reference_answers') or expected_answers
        round_intents = case_info.get('round_intents') or [case_info['intent'] for _ in questions]
        previous_intents = case_info.get('previous_intents') or ['' if i == 0 else round_intents[i - 1] for i in range(len(questions))]
        context_assert_types = case_info.get('context_assert_types') or ['normal' for _ in questions]
        expect_refuses = case_info.get('expect_refuses') or [False for _ in questions]
        expect_assets = case_info.get('expect_assets') or [False for _ in questions]
        enriched_rounds = case_info.get('enriched_rounds') or []
        msg_context_list = []
        round_rows = []
        sum_round_response_time = 0
        exec_res = None
        msg_info = None
        chat_id = f"chat_{case_info['env']}_{case_info['case_id']}_{int(time.time() * 1000000)}"
        switches = ModelIntentAssert.get_multi_turn_assert_switches()

        for i, question in enumerate(questions):
            msg_context_list.append(ModelCaseHandler.build_customer_msg(content=question, index=i * 2))
            msg_info = {
                'uid': get_random_uid(),
                'content': question,
                'chatId': chat_id,
                'msgContextList': msg_context_list
            }

            start_time = time.time()
            exec_res = model.send_msg_to_model(msg_info=msg_info)
            round_response_time = time.time() - start_time
            sum_round_response_time += round_response_time
            actual_answer = ModelIntentAssert.extract_model_answer(output_data=exec_res.get('output_data'))
            should_assert = case_info['round_assert_flags'][i]
            round_meta = enriched_rounds[i] if i < len(enriched_rounds) else {
                'round_intent': round_intents[i] if i < len(round_intents) else case_info['intent'],
                'previous_intent': previous_intents[i] if i < len(previous_intents) else '',
                'context_assert_type': context_assert_types[i] if i < len(context_assert_types) else 'normal',
                'should_assert': should_assert,
                'expect_refuse': expect_refuses[i] if i < len(expect_refuses) else False,
                'expect_asset': expect_assets[i] if i < len(expect_assets) else False,
                'reference_answer': reference_answers[i],
                'expected_answer': expected_answers[i],
            }
            round_info = {
                'round': i + 1,
                'question': question,
                'expected_answer': round_meta.get('expected_answer', expected_answers[i]),
                'reference_answer': round_meta.get('reference_answer', reference_answers[i]),
                'round_intent': round_meta.get('round_intent', round_intents[i] if i < len(round_intents) else case_info['intent']),
                'previous_intent': round_meta.get('previous_intent', previous_intents[i] if i < len(previous_intents) else ''),
                'context_assert_type': round_meta.get('context_assert_type', context_assert_types[i] if i < len(context_assert_types) else 'normal'),
                'should_assert': should_assert,
                'expect_refuse': round_meta.get('expect_refuse', expect_refuses[i] if i < len(expect_refuses) else False),
                'expect_asset': round_meta.get('expect_asset', expect_assets[i] if i < len(expect_assets) else False),
                'request_data': exec_res.get('request_data'),
            }
            if should_assert:
                round_eval = ModelIntentAssert.evaluate_multi_turn_round(
                    round_info=round_info,
                    output_data=exec_res.get('output_data'),
                    context_rounds=round_rows,
                    response_time=round_response_time,
                    similarity_threshold=case_info['similarity_threshold']
                )
            else:
                round_eval = {
                    'round': i + 1,
                    'question': question,
                    'expected_answer': expected_answers[i],
                    'reference_answer': reference_answers[i],
                    'actual_answer': actual_answer,
                    'round_intent': round_info['round_intent'],
                    'actual_intent': '',
                    'previous_intent': round_info['previous_intent'],
                    'context_assert_type': round_info['context_assert_type'],
                    'expect_refuse': round_info['expect_refuse'],
                    'standard_similarity_score': 100,
                    'reference_similarity_score': 100,
                    'similarity_score': 100,
                    'similarity_pass': True,
                    'similarity_reason': '当前轮次配置为不参与断言',
                    'intent_pass': True,
                    'context_carry_pass': True,
                    'intent_pollution_pass': True,
                    'user_correction_pass': True,
                    'risk_refusal_pass': True,
                    'return_to_business_pass': True,
                    'asset_present': False,
                    'asset_allowed': False,
                    'asset_value': '',
                    'asset_value_pass': True,
                    'biz_ref_id': '',
                    'biz_ref_id_pass': True,
                    'asset_allow_pass': True,
                    'asset_pass': True,
                    'asset_failure_reasons': [],
                    'assert_items': [],
                    'failed_assert_items': [],
                    'failure_suggestions': [],
                    'round_pass': True,
                    'failure_reason': '',
                    'response_time': round(round_response_time, 3),
                    'request_data': exec_res.get('request_data'),
                    'output_data': exec_res.get('output_data'),
                    'should_assert': False,
                }
            msg_context_list.append(ModelCaseHandler.build_staff_msg(content=actual_answer, index=i * 2 + 1))

            round_row = {
                'round': i + 1,
                'question': question,
                'expected_answer': expected_answers[i],
                'reference_answer': reference_answers[i],
                'actual_answer': actual_answer,
                'round_intent': round_eval.get('round_intent'),
                'chat_type': round_eval.get('chat_type'),
                'handoff_reason': round_eval.get('handoff_reason'),
                'chat_type_pass': round_eval.get('chat_type_pass'),
                'previous_intent': round_eval.get('previous_intent'),
                'context_assert_type': round_eval.get('context_assert_type'),
                'expect_refuse': round_eval.get('expect_refuse'),
                'standard_similarity_score': round_eval.get('standard_similarity_score'),
                'reference_similarity_score': round_eval.get('reference_similarity_score'),
                'similarity_score': round_eval.get('similarity_score'),
                'similarity_pass': round_eval.get('similarity_pass'),
                'similarity_reason': round_eval.get('similarity_reason'),
                'intent_pass': round_eval.get('intent_pass'),
                'intent_reason': round_eval.get('intent_reason'),
                'context_carry_pass': round_eval.get('context_carry_pass'),
                'intent_pollution_pass': round_eval.get('intent_pollution_pass'),
                'user_correction_pass': round_eval.get('user_correction_pass'),
                'risk_refusal_pass': round_eval.get('risk_refusal_pass'),
                'return_to_business_pass': round_eval.get('return_to_business_pass'),
                'asset_present': round_eval.get('asset_present'),
                'asset_allowed': round_eval.get('asset_allowed'),
                'asset_value': round_eval.get('asset_value'),
                'asset_value_pass': round_eval.get('asset_value_pass'),
                'biz_ref_id': round_eval.get('biz_ref_id'),
                'biz_ref_id_pass': round_eval.get('biz_ref_id_pass'),
                'asset_pass': round_eval.get('asset_pass'),
                'assert_items': round_eval.get('assert_items') or [],
                'failed_assert_items': round_eval.get('failed_assert_items') or [],
                'failure_suggestions': round_eval.get('failure_suggestions') or [],
                'round_pass': round_eval.get('round_pass'),
                'failure_reason': round_eval.get('failure_reason'),
                'should_assert': should_assert,
                'response_time': round(round_response_time, 3),
                'request_data': exec_res.get('request_data'),
                'output_data': exec_res.get('output_data'),
            }
            round_rows.append(round_row)
            log.info(f"【多轮第{i + 1}轮】用户问题：{question}，模型回复：{actual_answer}，相似度：{round_eval.get('similarity_score')}，意图：{round_eval.get('actual_intent')}，耗时：{round(round_response_time, 3)}s")

        assert_round_rows = [row for row in round_rows if row['should_assert']]
        all_rounds_pass = all(row['round_pass'] for row in assert_round_rows) if assert_round_rows else True
        last_round_pass = round_rows[-1]['round_pass'] if round_rows else True
        avg_round_response_time = round(sum_round_response_time / len(round_rows), 3) if round_rows else 0
        avg_similarity_score = round(sum([row['similarity_score'] for row in assert_round_rows]) / len(assert_round_rows), 2) if assert_round_rows else 100
        similarity_pass = avg_similarity_score >= case_info['similarity_threshold']
        final_pass = similarity_pass
        if switches['require_all_assert_rounds_pass']:
            final_pass = final_pass and all_rounds_pass
        if switches['require_last_round_pass']:
            final_pass = final_pass and last_round_pass
        report_row = {
            'case_id': case_info['case_id'],
            'case_type': case_info['case_type'],
            'case_desc': case_info['case_desc'],
            'remark': case_info.get('remark'),
            'intent': case_info['intent'],
            'actual_intent': '',
            'question': case_info['question'],
            'expected_answer': case_info['expected_answer'],
            'actual_answer': round_rows[-1]['actual_answer'],
            'is_same_meaning': final_pass,
            'similarity_score': avg_similarity_score,
            'similarity_reason': f"多轮逐轮平均相似度：{avg_similarity_score}",
            'similarity_threshold': case_info['similarity_threshold'],
            'similarity_pass': similarity_pass,
            'all_rounds_pass': all_rounds_pass,
            'last_round_pass': last_round_pass,
            'assert_switches': json.dumps(switches, ensure_ascii=False),
            'failure_reason': '；'.join([row.get('failure_reason') for row in assert_round_rows if row.get('failure_reason')]),
            'response_time': avg_round_response_time,
            'total_response_time': round(sum_round_response_time, 3),
            'round_count': len(round_rows),
            'is_pass': final_pass,
            'output_data': json.dumps(exec_res.get('output_data'), ensure_ascii=False),
            'round_detail': json.dumps(round_rows, ensure_ascii=False)
        }
        MODEL_REPORT_ROWS.append(report_row)
        ModelCaseHandler.save_model_rows([report_row])

        failed_round_rows = [row for row in round_rows if row['should_assert'] and not row.get('round_pass')]
        failure_summary_lines = ['【多轮失败定位摘要】：']
        if failed_round_rows:
            for row in failed_round_rows:
                failed_dimensions = [item.get('dimension', '') for item in row.get('failed_assert_items') or []]
                failure_summary_lines.extend([
                    f"第{row['round']}轮 | 失败维度：{'、'.join(failed_dimensions)} | 原因：{row.get('failure_reason')}",
                    f"问题：{row['question']}",
                    f"模型回复：{row['actual_answer']}",
                    f"修复建议：{'；'.join(row.get('failure_suggestions') or [])}"
                ])
        else:
            failure_summary_lines.append('无失败轮次')

        round_log_lines = [
            f"【多轮平均响应耗时】：{avg_round_response_time}s",
            f"【多轮总响应耗时】：{round(sum_round_response_time, 3)}s",
            '【多轮逐轮评分明细】：'
        ]
        for row in round_rows:
            failed_dimensions = '、'.join([item.get('dimension', '') for item in row.get('failed_assert_items') or []]) or '无'
            suggestions = '；'.join(row.get('failure_suggestions') or []) or '无'
            round_log_lines.extend([
                f"------ 第{row['round']}轮 ------",
                f"用户问题：{row['question']}",
                f"期望意图：{row['round_intent']}",
                f"实际意图：{row.get('actual_intent')}",
                f"chatType：{row.get('chat_type')}",
                f"handoffReason：{row.get('handoff_reason')}",
                f"chatType断言：{row.get('chat_type_pass')}",
                f"上下文类型：{row.get('context_assert_type')}",
                f"上一轮意图：{row.get('previous_intent')}",
                f"标准答案：{row['expected_answer']}",
                f"参考答案：{row.get('reference_answer')}",
                f"模型回复：{row['actual_answer']}",
                f"标准答案评分：{row.get('standard_similarity_score')}",
                f"参考答案评分：{row.get('reference_similarity_score')}",
                f"平均相似度：{row['similarity_score']}",
                f"意图断言：{row.get('intent_pass')}",
                f"上下文承接：{row.get('context_carry_pass')}",
                f"意图污染：{row.get('intent_pollution_pass')}",
                f"改口更新：{row.get('user_correction_pass')}",
                f"风险拒答：{row.get('risk_refusal_pass')}",
                f"回归业务：{row.get('return_to_business_pass')}",
                f"ASSET存在：{row.get('asset_present')}",
                f"ASSET允许：{row.get('asset_allowed')}",
                f"ASSET校验：{row.get('asset_pass')}",
                f"失败维度：{failed_dimensions}",
                f"失败原因：{row.get('failure_reason') or '无'}",
                f"修复建议：{suggestions}",
                f"是否断言：{row['should_assert']}",
                f"响应耗时：{row['response_time']}s",
                f"是否通过：{row.get('round_pass')}"
            ])
        exec_log = build_exec_log(case_info=case_info, msg_info=msg_info, exec_res=exec_res, report_row=report_row, response_time=avg_round_response_time)
        exec_log = exec_log + '\n' + '\n'.join(failure_summary_lines) + '\n' + '\n'.join(round_log_lines)
        actual_dialog_text = build_multi_turn_actual_dialog(round_rows=round_rows)
        assert_dialog_text = build_multi_turn_assert_dialog(round_rows=round_rows)
        eval_body = build_multi_turn_eval_body(round_rows=round_rows, report_row=report_row)
        log.info(f"\n{exec_log}")
        allure.attach(actual_dialog_text, '信贷大模型实际话术', allure.attachment_type.TEXT)
        allure.attach(assert_dialog_text, '断言话术', allure.attachment_type.TEXT)
        allure.attach('\n'.join(failure_summary_lines), '多轮失败定位摘要', allure.attachment_type.TEXT)
        allure.attach(exec_log, '执行日志', allure.attachment_type.TEXT)
        allure.attach(eval_body, '模型评估明细CSV', allure.attachment_type.CSV)
        allure.attach(json.dumps(round_rows, ensure_ascii=False, indent=2), '多轮逐轮评估明细', allure.attachment_type.JSON)

        ModelIntentAssert.assert_model_result(report_row=report_row)

    @allure.story('模型测试汇总报告')
    @pytest.mark.model_summary
    def test_model_summary_report(self) -> None:
        """
        【信贷大模型--汇总报告】
        :return: None
        """
        report_rows = ModelCaseHandler.load_model_rows_from_run() or MODEL_REPORT_ROWS
        attach_model_report(report_rows=report_rows)
        assert True


def teardown_module():
    """
    模块结束后输出模型评估明细报表
    :return:
    """
    report_rows = ModelCaseHandler.load_model_rows_from_run() or MODEL_REPORT_ROWS
    if not report_rows:
        return

    attach_model_report(report_rows=report_rows)
