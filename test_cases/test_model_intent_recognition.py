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
import threading
import time

Base_Path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(Base_Path)

import allure
import pytest

from assert_code.model_intent_assert import ModelIntentAssert, AssertMode
from assert_code.postloan_intent_assert import PostloanIntentAssert
from debug_model_by_pytest import TestConfig
from script_code.model_intent_recognition_exec import ModelIntentRecognition
from utils.handle_log import log
from utils.handle_model_cases import assemble_model_case_params, get_model_case_desc, ModelCaseHandler
from utils.postloan_model_cases import assemble_postloan_case_params, get_postloan_case_desc
from utils.handle_allure_report import (
    attach_single_turn_report,
    attach_multi_turn_report,
    attach_model_assert_detail,
)


from utils.batch_assert_collector import batch_collector


MODEL_REPORT_ROWS = []
_MODEL_REPORT_ROWS_LOCK = threading.Lock()

# uid 池加载与分配（支持多池子缓存）
_UID_POOLS = {}


def _load_uid_pool(pool_name: str = 'credit') -> list:
    """
    从 uid 池文件加载 uid
    :param pool_name: 'credit' 表示信贷池，'postloan' 表示贷后池
    """
    if pool_name in _UID_POOLS:
        return _UID_POOLS[pool_name]

    if pool_name == 'postloan':
        filename = 'postloan_uids_pool.csv'
    else:
        filename = 'credited_uids_pool.csv'

    uid_file = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'case_data', filename
    )
    if not os.path.exists(uid_file):
        raise FileNotFoundError(
            f"uid 池文件不存在: {uid_file}\n"
            f"请确保 case_data/{filename} 存在且至少包含一行 uid 数据。"
        )
    with open(uid_file, 'r', encoding='utf-8-sig') as f:  # utf-8-sig 自动处理 BOM
        reader = csv.DictReader(f)
        _UID_POOLS[pool_name] = [
            row['uid'].strip() for row in reader
            if row.get('uid', '').strip()
        ]
    if not _UID_POOLS[pool_name]:
        raise ValueError(
            f"uid 池文件内容为空: {uid_file}\n"
            f"请确保 CSV 文件包含至少一个有效的 uid 值。"
        )
    return _UID_POOLS[pool_name]


def get_random_uid(pool_name: str = 'credit') -> str:
    """从 uid 池中纯随机获取一个 uid（不记录已使用状态）"""
    pool = _load_uid_pool(pool_name)
    return random.choice(pool)


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
    # 批量断言模式下，不挂载传统汇总附件（批量断言有独立的 HTML/CSV 报告）
    is_batch_mode = os.getenv('MODEL_BATCH_ASSERT', '0') == '1'

    if not report_rows:
        if not is_batch_mode:
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

    # 仅在非批量断言模式下挂载传统汇总附件
    if not is_batch_mode:
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

        # 检测批量断言模式
        if os.getenv('MODEL_BATCH_ASSERT', '0') == '1':
            # 批量模式：只做本地断言（提取回复 + chatType + ASSET），不调用外部模型
            # 外部模型的语义评估统一推迟到 test_model_summary_report 中批量执行
            actual_answer = ModelIntentAssert.extract_model_answer(output_data=exec_res.get('output_data'))
            actual_intent = ModelIntentAssert.extract_model_intent(output_data=exec_res.get('output_data'))
            reply_info = ModelIntentAssert._extract_reply_contents(output_data=exec_res.get('output_data'))
            chat_type_eval = ModelIntentAssert._evaluate_chat_type_result(case_info['intent'], reply_info)
            asset_eval = ModelIntentAssert.evaluate_asset_result(case_info['intent'], reply_info)

            # 构造本地评估结果（与 evaluate_single_turn 返回结构兼容，但不含外部模型评估）
            fail_reasons = []
            if not chat_type_eval['chat_type_pass']:
                fail_reasons.extend(chat_type_eval['chat_type_failure_reasons'])
            if not asset_eval['asset_pass']:
                fail_reasons.extend(asset_eval['asset_failure_reasons'])

            local_eval = {
                'actual_intent': actual_intent,
                'chat_type': chat_type_eval['chat_type'],
                'handoff_reason': chat_type_eval['handoff_reason'],
                'chat_type_pass': chat_type_eval['chat_type_pass'],
                'reply_contents_raw': json.dumps(reply_info.get('reply_contents_raw'), ensure_ascii=False),
                'text_values': json.dumps(reply_info.get('text_values'), ensure_ascii=False),
                'asset_values': json.dumps(reply_info.get('asset_values'), ensure_ascii=False),
                'biz_ref_ids': json.dumps(reply_info.get('biz_ref_ids'), ensure_ascii=False),
                'asset_present': asset_eval['asset_present'],
                'asset_allowed': asset_eval['asset_allowed'],
                'asset_value': asset_eval['asset_value'],
                'asset_value_pass': asset_eval['asset_value_pass'],
                'biz_ref_id': asset_eval['biz_ref_id'],
                'biz_ref_id_pass': asset_eval['biz_ref_id_pass'],
                'fail_reasons': fail_reasons,
                'failure_reason': '；'.join(fail_reasons) if fail_reasons else '',
                'assert_detail': {
                    'chat_type': chat_type_eval['chat_type'],
                    'chat_type_pass': chat_type_eval['chat_type_pass'],
                    'asset_present': asset_eval['asset_present'],
                    'asset_allowed': asset_eval['asset_allowed'],
                    'asset_value': asset_eval['asset_value'],
                    'asset_value_pass': asset_eval['asset_value_pass'],
                    'biz_ref_id': asset_eval['biz_ref_id'],
                    'biz_ref_id_pass': asset_eval['biz_ref_id_pass'],
                    'fail_reasons': fail_reasons,
                },
            }

            # 收集数据时，同时记录 chat_type 信息（用于批量评估阶段判断是否跳过语义评分）
            batch_collector.add({
                'case_id': case_info['case_id'],
                'case_type': TestConfig.CASE_TYPE_SINGLE_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'question': case_info['question'],
                'actual_answer': actual_answer,
                'expected_answer': case_info['expected_answer'],
                'similarity_threshold': case_info['similarity_threshold'],
                'response_time': response_time,
                'env': case_info['env'],
                'group': case_info['group'],
                # 本地断言结果（用于批量评估后合并）
                'local_chat_type_pass': local_eval['chat_type_pass'],
                'local_asset_value_pass': local_eval['asset_value_pass'],
                'local_biz_ref_id_pass': local_eval['biz_ref_id_pass'],
                'local_failure_reason': local_eval.get('failure_reason', ''),
                # chat_type 标记（用于判断是否跳过语义评估）
                'chat_type': local_eval.get('chat_type', 'NORMAL'),
                'output_data': exec_res.get('output_data'),
                'msg_info': msg_info,
            })
            log.info(f"【批量断言】已收集单轮数据：case_id={case_info['case_id']}, intent={case_info['intent']}")
            # 本地简单断言：确保接口返回了数据
            assert actual_answer, f"信贷模型返回为空：case_id={case_info['case_id']}"
            # 批量模式下，Allure 报告需要挂载基础信息
            allure.attach(actual_answer, '信贷大模型实际话术', allure.attachment_type.TEXT)
            allure.attach(case_info['expected_answer'], '断言话术', allure.attachment_type.TEXT)
            if exec_res.get('output_data'):
                allure.attach(
                    json.dumps(exec_res.get('output_data'), ensure_ascii=False, indent=2),
                    '信贷大模型完整返参',
                    allure.attachment_type.JSON,
                )
            allure.attach('当前为批量断言模式，详细评估结果将在测试结束后批量生成', '批量断言提示', allure.attachment_type.TEXT)
            # 保存完整报告数据到持久化文件（用于后续 Allure 报告和企微通知统计）
            report_row = {
                'case_id': case_info['case_id'],
                'case_type': TestConfig.CASE_TYPE_SINGLE_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'actual_intent': local_eval.get('actual_intent', ''),
                'question': case_info['question'],
                'expected_answer': case_info['expected_answer'],
                'actual_answer': actual_answer,
                'chat_type': local_eval.get('chat_type', ''),
                'handoff_reason': local_eval.get('handoff_reason', ''),
                'chat_type_pass': local_eval['chat_type_pass'],
                'reply_contents_raw': local_eval.get('reply_contents_raw', ''),
                'text_values': local_eval.get('text_values', ''),
                'asset_values': local_eval.get('asset_values', ''),
                'biz_ref_ids': local_eval.get('biz_ref_ids', ''),
                'is_same_meaning': local_eval.get('is_same_meaning', True),
                'similarity_score': 0,
                'similarity_reason': '批量断言模式：详细评估结果将在测试结束后批量生成',
                'similarity_threshold': case_info['similarity_threshold'],
                'text_threshold': case_info['similarity_threshold'],
                'text_comparator': 'gte',
                'text_pass': True,
                'asset_present': local_eval.get('asset_present', False),
                'asset_allowed': local_eval.get('asset_allowed', False),
                'asset_value': local_eval.get('asset_value', ''),
                'asset_value_pass': local_eval['asset_value_pass'],
                'biz_ref_id': local_eval.get('biz_ref_id', ''),
                'biz_ref_id_pass': local_eval['biz_ref_id_pass'],
                'fail_reasons': local_eval.get('fail_reasons', []),
                'failure_reason': '批量断言模式：详细评估结果将在测试结束后批量生成',
                'similarity_pass': True,
                'response_time': round(response_time, 3),
                'is_pass': local_eval['chat_type_pass'] and local_eval['asset_value_pass'] and local_eval['biz_ref_id_pass'],
                'assert_detail': local_eval.get('assert_detail', {}),
                'output_data': json.dumps(exec_res.get('output_data'), ensure_ascii=False) if exec_res.get('output_data') else '',
            }
            ModelCaseHandler.save_model_rows([report_row])
            return

        # 非批量模式：正常执行外部模型断言
        report_row = ModelIntentAssert.evaluate_single_turn(
            case_info=case_info,
            output_data=exec_res.get('output_data'),
            response_time=response_time,
            assert_mode=ModelIntentAssert.get_assert_mode(),
        )
        with _MODEL_REPORT_ROWS_LOCK:
            MODEL_REPORT_ROWS.append(report_row)
        ModelCaseHandler.save_model_rows([report_row])

        exec_log = build_exec_log(case_info=case_info, msg_info=msg_info, exec_res=exec_res, report_row=report_row, response_time=response_time)
        log.info(f"\n{exec_log}")

        # 使用封装函数挂载 allure 报告（与断言模式联动）
        assert_mode = ModelIntentAssert.get_assert_mode()
        attach_single_turn_report(report_row=report_row, case_info=case_info, assert_mode=assert_mode.value)
        attach_model_assert_detail(report_row=report_row, assert_mode=assert_mode.value)

        assert_answer_text = '\n'.join([
            f"【标准答案】：{report_row['expected_answer']}",
        ])
        allure.attach(report_row['actual_answer'], '信贷大模型实际话术', allure.attachment_type.TEXT)
        allure.attach(assert_answer_text, '断言话术', allure.attachment_type.TEXT)
        # 挂载模型完整返参
        output_data = exec_res.get('output_data')
        if output_data:
            allure.attach(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                '信贷大模型完整返参',
                allure.attachment_type.JSON,
            )

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
        uid = get_random_uid()

        is_batch_mode = os.getenv('MODEL_BATCH_ASSERT', '0') == '1'

        for i, question in enumerate(questions):
            msg_context_list.append(ModelCaseHandler.build_customer_msg(content=question, index=i * 2))
            msg_info = {
                'uid': uid,
                'content': question,
                'chatId': chat_id,
                'msgContextList': msg_context_list
            }

            start_time = time.time()
            exec_res = model.send_msg_to_model(msg_info=msg_info)
            round_response_time = time.time() - start_time
            sum_round_response_time += round_response_time
            actual_answer = ModelIntentAssert.extract_model_answer(output_data=exec_res.get('output_data'))
            round_meta = enriched_rounds[i] if i < len(enriched_rounds) else {
                'round_intent': round_intents[i] if i < len(round_intents) else case_info['intent'],
                'previous_intent': previous_intents[i] if i < len(previous_intents) else '',
                'context_assert_type': context_assert_types[i] if i < len(context_assert_types) else 'normal',
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
                'expect_refuse': round_meta.get('expect_refuse', expect_refuses[i] if i < len(expect_refuses) else False),
                'expect_asset': round_meta.get('expect_asset', expect_assets[i] if i < len(expect_assets) else False),
                'request_data': exec_res.get('request_data'),
            }
            if is_batch_mode:
                # 批量模式：只做本地断言（提取回复、chatType、ASSET），跳过外部模型
                reply_info = ModelIntentAssert._extract_reply_contents(output_data=exec_res.get('output_data'))
                chat_type_eval = ModelIntentAssert._evaluate_chat_type_result(round_info['round_intent'], reply_info)
                asset_eval = ModelIntentAssert.evaluate_asset_result(round_info['round_intent'], reply_info)
                round_eval = {
                    'round': i + 1,
                    'question': question,
                    'expected_answer': expected_answers[i],
                    'reference_answer': reference_answers[i],
                    'actual_answer': actual_answer,
                    'round_intent': round_info['round_intent'],
                    'actual_intent': '',
                    'chat_type': chat_type_eval['chat_type'],
                    'handoff_reason': chat_type_eval['handoff_reason'],
                    'chat_type_pass': chat_type_eval['chat_type_pass'],
                    'previous_intent': round_info['previous_intent'],
                    'context_assert_type': round_info['context_assert_type'],
                    'expect_refuse': round_info['expect_refuse'],
                    'standard_similarity_score': 0,
                    'reference_similarity_score': 0,
                    'similarity_score': 0,
                    'similarity_pass': True,
                    'similarity_reason': '批量断言模式：详细评估结果将在测试结束后批量生成',
                    'intent_pass': True,
                    'intent_reason': '',
                    'context_carry_pass': True,
                    'intent_pollution_pass': True,
                    'user_correction_pass': True,
                    'risk_refusal_pass': True,
                    'return_to_business_pass': True,
                    'asset_present': asset_eval['asset_present'],
                    'asset_allowed': asset_eval['asset_allowed'],
                    'asset_value': asset_eval['asset_value'],
                    'asset_value_pass': asset_eval['asset_value_pass'],
                    'biz_ref_id': asset_eval['biz_ref_id'],
                    'biz_ref_id_pass': asset_eval['biz_ref_id_pass'],
                    'asset_pass': asset_eval['asset_pass'],
                    'assert_items': [],
                    'failed_assert_items': [],
                    'failure_suggestions': [],
                    'round_pass': True,
                    'failure_reason': '',
                    'response_time': round(round_response_time, 3),
                    'request_data': exec_res.get('request_data'),
                    'output_data': exec_res.get('output_data'),
                }
            else:
                round_eval = ModelIntentAssert.evaluate_multi_turn_round(
                    round_info=round_info,
                    output_data=exec_res.get('output_data'),
                    context_rounds=round_rows,
                    response_time=round_response_time,
                    similarity_threshold=case_info['similarity_threshold'],
                    assert_mode=ModelIntentAssert.get_assert_mode(),
                )
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
                'response_time': round(round_response_time, 3),
                'request_data': exec_res.get('request_data'),
                'output_data': exec_res.get('output_data'),
            }
            round_rows.append(round_row)
            log.info(f"【多轮第{i + 1}轮】用户问题：{question}，模型回复：{actual_answer}，相似度：{round_eval.get('similarity_score')}，意图：{round_eval.get('actual_intent')}，耗时：{round(round_response_time, 3)}s")

        # 检测批量断言模式
        if os.getenv('MODEL_BATCH_ASSERT', '0') == '1':
            # 批量模式：收集完整多轮对话数据（一个 case 包含所有轮次）
            multi_turn_rounds = []
            for round_row in round_rows:
                multi_turn_rounds.append({
                    'round': round_row['round'],
                    'question': round_row['question'],
                    'actual_answer': round_row['actual_answer'],
                    'expected_answer': round_row['expected_answer'],
                    'round_intent': round_row.get('round_intent', case_info['intent']),
                    'context_assert_type': round_row.get('context_assert_type', 'normal'),
                    'previous_intent': round_row.get('previous_intent', ''),
                })

            batch_collector.add({
                'case_id': case_info['case_id'],
                'case_type': TestConfig.CASE_TYPE_MULTI_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'similarity_threshold': case_info['similarity_threshold'],
                'rounds': multi_turn_rounds,
                # 保留最后一轮的 output_data，用于兼容旧逻辑
                'last_output_data': exec_res.get('output_data'),
                # 新增：收集每一轮的 output_data，用于逐轮本地断言（ASSET、转人工）
                'round_outputs': [
                    {
                        'round': r['round'],
                        'output_data': r.get('output_data'),
                        'round_intent': r.get('round_intent', case_info['intent']),
                    }
                    for r in round_rows
                    if r.get('output_data')
                ],
            })
            log.info(f"【批量断言】已收集多轮数据：case_id={case_info['case_id']}, 共 {len(multi_turn_rounds)} 轮")
            # 本地简单断言：确保至少有一轮返回了数据
            assert round_rows, f"多轮测试无数据：case_id={case_info['case_id']}"
            # 本地简单断言：确保至少有一轮返回了数据
            assert round_rows, f"多轮测试无数据：case_id={case_info['case_id']}"
            # 挂载 Allure 基础信息 - 合并展示所有轮次的对话
            # 每轮请求入参和模型回复（用于排查问题）
            round_detail_lines = []
            for round_row in round_rows:
                round_detail_lines.append(f"{'=' * 60}")
                round_detail_lines.append(f"【第{round_row['round']}轮】")
                round_detail_lines.append(f"用户问题：{round_row['question']}")
                round_detail_lines.append(f"模型回复：{round_row['actual_answer']}")
                round_detail_lines.append(f"标准答案：{round_row['expected_answer']}")
                round_detail_lines.append(f"响应耗时：{round_row['response_time']}s")
                # 请求入参
                request_data = round_row.get('request_data')
                if request_data:
                    round_detail_lines.append(f"\n【请求入参】")
                    try:
                        import json
                        round_detail_lines.append(json.dumps(request_data, ensure_ascii=False, indent=2))
                    except Exception:
                        round_detail_lines.append(str(request_data))
                # 模型回复结果
                output_data = round_row.get('output_data')
                if output_data:
                    round_detail_lines.append(f"\n【模型回复结果】")
                    try:
                        import json
                        round_detail_lines.append(json.dumps(output_data, ensure_ascii=False, indent=2))
                    except Exception:
                        round_detail_lines.append(str(output_data))
                round_detail_lines.append('')

            allure.attach(
                '\n'.join(round_detail_lines),
                '多轮逐轮请求入参与模型回复详情',
                allure.attachment_type.TEXT,
            )

            actual_dialog_lines = []
            expected_dialog_lines = []
            for round_row in round_rows:
                actual_dialog_lines.append(f"第{round_row['round']}轮")
                actual_dialog_lines.append(f"  用户：{round_row['question']}")
                actual_dialog_lines.append(f"  模型：{round_row['actual_answer']}")
                expected_dialog_lines.append(f"第{round_row['round']}轮")
                expected_dialog_lines.append(f"  用户：{round_row['question']}")
                expected_dialog_lines.append(f"  标准：{round_row['expected_answer']}")

            allure.attach(
                '\n'.join(actual_dialog_lines),
                '多轮真实对话（合并展示）',
                allure.attachment_type.TEXT,
            )
            allure.attach(
                '\n'.join(expected_dialog_lines),
                '多轮标准话术（合并展示）',
                allure.attachment_type.TEXT,
            )
            allure.attach('当前为批量断言模式，详细评估结果将在测试结束后批量生成', '批量断言提示', allure.attachment_type.TEXT)
            # 保存完整报告数据到持久化文件（用于后续 Allure 报告和企微通知统计）
            avg_round_response_time = round(sum_round_response_time / len(round_rows), 3) if round_rows else 0
            report_row = {
                'case_id': case_info['case_id'],
                'case_type': TestConfig.CASE_TYPE_MULTI_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'actual_intent': '',
                'question': case_info['question'],
                'expected_answer': case_info['expected_answer'],
                'actual_answer': round_rows[-1]['actual_answer'] if round_rows else '',
                'chat_type': '',
                'handoff_reason': '',
                'chat_type_pass': True,
                'reply_contents_raw': '',
                'text_values': '',
                'asset_values': '',
                'biz_ref_ids': '',
                'is_same_meaning': True,
                'similarity_score': 0,
                'similarity_reason': '批量断言模式：详细评估结果将在测试结束后批量生成',
                'similarity_threshold': case_info['similarity_threshold'],
                'text_threshold': case_info['similarity_threshold'],
                'text_comparator': 'gte',
                'text_pass': True,
                'asset_present': False,
                'asset_allowed': False,
                'asset_value': '',
                'asset_value_pass': True,
                'biz_ref_id': '',
                'biz_ref_id_pass': True,
                'fail_reasons': [],
                'failure_reason': '批量断言模式：详细评估结果将在测试结束后批量生成',
                'similarity_pass': True,
                'response_time': avg_round_response_time,
                'is_pass': True,
                'assert_detail': {},
                'output_data': json.dumps(exec_res.get('output_data'), ensure_ascii=False) if exec_res.get('output_data') else '',
                'round_count': len(round_rows),
            }
            ModelCaseHandler.save_model_rows([report_row])
            return

        # ============================================================
        # 非批量模式：所有轮次执行完毕后，一次性多维度评估
        # ============================================================
        if not os.getenv('MODEL_BATCH_ASSERT', '0') == '1' and round_rows:
            # 构建评估数据
            multi_turn_rounds = []
            for round_row in round_rows:
                multi_turn_rounds.append({
                    'round': round_row['round'],
                    'question': round_row['question'],
                    'actual_answer': round_row['actual_answer'],
                    'expected_answer': round_row['expected_answer'],
                    'round_intent': round_row.get('round_intent', case_info['intent']),
                    'context_assert_type': round_row.get('context_assert_type', 'normal'),
                    'previous_intent': round_row.get('previous_intent', ''),
                })

            case_data = {
                'case_id': case_info['case_id'],
                'case_type': TestConfig.CASE_TYPE_MULTI_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'similarity_threshold': case_info['similarity_threshold'],
                'rounds': multi_turn_rounds,
                # 保留最后一轮的 output_data，用于本地断言
                'last_output_data': round_rows[-1].get('output_data'),
                # 收集每一轮的 output_data，用于逐轮本地断言（ASSET、转人工）
                'round_outputs': [
                    {
                        'round': r['round'],
                        'output_data': r.get('output_data'),
                        'round_intent': r.get('round_intent', case_info['intent']),
                    }
                    for r in round_rows
                    if r.get('output_data')
                ],
            }

            # 调用 MultiTurnEvaluator 进行一次性评估
            from assert_code.batch_assert_strategies import MultiTurnEvaluator
            from assert_code.external_model_judge import ExternalModelJudge
            judge = ExternalModelJudge(
                model_name=os.getenv('MODEL_BATCH_JUDGE_MODEL', 'deepseek-v4-pro'),
                use_knowledge_base=True,
                inject_knowledge_as_system=True,
            )
            result = MultiTurnEvaluator.evaluate_single(case_data, judge)

            # 更新 round_rows（将评估结果分配到最后一轮）
            if round_rows:
                last_row = round_rows[-1]
                last_row['similarity_score'] = result.get('overall_score', 0)
                last_row['similarity_pass'] = result.get('overall_pass', False)
                last_row['similarity_reason'] = result.get('failure_reason', '')
                last_row['round_pass'] = result.get('overall_pass', False)
                last_row['failure_reason'] = result.get('failure_reason', '')
                # 本地断言结果
                last_row['chat_type_pass'] = result.get('transfer_pass', True)
                last_row['asset_pass'] = result.get('asset_pass', True)

            log.info(f"【多轮一次性评估】case_id={case_info['case_id']}, overall_score={result.get('overall_score')}, overall_pass={result.get('overall_pass')}, transfer_pass={result.get('transfer_pass')}, asset_pass={result.get('asset_pass')}")

        assert_round_rows = round_rows
        overall_pass = round_rows[-1]['round_pass'] if round_rows else True
        avg_round_response_time = round(sum_round_response_time / len(round_rows), 3) if round_rows else 0
        avg_similarity_score = round(sum([row['similarity_score'] for row in assert_round_rows]) / len(assert_round_rows), 2) if assert_round_rows else 100
        similarity_pass = avg_similarity_score >= case_info['similarity_threshold']
        final_pass = similarity_pass and overall_pass

        # ====== 多轮增强评估（可选，通过 MODEL_ENHANCED_MULTI_TURN_EVAL 环境变量控制）======
        enhanced_result = None
        if os.getenv('MODEL_ENHANCED_MULTI_TURN_EVAL', '0') == '1':
            try:
                enhanced_result = ModelIntentAssert.evaluate_multi_turn_enhanced(
                    case_info=case_info,
                    round_rows=round_rows,
                    round_eval_results=round_rows,
                    enable_llm_judge=os.getenv('MODEL_ENHANCED_ENABLE_LLM_JUDGE', '1') == '1',
                    enable_state_validation=os.getenv('MODEL_ENHANCED_ENABLE_STATE_VALIDATION', '1') == '1',
                    enable_consistency_check=os.getenv('MODEL_ENHANCED_ENABLE_CONSISTENCY_CHECK', '1') == '1',
                    llm_judge_model=os.getenv('MODEL_ENHANCED_LLM_JUDGE_MODEL', 'kimi-k2.6') or None,
                    state_validation_mode=os.getenv('MODEL_ENHANCED_STATE_VALIDATION_MODE', 'strict'),
                )
                if enhanced_result:
                    # LLM Judge 报告
                    if enhanced_result.get('llm_judge_result') and hasattr(enhanced_result['llm_judge_result'], 'report_text'):
                        allure.attach(enhanced_result['llm_judge_result'].report_text, 'LLM Judge 评估报告',
                                     allure.attachment_type.TEXT)

                    # 状态转移验证报告
                    if enhanced_result.get('state_validation_result') and hasattr(enhanced_result['state_validation_result'], 'summary'):
                        allure.attach(enhanced_result['state_validation_result'].summary, '状态转移验证报告',
                                     allure.attachment_type.TEXT)

                    # 信息一致性报告
                    if enhanced_result.get('consistency_result'):
                        allure.attach(str(enhanced_result['consistency_result']),
                                     '信息一致性检查报告', allure.attachment_type.TEXT)

                    # 增强评估报告
                    if enhanced_result.get('report_text'):
                        allure.attach(enhanced_result['report_text'], '多轮增强评估报告',
                                     allure.attachment_type.TEXT)

                    # 可选：将增强评估纳入最终判定
                    if not enhanced_result['enhanced_pass']:
                        final_pass = False
            except Exception as e:
                log.warning(f"【增强评估】执行失败，不影响原有测试：{e}")
                import traceback
                log.warning(traceback.format_exc())
        # ==============================================================================

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
            'overall_pass': overall_pass,
            'failure_reason': '；'.join([row.get('failure_reason') for row in assert_round_rows if row.get('failure_reason')]),
            'response_time': avg_round_response_time,
            'total_response_time': round(sum_round_response_time, 3),
            'round_count': len(round_rows),
            'is_pass': final_pass,
            'output_data': json.dumps(exec_res.get('output_data'), ensure_ascii=False),
            'round_detail': json.dumps(round_rows, ensure_ascii=False)
        }
        with _MODEL_REPORT_ROWS_LOCK:
            MODEL_REPORT_ROWS.append(report_row)
        ModelCaseHandler.save_model_rows([report_row])

        failed_round_rows = [row for row in round_rows if not row.get('round_pass')]
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
                f"响应耗时：{row['response_time']}s",
                f"是否通过：{row.get('round_pass')}"
            ])
        exec_log = build_exec_log(case_info=case_info, msg_info=msg_info, exec_res=exec_res, report_row=report_row, response_time=avg_round_response_time)
        exec_log = exec_log + '\n' + '\n'.join(failure_summary_lines) + '\n' + '\n'.join(round_log_lines)
        actual_dialog_text = build_multi_turn_actual_dialog(round_rows=round_rows)
        assert_dialog_text = build_multi_turn_assert_dialog(round_rows=round_rows)
        eval_body = build_multi_turn_eval_body(round_rows=round_rows, report_row=report_row)
        log.info(f"\n{exec_log}")

        # 使用封装函数挂载 allure 报告（与断言模式联动）
        assert_mode = ModelIntentAssert.get_assert_mode()
        attach_multi_turn_report(round_rows=round_rows, report_row=report_row, case_info=case_info, assert_mode=assert_mode.value)

        allure.attach(actual_dialog_text, '信贷大模型实际话术', allure.attachment_type.TEXT)
        allure.attach(assert_dialog_text, '断言话术', allure.attachment_type.TEXT)
        allure.attach('\n'.join(failure_summary_lines), '多轮失败定位摘要', allure.attachment_type.TEXT)
        allure.attach(eval_body, '模型评估明细CSV', allure.attachment_type.CSV)

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

        # 批量断言模式下，在测试函数中直接执行批量断言（Allure 上下文活跃，可正确挂载附件）
        if os.getenv('MODEL_BATCH_ASSERT', '0') == '1':
            self._run_batch_assert_and_attach()

        assert True

    # ============================================================
    # 原有方法保持不变（信贷场景）
    # ============================================================
    def _run_batch_assert_and_attach(self):
        """
        执行批量断言并将结果挂载到 Allure 报告

        在 test_model_summary_report 中执行（而非 session teardown），
        是因为此时 pytest 的 Allure 上下文仍然活跃，可以正确挂载附件。
        """
        from assert_code.batch_model_assert import BatchModelAssert
        from utils.batch_assert_collector import batch_collector
        from utils.handle_log import log

        # 获取收集的数据（优先从 batch_collector 获取）
        items = batch_collector.get_all()

        # 如果 batch_collector 为空，尝试从持久化文件加载（多进程场景下需要）
        if not items:
            log.info("【批量断言】batch_collector 为空，尝试从持久化文件加载数据...")
            try:
                report_rows = ModelCaseHandler.load_model_rows_from_run()
                # 将 report_rows 转换为 batch_collector 格式
                for row in report_rows:
                    # 多轮数据需要保留 rounds 字段
                    round_detail = row.get('round_detail')
                    rounds = []
                    if round_detail:
                        try:
                            import json
                            rounds = json.loads(round_detail) if isinstance(round_detail, str) else round_detail
                        except Exception:
                            rounds = []
                    items.append({
                        'case_id': row.get('case_id', ''),
                        'case_type': row.get('case_type', ''),
                        'case_desc': row.get('case_desc', ''),
                        'intent': row.get('intent', ''),
                        'question': row.get('question', ''),
                        'actual_answer': row.get('actual_answer', ''),
                        'expected_answer': row.get('expected_answer', ''),
                        'similarity_threshold': row.get('similarity_threshold', 70),
                        'response_time': row.get('response_time', 0),
                        # 本地断言字段（用于批量断言后合并展示）
                        'local_chat_type_pass': row.get('chat_type_pass', True),
                        'local_asset_value_pass': row.get('asset_value_pass', True),
                        'local_biz_ref_id_pass': row.get('biz_ref_id_pass', True),
                        'chat_type': row.get('chat_type', 'NORMAL'),
                        # ASSET 相关字段（用于本地断言展示）
                        'asset_present': row.get('asset_present', False),
                        'asset_value': row.get('asset_value', ''),
                        # 模型返回数据（用于本地断言）
                        'output_data': row.get('output_data'),
                        # 多轮特有字段
                        'rounds': rounds,
                    })
                log.info(f"【批量断言】从持久化文件加载了 {len(items)} 条数据")
            except Exception as e:
                log.warning(f"【批量断言】从持久化文件加载数据失败：{e}")

        if not items:
            allure.attach('无待断言数据', '批量断言状态', allure.attachment_type.TEXT)
            return

        log.info(f"【批量断言】test_model_summary_report 中执行，共 {len(items)} 条数据")

        try:
            # 初始化批量断言器（一次性注入知识库）
            assert_mode = os.getenv('MODEL_ASSERT_MODE', 'intent_checklist')
            batch = BatchModelAssert(
                model_name=os.getenv('MODEL_BATCH_JUDGE_MODEL', 'deepseek-v4-pro'),
                max_group_size=int(os.getenv('MODEL_BATCH_MAX_GROUP_SIZE', '10')),
                max_group_size_multi=int(os.getenv('MODEL_BATCH_MAX_GROUP_SIZE_MULTI', '2')),
                assert_mode=assert_mode,  # 新增：传入断言模式
            )

            # 按 case_type 分组：单轮和多轮分开处理（兼容贷后场景）
            single_turn_items = [item for item in items if TestConfig.is_single_turn(item.get('case_type', ''))]
            multi_turn_items = [item for item in items if TestConfig.is_multi_turn(item.get('case_type', ''))]

            log.info(f"【批量断言】共 {len(items)} 条数据，单轮 {len(single_turn_items)} 条，多轮 {len(multi_turn_items)} 条")

            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'report', 'model_intent_recognition', 'batch_assert')

            # ============================================================
            # 单轮批量断言处理
            # ============================================================
            if single_turn_items:
                log.info(f"【批量断言】开始处理单轮数据：{len(single_turn_items)} 条")

                # 按 chat_type 分组：TRANSFER 的跳过语义评估，NORMAL 的执行外部评分
                transfer_items = [item for item in single_turn_items if item.get('chat_type', '') == 'TRANSFER']
                normal_items = [item for item in single_turn_items if item.get('chat_type', '') != 'TRANSFER']

                # 对 NORMAL 的用例执行外部模型批量评估
                single_results = []
                if normal_items:
                    single_results = batch.batch_evaluate(normal_items)
                    log.info(f"【批量断言】单轮外部模型批量评估完成：{len(single_results)} 条")

                # 对 TRANSFER 的用例直接构造结果（跳过语义评估）
                for item in transfer_items:
                    local_chat_type_pass = item.get('local_chat_type_pass', True)
                    local_asset_value_pass = item.get('local_asset_value_pass', True)
                    local_biz_ref_id_pass = item.get('local_biz_ref_id_pass', True)
                    transfer_is_pass = local_chat_type_pass and local_asset_value_pass and local_biz_ref_id_pass
                    if transfer_is_pass:
                        transfer_reason = "模型已转人工，跳过语义评估（chat_type=TRANSFER，本地断言通过）"
                    else:
                        transfer_reason = f"模型已转人工，跳过语义评估（chat_type=TRANSFER）"
                        if not local_chat_type_pass:
                            transfer_reason += "；转人工未通过"
                        if not local_asset_value_pass:
                            transfer_reason += "；ASSET断言未通过"
                        if not local_biz_ref_id_pass:
                            transfer_reason += "；biz_ref_id断言未通过"
                    single_results.append({
                        'case_id': item['case_id'],
                        'case_type': item.get('case_type', ''),
                        'case_desc': item.get('case_desc', ''),
                        'intent': item.get('intent', ''),
                        'question': item.get('question', ''),
                        'actual_answer': item.get('actual_answer', ''),
                        'expected_answer': item.get('expected_answer', ''),
                        'similarity_score': 0,
                        'similarity_threshold': item.get('similarity_threshold', 70),
                        'is_pass': transfer_is_pass,
                        'reason': transfer_reason,
                        'evaluated': True,
                        'error': None,
                        'local_assert_detail': {
                            'chat_type_pass': local_chat_type_pass,
                            'asset_value_pass': local_asset_value_pass,
                            'biz_ref_id_pass': local_biz_ref_id_pass,
                        }
                    })

                # 合并：本地断言结果 + 批量语义评估结果
                single_items_by_case_id = {item['case_id']: item for item in single_turn_items}
                for result in single_results:
                    case_id = result.get('case_id')
                    if not case_id:
                        continue
                    original = single_items_by_case_id.get(case_id, {})
                    local_chat_type_pass = original.get('local_chat_type_pass', True)
                    local_asset_value_pass = original.get('local_asset_value_pass', True)
                    local_biz_ref_id_pass = original.get('local_biz_ref_id_pass', True)
                    is_transfer = original.get('chat_type', '') == 'TRANSFER'

                    if is_transfer:
                        final_pass = local_chat_type_pass and local_asset_value_pass and local_biz_ref_id_pass
                    else:
                        final_pass = (
                            result.get('is_pass', False) and
                            local_chat_type_pass and
                            local_asset_value_pass and
                            local_biz_ref_id_pass
                        )
                    result['is_pass'] = final_pass

                    if not final_pass:
                        failure_parts = []
                        # 保留外部模型返回的详细原因（失败的用例也需要原因）
                        external_reason = result.get('reason', '')
                        if external_reason:
                            failure_parts.append(f"外部模型评估：{external_reason}")
                        if not is_transfer and not result.get('is_pass', False):
                            failure_parts.append(f"语义相似度未通过（评分：{result.get('similarity_score', 0)}）")
                        if not local_chat_type_pass:
                            failure_parts.append("转人工未通过")
                        if not local_asset_value_pass:
                            failure_parts.append("ASSET断言未通过")
                        if not local_biz_ref_id_pass:
                            failure_parts.append("biz_ref_id断言未通过")
                        if is_transfer:
                            failure_parts.append("模型已转人工，跳过语义评估")
                        result['reason'] = '；'.join(failure_parts)

                    result['local_assert_detail'] = {
                        'chat_type_pass': local_chat_type_pass,
                        'asset_value_pass': local_asset_value_pass,
                        'biz_ref_id_pass': local_biz_ref_id_pass,
                    }

                # 生成单轮报告
                single_summary = batch.generate_report(single_turn_items, single_results, output_dir=output_dir)

                # 挂载单轮汇总信息
                single_summary_text = (
                    f"【单轮批量断言结果】\n"
                    f"总计：{single_summary['total']} 条\n"
                    f"通过：{single_summary['pass_count']} 条\n"
                    f"失败：{single_summary['failed_count']} 条\n"
                    f"通过率：{single_summary['pass_rate']}\n"
                )
                allure.attach(single_summary_text, '单轮批量断言汇总', allure.attachment_type.TEXT)

                # 挂载单轮 HTML 报告
                single_html_path = single_summary.get('html_path')
                if single_html_path and os.path.exists(single_html_path):
                    allure.attach.file(single_html_path, name='单轮批量断言详细报告（HTML）', attachment_type=allure.attachment_type.HTML)
                    log.info(f"【批量断言】单轮 HTML 报告已挂载到 Allure：{single_html_path}")

                # 挂载单轮 CSV 报告
                single_detail_path = single_summary.get('detail_path')
                if single_detail_path and os.path.exists(single_detail_path):
                    allure.attach.file(single_detail_path, name='单轮批量断言详细结果（CSV）', attachment_type=allure.attachment_type.CSV)
                    log.info(f"【批量断言】单轮 CSV 报告已挂载到 Allure：{single_detail_path}")

            # ============================================================
            # 多轮批量断言处理
            # ============================================================
            multi_results = []
            if multi_turn_items:
                log.info(f"【批量断言】开始处理多轮数据：{len(multi_turn_items)} 条")
                multi_results = batch.batch_evaluate(multi_turn_items)
                log.info(f"【批量断言】多轮外部模型批量评估完成：{len(multi_results)} 条")

                # 生成多轮报告
                multi_summary = batch.generate_multi_turn_report(multi_turn_items, multi_results, output_dir=output_dir)

                # 挂载多轮汇总信息
                multi_summary_text = (
                    f"【多轮批量断言结果】\n"
                    f"总计：{multi_summary['total']} 条\n"
                    f"通过：{multi_summary['pass_count']} 条\n"
                    f"失败：{multi_summary['failed_count']} 条\n"
                    f"通过率：{multi_summary['pass_rate']}\n"
                )
                allure.attach(multi_summary_text, '多轮批量断言汇总', allure.attachment_type.TEXT)

                # 挂载多轮 HTML 报告
                multi_html_path = multi_summary.get('html_path')
                if multi_html_path and os.path.exists(multi_html_path):
                    allure.attach.file(multi_html_path, name='多轮批量断言详细报告（HTML）', attachment_type=allure.attachment_type.HTML)
                    log.info(f"【批量断言】多轮 HTML 报告已挂载到 Allure：{multi_html_path}")

                # 挂载多轮 CSV 报告
                multi_detail_path = multi_summary.get('detail_path')
                if multi_detail_path and os.path.exists(multi_detail_path):
                    allure.attach.file(multi_detail_path, name='多轮批量断言详细结果（CSV）', attachment_type=allure.attachment_type.CSV)
                    log.info(f"【批量断言】多轮 CSV 报告已挂载到 Allure：{multi_detail_path}")

            # ============================================================
            # 合并汇总结果
            # ============================================================
            total = (len(single_results) if single_turn_items else 0) + (len(multi_results) if multi_turn_items else 0)
            pass_count = (
                sum(1 for r in single_results if r.get('is_pass')) if single_turn_items else 0
            ) + (
                sum(1 for r in multi_results if r.get('overall_pass')) if multi_turn_items else 0
            )
            fail_count = total - pass_count
            pass_rate = round(pass_count / total * 100, 2) if total else 0

            # 保存批量断言结果到 JSON（供外部读取）
            try:
                import multiprocessing
                import json
                worker_id = multiprocessing.current_process().name.replace('-', '_')
                batch_result_file = os.path.join(output_dir, f'batch_assert_result_{worker_id}.json')
                with open(batch_result_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'total': total,
                        'pass_count': pass_count,
                        'failed_count': fail_count,
                        'pass_rate': f'{pass_rate}%',
                        'single_turn': {
                            'total': len(single_results) if single_turn_items else 0,
                            'pass_count': sum(1 for r in single_results if r.get('is_pass')) if single_turn_items else 0,
                        },
                        'multi_turn': {
                            'total': len(multi_results) if multi_turn_items else 0,
                            'pass_count': sum(1 for r in multi_results if r.get('overall_pass')) if multi_turn_items else 0,
                        },
                    }, f, ensure_ascii=False, indent=2)
                log.info(f"【批量断言】结果已保存到：{batch_result_file}")
            except Exception as e:
                log.warning(f"【批量断言】保存结果到 JSON 失败：{e}")

            # 输出汇总日志
            log.info("=" * 80)
            log.info("【批量断言评估汇总】")
            log.info(f"  总计：{total} 条")
            log.info(f"  通过：{pass_count} 条")
            log.info(f"  失败：{fail_count} 条")
            log.info(f"  通过率：{pass_rate}%")
            if single_turn_items:
                single_pass = sum(1 for r in single_results if r.get('is_pass'))
                log.info(f"  单轮：{len(single_results)} 条，通过 {single_pass} 条")
            if multi_turn_items:
                multi_pass = sum(1 for r in multi_results if r.get('overall_pass'))
                log.info(f"  多轮：{len(multi_results)} 条，通过 {multi_pass} 条")
            log.info("=" * 80)

        except Exception as e:
            log.error(f"【批量断言】批量评估执行失败：{e}")
            import traceback
            log.error(traceback.format_exc())
            allure.attach(f'批量断言执行失败：{e}', '批量断言错误', allure.attachment_type.TEXT)
        finally:
            # 清空收集器
            batch_collector.clear()


def teardown_module():
    """
    模块结束后输出模型评估明细报表
    """
    # 批量断言模式下，汇总报告已在 test_model_summary_report 中挂载，避免重复
    if os.getenv('MODEL_BATCH_ASSERT', '0') == '1':
        return

    report_rows = ModelCaseHandler.load_model_rows_from_run() or MODEL_REPORT_ROWS
    if not report_rows:
        return

    attach_model_report(report_rows=report_rows)
