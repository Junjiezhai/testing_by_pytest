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
import sys
import time

Base_Path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(Base_Path)

import allure
import pytest

from assert_code.model_intent_assert import ModelIntentAssert
from script_code.model_intent_recogntion_exec import ModelIntentRecognition
from utils.handle_log import log
from utils.handle_model_cases import assemble_model_case_params, get_model_case_desc, ModelCaseHandler


MODEL_REPORT_ROWS = []


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
    failed_cases = [f"{row.get('case_id')} | {row.get('case_desc')} | 相似度={row.get('similarity_score')}" for row in report_rows if row.get('is_pass') is False]

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


def build_multi_turn_eval_body(round_rows: list, report_row: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'case_id', 'case_type', 'case_desc', 'intent', 'round', 'question', 'expected_answer',
        'actual_answer', 'response_time', 'similarity_score', 'similarity_pass',
        'case_avg_score', 'similarity_threshold', 'case_result'
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
            'actual_answer': row['actual_answer'],
            'response_time': row['response_time'],
            'similarity_score': row['similarity_score'],
            'similarity_pass': row['similarity_pass'],
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
        f"【用户问题】：{case_info['question']}",
        f"【标准话术】：{case_info['expected_answer']}",
        f"【模型请求msg_info】：{json.dumps(msg_info, ensure_ascii=False)}",
        f"【模型请求request_data】：{json.dumps(exec_res.get('request_data'), ensure_ascii=False)}",
        f"【模型完整返回】：{json.dumps(exec_res.get('output_data'), ensure_ascii=False)}",
        f"【模型有效出参value】：{report_row['actual_answer']}",
        f"【外部模型相似度评分】：{report_row['similarity_score']}",
        f"【外部模型评估原因】：{report_row['similarity_reason']}",
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
            'uid': '4089534',
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

        exec_log = build_exec_log(case_info=case_info, msg_info=msg_info, exec_res=exec_res, report_row=report_row, response_time=response_time)
        log.info(f"\n{exec_log}")
        allure.attach(json.dumps(case_info, ensure_ascii=False, indent=2), '用例信息', allure.attachment_type.JSON)
        allure.attach(exec_log, '执行日志', allure.attachment_type.TEXT)
        allure.attach(json.dumps(exec_res.get('request_data'), ensure_ascii=False, indent=2), '信贷大模型请求入参', allure.attachment_type.JSON)
        allure.attach(json.dumps(exec_res.get('output_data'), ensure_ascii=False, indent=2), '信贷大模型完整返回', allure.attachment_type.JSON)
        allure.attach(json.dumps(report_row, ensure_ascii=False, indent=2), '模型评估明细', allure.attachment_type.JSON)
        allure.attach(report_row['actual_answer'], '信贷大模型实际话术', allure.attachment_type.TEXT)
        allure.attach(report_row['expected_answer'], '标准话术', allure.attachment_type.TEXT)

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
        allure.dynamic.parent_suite('多轮对话上下文连贯性')
        allure.dynamic.suite(case_info['intent'])
        allure.dynamic.label('intent', case_info['intent'])

        log.info(f"\n==============【当前环境：env={case_info['env']}, group={case_info['group']}】信贷大模型多轮测试 =============\n")
        model = ModelIntentRecognition(env=case_info['env'], group=case_info['group'])
        questions = case_info['questions']
        expected_answers = case_info['expected_answers']
        msg_context_list = []
        round_rows = []
        total_response_time = 0
        exec_res = None
        msg_info = None
        chat_id = f"chat_{case_info['env']}_{case_info['case_id']}_{int(time.time() * 1000000)}"

        for i, question in enumerate(questions):
            msg_context_list.append(ModelCaseHandler.build_customer_msg(content=question, index=i * 2))
            msg_info = {
                'uid': '4089534',
                'content': question,
                'chatId': chat_id,
                'msgContextList': msg_context_list
            }

            start_time = time.time()
            exec_res = model.send_msg_to_model(msg_info=msg_info)
            round_response_time = time.time() - start_time
            total_response_time += round_response_time
            actual_answer = ModelIntentAssert.extract_model_answer(output_data=exec_res.get('output_data'))
            expected_answer = expected_answers[i]
            should_assert = case_info['round_assert_flags'][i]
            round_eval = ModelIntentAssert.evaluate_answer(
                actual_answer=actual_answer,
                expected_answer=expected_answer,
                similarity_threshold=case_info['similarity_threshold']
            ) if should_assert else {
                'similarity_score': 100,
                'similarity_pass': True,
                'similarity_reason': '当前轮次配置为不参与断言'
            }
            msg_context_list.append(ModelCaseHandler.build_staff_msg(content=actual_answer, index=i * 2 + 1))

            round_row = {
                'round': i + 1,
                'question': question,
                'expected_answer': expected_answer,
                'actual_answer': actual_answer,
                'similarity_score': round_eval['similarity_score'],
                'similarity_pass': round_eval['similarity_pass'],
                'similarity_reason': round_eval['similarity_reason'],
                'should_assert': should_assert,
                'response_time': round(round_response_time, 3),
                'request_data': exec_res.get('request_data'),
                'output_data': exec_res.get('output_data')
            }
            round_rows.append(round_row)
            log.info(f"【多轮第{i + 1}轮】用户问题：{question}，模型回复：{actual_answer}，相似度：{round_eval['similarity_score']}，耗时：{round(round_response_time, 3)}s")

        assert_round_rows = [row for row in round_rows if row['should_assert']]
        avg_similarity_score = round(sum([row['similarity_score'] for row in assert_round_rows]) / len(assert_round_rows), 2) if assert_round_rows else 100
        similarity_pass = avg_similarity_score >= case_info['similarity_threshold']
        report_row = {
            'case_id': case_info['case_id'],
            'case_type': case_info['case_type'],
            'case_desc': case_info['case_desc'],
            'intent': case_info['intent'],
            'actual_intent': '',
            'question': case_info['question'],
            'expected_answer': case_info['expected_answer'],
            'actual_answer': round_rows[-1]['actual_answer'],
            'is_same_meaning': similarity_pass,
            'similarity_score': avg_similarity_score,
            'similarity_reason': f"多轮逐轮平均相似度：{avg_similarity_score}",
            'similarity_threshold': case_info['similarity_threshold'],
            'similarity_pass': similarity_pass,
            'response_time': round(total_response_time, 3),
            'is_pass': similarity_pass,
            'output_data': json.dumps(exec_res.get('output_data'), ensure_ascii=False),
            'round_detail': json.dumps(round_rows, ensure_ascii=False)
        }
        MODEL_REPORT_ROWS.append(report_row)

        round_log_lines = ['【多轮逐轮评分明细】：']
        for row in round_rows:
            round_log_lines.extend([
                f"------ 第{row['round']}轮 ------",
                f"用户问题：{row['question']}",
                f"标准话术：{row['expected_answer']}",
                f"模型回复：{row['actual_answer']}",
                f"相似度评分：{row['similarity_score']}",
                f"评分原因：{row['similarity_reason']}",
                f"是否断言：{row['should_assert']}",
                f"响应耗时：{row['response_time']}s",
                f"是否通过：{row['similarity_pass']}"
            ])
        exec_log = build_exec_log(case_info=case_info, msg_info=msg_info, exec_res=exec_res, report_row=report_row, response_time=total_response_time)
        exec_log = exec_log + '\n' + '\n'.join(round_log_lines)
        eval_body = build_multi_turn_eval_body(round_rows=round_rows, report_row=report_row)
        log.info(f"\n{exec_log}")
        allure.attach(eval_body, '模型评估明细CSV', allure.attachment_type.CSV)

        ModelIntentAssert.assert_model_result(report_row=report_row)

    @allure.story('模型测试汇总报告')
    @pytest.mark.model_summary
    def test_model_summary_report(self) -> None:
        """
        【信贷大模型--汇总报告】
        :return: None
        """
        attach_model_report(report_rows=MODEL_REPORT_ROWS)
        assert True


def teardown_module():
    """
    模块结束后输出模型评估明细报表
    :return:
    """
    if not MODEL_REPORT_ROWS:
        return

    attach_model_report(report_rows=MODEL_REPORT_ROWS)
