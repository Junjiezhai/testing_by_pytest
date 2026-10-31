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


@allure.feature('贷后催收大模型')
@pytest.mark.model_intent_recognition
class TestPostloan:
    # ============================================================
    # 贷后催收场景测试（新增，与信贷场景完全独立）
    # ============================================================

    @allure.story('贷后催收-单轮意图识别与话术应答')
    @pytest.mark.postloan_single_turn
    @pytest.mark.parametrize(*(assemble_postloan_case_params(case_type='single_turn')),
                             ids=get_postloan_case_desc(case_type='single_turn'))
    def test_postloan_single_turn_intent_recognition(self, case_info: dict) -> None:
        """
        【贷后催收大模型--单轮意图识别与话术应答】
        :param case_info: 用例信息
        :return: None
        """
        if not case_info:
            pytest.skip('当前未配置 postloan_single_turn 类型用例')
        allure.dynamic.parent_suite('贷后催收-单轮意图识别与话术应答')
        allure.dynamic.suite(case_info['intent'])
        allure.dynamic.label('intent', case_info['intent'])

        log.info(
            f"\n==============【当前环境：env={case_info['env']}, "
            f"group={case_info['group']}】贷后催收大模型单轮测试 =============\n"
        )

        # 复用现有模型调用（接口通用）
        model = ModelIntentRecognition(env=case_info['env'], group=case_info['group'])
        msg_info = {
            'uid': get_random_uid('postloan'),
            'biz_scene_key': "BSK2606161609440188",
            'content': case_info['question']
        }

        start_time = time.time()
        exec_res = model.send_msg_to_model(msg_info=msg_info)
        response_time = time.time() - start_time

        # 检测批量断言模式
        if os.getenv('MODEL_BATCH_ASSERT', '0') == '1':
            # 批量模式：只做本地断言（意图识别 + chatType + ASSET + 合规性）
            actual_answer = PostloanIntentAssert.extract_model_answer(output_data=exec_res.get('output_data'))
            actual_intent = PostloanIntentAssert.extract_model_intent(output_data=exec_res.get('output_data'))
            reply_info = PostloanIntentAssert._extract_reply_contents(output_data=exec_res.get('output_data'))
            intent_check = PostloanIntentAssert._check_postloan_intent(case_info['intent'], exec_res.get('output_data'))
            chat_type_eval = PostloanIntentAssert._evaluate_chat_type_result(case_info['intent'], reply_info)

            # 综合判定
            local_chat_type_pass = chat_type_eval['chat_type_pass']
            local_intent_pass = intent_check['is_match']

            # 转人工用例：跳过ASSET、biz_ref_id、合规性断言，只要chatType=TRANSFER即通过
            if chat_type_eval['chat_type'] == 'TRANSFER':
                local_asset_value_pass = True
                local_biz_ref_id_pass = True
                local_compliance_pass = True
                is_pass = local_chat_type_pass and local_intent_pass
                # 收集失败原因（仅收集意图和chat_type）
                fail_reasons = []
                if not local_intent_pass:
                    fail_reasons.append(intent_check['failure_reason'])
                if not local_chat_type_pass:
                    fail_reasons.extend(chat_type_eval['chat_type_failure_reasons'])
                # 构造报告（转人工用例跳过ASSET和合规性相关字段）
                report_row = {
                    'case_id': case_info['case_id'],
                    'case_type': TestConfig.CASE_TYPE_POSTLOAN_SINGLE_TURN,
                    'case_desc': case_info['case_desc'],
                    'intent': case_info['intent'],
                    'actual_intent': actual_intent,
                    'question': case_info['question'],
                    'expected_answer': case_info['expected_answer'],
                    'actual_answer': actual_answer,
                    'chat_type': chat_type_eval['chat_type'],
                    'chat_type_pass': local_chat_type_pass,
                    'postloan_intent_match': intent_check,
                    'asset_present': False,
                    'asset_allowed': False,
                    'asset_value': '',
                    'asset_value_pass': True,
                    'biz_ref_id': '',
                    'biz_ref_id_pass': True,
                    'is_pass': is_pass,
                    'fail_reasons': fail_reasons,
                    'failure_reason': '；'.join(fail_reasons) if fail_reasons else '',
                    'similarity_score': 0,
                    'similarity_reason': '批量断言模式：转人工用例跳过语义评估',
                    'similarity_threshold': case_info['similarity_threshold'],
                    'response_time': round(response_time, 3),
                    # 保存模型返回数据（用于批量断言阶段重新计算本地断言）
                    'output_data': exec_res.get('output_data') if exec_res.get('output_data') else None,
                }
            else:
                compliance_check = PostloanIntentAssert._check_postloan_compliance(case_info['intent'], actual_answer)
                asset_eval = PostloanIntentAssert.evaluate_asset_result(case_info['intent'], reply_info)
                local_asset_value_pass = asset_eval['asset_value_pass']
                local_biz_ref_id_pass = asset_eval['biz_ref_id_pass']
                local_compliance_pass = compliance_check['is_pass']
                is_pass = (
                    local_chat_type_pass and
                    local_asset_value_pass and
                    local_biz_ref_id_pass and
                    local_compliance_pass and
                    local_intent_pass
                )
                # 收集失败原因
                fail_reasons = []
                if not local_intent_pass:
                    fail_reasons.append(intent_check['failure_reason'])
                if not local_chat_type_pass:
                    fail_reasons.extend(chat_type_eval['chat_type_failure_reasons'])
                if not local_asset_value_pass:
                    fail_reasons.extend(asset_eval['asset_failure_reasons'])
                if not local_biz_ref_id_pass:
                    fail_reasons.append(f"biz_ref_id 断言未通过")
                if not local_compliance_pass:
                    fail_reasons.extend(compliance_check['failure_reasons'])
                # 构造报告
                report_row = {
                    'case_id': case_info['case_id'],
                    'case_type': TestConfig.CASE_TYPE_POSTLOAN_SINGLE_TURN,
                    'case_desc': case_info['case_desc'],
                    'intent': case_info['intent'],
                    'actual_intent': actual_intent,
                    'question': case_info['question'],
                    'expected_answer': case_info['expected_answer'],
                    'actual_answer': actual_answer,
                    'chat_type': chat_type_eval['chat_type'],
                    'chat_type_pass': local_chat_type_pass,
                    'postloan_intent_match': intent_check,
                    'postloan_compliance_check': compliance_check,
                    'asset_present': asset_eval['asset_present'],
                    'asset_allowed': asset_eval['asset_allowed'],
                    'asset_value': asset_eval['asset_value'],
                    'asset_value_pass': local_asset_value_pass,
                    'biz_ref_id': asset_eval['biz_ref_id'],
                    'biz_ref_id_pass': local_biz_ref_id_pass,
                    'is_pass': is_pass,
                    'fail_reasons': fail_reasons,
                    'failure_reason': '；'.join(fail_reasons) if fail_reasons else '',
                    'similarity_score': 0,
                    'similarity_reason': '批量断言模式：详细评估结果将在测试结束后批量生成',
                    'similarity_threshold': case_info['similarity_threshold'],
                    'response_time': round(response_time, 3),
                    # 保存模型返回数据（用于批量断言阶段重新计算本地断言）
                    'output_data': exec_res.get('output_data') if exec_res.get('output_data') else None,
                }

            # 保存报告数据
            ModelCaseHandler.save_model_rows([report_row])
            log.info(
                f"【批量断言-贷后】已收集数据：case_id={case_info['case_id']}, "
                f"intent={case_info['intent']}"
            )

            # Allure 基础挂载
            allure.attach(actual_answer, '贷后大模型实际话术', allure.attachment_type.TEXT)
            allure.attach(case_info['expected_answer'], '断言话术', allure.attachment_type.TEXT)
            if exec_res.get('output_data'):
                allure.attach(
                    json.dumps(exec_res.get('output_data'), ensure_ascii=False, indent=2),
                    '贷后大模型完整返参',
                    allure.attachment_type.JSON,
                )
            allure.attach(
                '当前为批量断言模式，详细评估结果将在测试结束后批量生成',
                '批量断言提示',
                allure.attachment_type.TEXT,
            )

            # 本地简单断言
            assert actual_answer, f"贷后模型返回为空：case_id={case_info['case_id']}"
            return

        # 非批量模式：使用贷后专用断言（完整评估）
        report_row = PostloanIntentAssert.evaluate_postloan_single_turn(
            case_info=case_info,
            output_data=exec_res.get('output_data'),
            response_time=response_time,
            assert_mode=PostloanIntentAssert.get_assert_mode(),
        )

        with _MODEL_REPORT_ROWS_LOCK:
            MODEL_REPORT_ROWS.append(report_row)
        ModelCaseHandler.save_model_rows([report_row])

        # 构造执行日志
        exec_log = (
            f"==============【贷后催收】当前环境：env={case_info['env']}, "
            f"group={case_info['group']} ==============\n"
            f"【用例编号】：{case_info['case_id']}\n"
            f"【测试场景】：{case_info['case_desc']}\n"
            f"【意图分类】：{case_info['intent']}\n"
            f"【实际意图】：{report_row.get('actual_intent', '')}\n"
            f"【用户问题】：{case_info['question']}\n"
            f"【标准答案】：{case_info['expected_answer']}\n"
            f"【实际答案】：{report_row.get('actual_answer', '')}\n"
            f"【意图匹配】：{report_row.get('postloan_intent_match', {})}\n"
            f"【合规检查】：{report_row.get('postloan_compliance_check', {})}\n"
            f"【相似度】：{report_row.get('similarity_score')}，"
            f"阈值={report_row.get('similarity_threshold')}，"
            f"结果={report_row.get('similarity_pass')}\n"
            f"【失败原因】：{report_row.get('failure_reason')}\n"
            f"【响应耗时】：{round(response_time, 3)}s\n"
            f"【最终结果】：{report_row['is_pass']}"
        )
        log.info(f"\n{exec_log}")

        # 挂载 Allure 报告
        allure.attach(report_row['actual_answer'], '贷后大模型实际话术', allure.attachment_type.TEXT)
        allure.attach(case_info['expected_answer'], '断言话术', allure.attachment_type.TEXT)
        if exec_res.get('output_data'):
            allure.attach(
                json.dumps(exec_res.get('output_data'), ensure_ascii=False, indent=2),
                '贷后大模型完整返参',
                allure.attachment_type.JSON,
            )

        # 挂载贷后特有报告信息
        intent_match = report_row.get('postloan_intent_match', {})
        compliance_check = report_row.get('postloan_compliance_check', {})
        allure.attach(
            json.dumps(intent_match, ensure_ascii=False, indent=2),
            '贷后意图识别匹配结果',
            allure.attachment_type.JSON,
        )
        allure.attach(
            json.dumps(compliance_check, ensure_ascii=False, indent=2),
            '贷后话术合规性检查结果',
            allure.attachment_type.JSON,
        )

        # 最终断言
        PostloanIntentAssert.assert_model_result(report_row=report_row)

    # ============================================================
    # 贷后催收-多轮对话上下文连贯性（新增，完全独立）
    # ============================================================

    @allure.story('贷后催收-多轮对话上下文连贯性')
    @pytest.mark.postloan_multi_turn
    @pytest.mark.parametrize(*(assemble_postloan_case_params(case_type='multi_turn')),
                             ids=get_postloan_case_desc(case_type='multi_turn'))
    def test_postloan_multi_turn_dialog_consistency(self, case_info: dict) -> None:
        """
        【贷后催收大模型--多轮对话上下文连贯性】
        :param case_info: 用例信息
        :return: None
        """
        if not case_info:
            pytest.skip('当前未配置 postloan_multi_turn 类型用例')
        remark_suite = case_info.get('remark') or case_info.get('case_type') or '未分类'
        allure.dynamic.parent_suite('贷后催收-多轮对话')
        allure.dynamic.suite(remark_suite)
        allure.dynamic.sub_suite(case_info['intent'])
        allure.dynamic.label('remark', remark_suite)
        allure.dynamic.label('intent', case_info['intent'])

        log.info(
            f"\n==============【当前环境：env={case_info['env']}, "
            f"group={case_info['group']}】贷后催收大模型多轮测试 =============\n"
        )

        # 复用现有模型调用（接口通用）
        model = ModelIntentRecognition(env=case_info['env'], group=case_info['group'])
        questions = case_info['questions']
        expected_answers = case_info['expected_answers']
        reference_answers = case_info.get('reference_answers') or expected_answers
        round_intents = case_info.get('round_intents') or [case_info['intent'] for _ in questions]
        previous_intents = case_info.get('previous_intents') or ['' if i == 0 else round_intents[i - 1] for i in range(len(questions))]
        context_assert_types = case_info.get('context_assert_types') or ['normal' for _ in questions]
        enriched_rounds = case_info.get('enriched_rounds') or []
        msg_context_list = []
        round_rows = []
        sum_round_response_time = 0
        exec_res = None
        msg_info = None
        chat_id = f"postloan_chat_{case_info['env']}_{case_info['case_id']}_{int(time.time() * 1000000)}"
        uid = get_random_uid('postloan')

        is_batch_mode = os.getenv('MODEL_BATCH_ASSERT', '0') == '1'

        for i, question in enumerate(questions):
            msg_context_list.append(ModelCaseHandler.build_customer_msg(content=question, index=i * 2))
            msg_info = {
                'uid': uid,
                'content': question,
                'chatId': chat_id,
                'msgContextList': msg_context_list,
                'biz_scene_key': case_info.get('biz_scene_key', 'BSK2606161609440188'),
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
                'request_data': exec_res.get('request_data'),
            }
            if is_batch_mode:
                # 批量模式：只做本地断言（提取回复、chatType、ASSET + 催收合规），跳过外部模型
                reply_info = ModelIntentAssert._extract_reply_contents(output_data=exec_res.get('output_data'))
                chat_type_eval = ModelIntentAssert._evaluate_chat_type_result(round_info['round_intent'], reply_info)
                asset_eval = ModelIntentAssert.evaluate_asset_result(round_info['round_intent'], reply_info)
                # 贷后新增：催收合规性检查
                from assert_code.postloan_multi_turn_assert import check_collection_compliance
                compliance_result = check_collection_compliance(actual_answer)
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
                    'compliance_pass': compliance_result['is_pass'],
                    'compliance_reason': compliance_result['detail'],
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
                # 非批量模式：正常执行逐轮评估
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
                'compliance_pass': round_eval.get('compliance_pass', True),
                'compliance_reason': round_eval.get('compliance_reason', ''),
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
            log.info(f"【贷后多轮第{i + 1}轮】用户问题：{question}，模型回复：{actual_answer}，意图：{round_eval.get('actual_intent')}，耗时：{round(round_response_time, 3)}s")

        # 检测批量断言模式
        if is_batch_mode:
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
                'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'similarity_threshold': case_info['similarity_threshold'],
                'rounds': multi_turn_rounds,
                'last_output_data': exec_res.get('output_data'),
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
            log.info(f"【批量断言-贷后多轮】已收集数据：case_id={case_info['case_id']}, 共 {len(multi_turn_rounds)} 轮")
            assert round_rows, f"贷后多轮测试无数据：case_id={case_info['case_id']}"
            # 挂载 Allure 基础信息
            round_detail_lines = []
            for round_row in round_rows:
                round_detail_lines.append(f"{'=' * 60}")
                round_detail_lines.append(f"【第{round_row['round']}轮】")
                round_detail_lines.append(f"用户问题：{round_row['question']}")
                round_detail_lines.append(f"模型回复：{round_row['actual_answer']}")
                round_detail_lines.append(f"标准答案：{round_row['expected_answer']}")
                round_detail_lines.append(f"响应耗时：{round_row['response_time']}s")
                request_data = round_row.get('request_data')
                if request_data:
                    round_detail_lines.append(f"\n【请求入参】")
                    try:
                        import json
                        round_detail_lines.append(json.dumps(request_data, ensure_ascii=False, indent=2))
                    except Exception:
                        round_detail_lines.append(str(request_data))
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
                '贷后多轮逐轮请求入参与模型回复详情',
                allure.attachment_type.TEXT,
            )
            allure.attach('当前为批量断言模式，详细评估结果将在测试结束后批量生成', '批量断言提示', allure.attachment_type.TEXT)

            # 保存完整报告数据到持久化文件（用于后续 Allure 报告和企微通知统计）
            avg_round_response_time = round(sum_round_response_time / len(round_rows), 3) if round_rows else 0
            report_row = {
                'case_id': case_info['case_id'],
                'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
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
                'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
                'case_desc': case_info['case_desc'],
                'intent': case_info['intent'],
                'similarity_threshold': case_info['similarity_threshold'],
                'rounds': multi_turn_rounds,
                'last_output_data': round_rows[-1].get('output_data'),
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

            # 调用 PostloanMultiTurnEvaluator 进行一次性评估
            from assert_code.postloan_multi_turn_assert import PostloanMultiTurnEvaluator
            from assert_code.external_model_judge import ExternalModelJudge
            judge = ExternalModelJudge(
                model_name=os.getenv('MODEL_BATCH_JUDGE_MODEL', 'deepseek-v4-pro'),
                use_knowledge_base=False,
            )
            result = PostloanMultiTurnEvaluator.evaluate_single(case_data, judge)

            # 更新 round_rows（将评估结果分配到最后一轮）
            if round_rows:
                last_row = round_rows[-1]
                last_row['similarity_score'] = result.get('overall_score', 0)
                last_row['similarity_pass'] = result.get('overall_pass', False)
                last_row['similarity_reason'] = result.get('failure_reason', '')
                last_row['round_pass'] = result.get('overall_pass', False)
                last_row['failure_reason'] = result.get('failure_reason', '')
                last_row['chat_type_pass'] = result.get('transfer_pass', True)
                last_row['asset_pass'] = result.get('asset_pass', True)
                last_row['compliance_pass'] = result.get('compliance_pass', True)

            log.info(f"【贷后多轮一次性评估】case_id={case_info['case_id']}, overall_score={result.get('overall_score')}, overall_pass={result.get('overall_pass')}")

        assert round_rows, f"贷后多轮测试无数据：case_id={case_info['case_id']}"
        avg_round_response_time = round(sum_round_response_time / len(round_rows), 3) if round_rows else 0
        overall_pass = round_rows[-1]['round_pass'] if round_rows else True
        avg_similarity_score = round(sum([row['similarity_score'] for row in round_rows]) / len(round_rows), 2) if round_rows else 100
        similarity_pass = avg_similarity_score >= case_info['similarity_threshold']
        final_pass = similarity_pass and overall_pass

        report_row = {
            'case_id': case_info['case_id'],
            'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
            'case_desc': case_info['case_desc'],
            'remark': case_info.get('remark'),
            'intent': case_info['intent'],
            'actual_intent': '',
            'question': case_info['question'],
            'expected_answer': case_info['expected_answer'],
            'actual_answer': round_rows[-1]['actual_answer'],
            'is_same_meaning': final_pass,
            'similarity_score': avg_similarity_score,
            'similarity_reason': f"贷后多轮逐轮平均相似度：{avg_similarity_score}",
            'similarity_threshold': case_info['similarity_threshold'],
            'similarity_pass': similarity_pass,
            'overall_pass': overall_pass,
            'failure_reason': '；'.join([row.get('failure_reason') for row in round_rows if row.get('failure_reason')]),
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

        # 挂载 Allure 报告
        actual_dialog_lines = []
        expected_dialog_lines = []
        for round_row in round_rows:
            actual_dialog_lines.append(f"第{round_row['round']}轮")
            actual_dialog_lines.append(f"  用户：{round_row['question']}")
            actual_dialog_lines.append(f"  模型：{round_row['actual_answer']}")
            expected_dialog_lines.append(f"第{round_row['round']}轮")
            expected_dialog_lines.append(f"  用户：{round_row['question']}")
            expected_dialog_lines.append(f"  标准：{round_row['expected_answer']}")

        allure.attach('\n'.join(actual_dialog_lines), '贷后多轮真实对话', allure.attachment_type.TEXT)
        allure.attach('\n'.join(expected_dialog_lines), '贷后多轮标准话术', allure.attachment_type.TEXT)
        allure.attach(str(report_row), '贷后多轮评估结果', allure.attachment_type.TEXT)

    # ============================================================
    # 贷后催收-测试汇总报告
    # ============================================================
    @pytest.mark.postloan_summary
    def test_postloan_summary_report(self) -> None:
        """
        【贷后催收大模型--汇总报告】
        :return: None
        """
        # 筛选贷后相关报告行（单轮 + 多轮）
        all_report_rows = ModelCaseHandler.load_model_rows_from_run() or MODEL_REPORT_ROWS
        postloan_rows = [row for row in all_report_rows
                         if row.get('case_type', '').startswith('postloan')]

        # 挂载贷后汇总报告（兼容非批量模式）
        attach_model_report(report_rows=postloan_rows)

        if postloan_rows:
            # 批量断言模式下，汇总报告已在 _run_batch_assert_and_attach 中挂载，避免重复
            if os.getenv('MODEL_BATCH_ASSERT', '0') != '1':
                single_turn_rows = [r for r in postloan_rows if TestConfig.is_single_turn(r.get('case_type', ''))]
                multi_turn_rows = [r for r in postloan_rows if TestConfig.is_multi_turn(r.get('case_type', ''))]
                summary_parts = [
                    f"贷后催收测试汇总：\n",
                    f"  总用例数：{len(postloan_rows)}\n",
                    f"  通过数：{sum(1 for r in postloan_rows if r.get('is_pass'))}\n",
                    f"  失败数：{sum(1 for r in postloan_rows if not r.get('is_pass'))}\n",
                ]
                if single_turn_rows:
                    summary_parts.append(f"  单轮：{len(single_turn_rows)} 条，通过 {sum(1 for r in single_turn_rows if r.get('is_pass'))} 条\n")
                if multi_turn_rows:
                    summary_parts.append(f"  多轮：{len(multi_turn_rows)} 条，通过 {sum(1 for r in multi_turn_rows if r.get('is_pass'))} 条\n")
                summary = ''.join(summary_parts)
                allure.attach(summary, '贷后催收测试汇总', allure.attachment_type.TEXT)
        else:
            allure.attach('当前无贷后测试数据', '贷后催收测试汇总', allure.attachment_type.TEXT)

        # 批量断言模式下，执行批量评估
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
