# -*- coding: utf-8 -*-
"""
# @File    : debug_model_by_pytest.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
# @Description : 信贷大模型 pytest 调试入口文件

使用方式：
在 main 函数中直接修改调试参数，然后在 IDE 内直接运行本文件。
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.handle_allure_report import build_allure_run_dirs, generate_allure_report, get_case_count, open_allure_report, report_summary
from utils.handle_log import log
from utils.handle_yaml import get_test_config, update_test_config


from utils.handle_model_cases import ModelCaseHandler


MODEL_WEHOOK_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=33b27e52-f5ab-4690-a62c-e8d1e3ce1a67'
TEST_FILE = './test_cases/test_model_intent_recognition.py'


def send_start_notice(wehook_url=MODEL_WEHOOK_URL):
    """
    测试执行前发送企微通知
    """
    content_text = (
        "执行自动化测试中，请勿发版，如果必须发版，请通知jeremyzhai !!!@joelwu(吴荣洲) @haganzhou(周汉耿)\n"
        f"操作人：jeremyzhai\n"
        f"操作时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    content = {
        "msgtype": "text",
        "text": {
            "content": content_text,
        }
    }
    try:
        response = requests.post(wehook_url, json=content, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get('errcode') != 0:
            log.error(f"企微通知发送失败：{result}")
            return False
        log.info("企微通知发送成功")
        return True
    except Exception as e:
        log.error(f"企微通知发送异常：{e}")
        return False


def load_latest_model_summary():
    """读取本轮汇总结果"""
    run_dir = ModelCaseHandler.get_current_run_dir()
    latest_summary_path = os.path.join(run_dir, 'latest_summary_path.txt')
    if os.path.exists(latest_summary_path):
        with open(latest_summary_path, encoding='utf-8') as f:
            summary_file = f.read().strip()
        if summary_file and os.path.exists(summary_file):
            with open(summary_file, encoding='utf-8') as f:
                summary = json.load(f)
            return summary[0] if summary else None
    return None


def report_model_summary(num_successd, num_failed, allure_report_url, env=None, group=None, elapsed_minutes=0.0):
    model_summary = load_latest_model_summary()
    extra_lines = []
    if model_summary:
        failure_dimensions = model_summary.get('多轮失败维度统计') or {}
        extra_lines.extend([
            '类型 | 通过用例数 | 失败用例数 | 总用例数 | 通过率',
            f"单轮 | {model_summary.get('单轮通过数', 0)} | {model_summary.get('单轮失败数', 0)} | {model_summary.get('单轮用例数', 0)} | {model_summary.get('单轮通过率', 0)}%",
            f"多轮 | {model_summary.get('多轮通过数', 0)} | {model_summary.get('多轮失败数', 0)} | {model_summary.get('多轮用例数', 0)} | {model_summary.get('多轮通过率', 0)}%",
            '耗时 | 平均 | P90 | P95 | 最大',
            f"响应 | {model_summary.get('平均响应耗时', 0)}s | {model_summary.get('P90响应耗时', 0)}s | {model_summary.get('P95响应耗时', 0)}s | {model_summary.get('最大响应耗时', 0)}s",
            f"多轮失败维度统计：{failure_dimensions if failure_dimensions else '无'}"
        ])
    report_summary(
        num_successd,
        num_failed,
        allure_report_url,
        env,
        group,
        wehook_url=MODEL_WEHOOK_URL,
        extra_content='\n'.join(extra_lines),
        elapsed_minutes=elapsed_minutes
    )


def set_test_config(env='pre', group='default'):
    if env or group:
        log.info('正在更新配置文件...')
        log.info(f"  env: {env if env else '(保持不变)'}")
        log.info(f"  group: {group if group else '(保持不变)'}")
        update_test_config(env=env, group=group)
    return get_test_config()


def build_pytest_args(case_type: str, keyword: str = None, parallel_workers: int = 5):
    keyword_map = {
        'single_turn': 'test_single_turn_intent_recognition',
        'multi_turn': 'test_multi_turn_dialog_consistency',
        'summary': 'test_model_summary_report'
    }
    selected_keyword = keyword or keyword_map.get(case_type)
    pytest_args = [TEST_FILE]
    if selected_keyword:
        pytest_args.extend(['-k', selected_keyword])
    pytest_args.extend(['-n', str(parallel_workers)])
    pytest_args.extend(['-s'])
    return pytest_args


def main():
    # ========================================================================
    # 【IDE 调试参数：直接改这里】
    # ========================================================================
    env = 'pre'
    group = 'default'

    # 可选值：'single_turn'、'multi_turn'、'summary'、'all'
    case_type = 'all'

    # pytest-xdist 并发工作进程数；IDE 调试建议设为 1，避免并行断点混乱
    parallel_workers = 3

    # None 表示全部；调试时建议先跑 1 条
    single_turn_limit = None
    multi_turn_limit = None

    # 可选：指定 pytest -k 过滤，例如 'MIR_0001'
    # 不需要指定时保持 None，会根据 case_type 自动选择单轮/多轮测试函数
    keyword = None

    # 是否在测试结束后启动 allure serve；IDE 调试建议 False，避免进程阻塞
    serve_allure = False

    # 多轮断言安全阀：
    # 1. 是否启用意图断言
    enable_intent_assert = True
    # 2. 是否启用上下文断言
    enable_context_assert = True
    # 3. 是否启用风险拒答断言
    enable_risk_assert = True
    # 4. 是否启用 ASSET 断言
    enable_asset_assert = True
    # 5. 是否要求所有参与断言轮次都通过，而不是只看平均分
    require_all_assert_rounds_pass = True
    # 6. 是否要求最后一轮必须通过
    require_last_round_pass = True
    # ========================================================================

    import pytest

    os.environ['PYTHONIOENCODING'] = 'utf-8'

    start_time = time.time()

    log.info('=' * 80)
    log.info('信贷大模型 pytest 调试执行器')
    log.info('=' * 80)

    config = set_test_config(env, group)
    run_id = datetime.now().strftime('%Y%m%d%H%M%S')
    os.environ['MODEL_REPORT_RUN_ID'] = run_id

    os.environ['MODEL_SINGLE_TURN_LIMIT'] = 'None' if single_turn_limit is None else str(single_turn_limit)
    os.environ['MODEL_MULTI_TURN_LIMIT'] = 'None' if multi_turn_limit is None else str(multi_turn_limit)
    os.environ['MODEL_ENABLE_INTENT_ASSERT'] = '1' if enable_intent_assert else '0'
    os.environ['MODEL_ENABLE_CONTEXT_ASSERT'] = '1' if enable_context_assert else '0'
    os.environ['MODEL_ENABLE_RISK_ASSERT'] = '1' if enable_risk_assert else '0'
    os.environ['MODEL_ENABLE_ASSET_ASSERT'] = '1' if enable_asset_assert else '0'
    os.environ['MODEL_REQUIRE_ALL_ASSERT_ROUNDS_PASS'] = '1' if require_all_assert_rounds_pass else '0'
    os.environ['MODEL_REQUIRE_LAST_ROUND_PASS'] = '1' if require_last_round_pass else '0'

    result_dir, report_dir = build_allure_run_dirs()
    pytest_args = build_pytest_args(case_type=case_type, keyword=keyword, parallel_workers=parallel_workers)
    pytest_args.extend(['--alluredir', result_dir])
    # 清理模式：如需每次覆盖历史报告，解除下面一行注释，并配合下方 allure generate --clean 命令使用
    # pytest_args.append('--clean-alluredir')

    log.info('-' * 80)
    log.info('当前测试配置:')
    log.info(f"  环境 (env)  : {config['env']}")
    log.info(f"  分组 (group): {config['group']}")
    log.info(f"  用例类型    : {case_type}")
    log.info(f"  并发工作数  : {parallel_workers}")
    log.info(f"  单轮限制    : {single_turn_limit if single_turn_limit is not None else '全部'}")
    log.info(f"  多轮限制    : {multi_turn_limit if multi_turn_limit is not None else '全部'}")
    log.info(f"  keyword     : {keyword if keyword else '(按用例类型自动选择)'}")
    log.info(f"  pytest参数  : {pytest_args}")
    log.info('-' * 80)

    # 发送测试开始通知
    send_start_notice()

    pytest.main(pytest_args)

    generate_allure_report(result_dir, report_dir)
    # 清理模式：如需每次覆盖历史报告，解除下面一行注释，并注释上面的 generate_allure_report
    # os.system('allure generate ./report/tmp -o ./report/report --clean')
    allure_report_url = open_allure_report(report_dir)
    num_successd, num_failed = get_case_count(os.path.join(report_dir, 'widgets', 'summary.json'))
    elapsed_minutes = (time.time() - start_time) / 60

    # 从本轮运行目录聚合所有用例结果并生成汇总
    log.info('正在聚合本轮模型测试结果...')
    report_rows = ModelCaseHandler.load_model_rows_from_run()
    if report_rows:
        ModelCaseHandler.save_model_run_reports(report_rows)
        log.info(f'本轮聚合完成：{len(report_rows)} 条用例')
    else:
        log.info('本轮无模型测试结果')

    report_model_summary(num_successd, num_failed, allure_report_url, config['env'], config['group'], elapsed_minutes=elapsed_minutes)

    if serve_allure:
        os.system(f'allure serve {result_dir}')


if __name__ == '__main__':
    main()
