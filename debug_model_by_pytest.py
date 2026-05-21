# -*- coding: utf-8 -*-
"""
# @File    : debug_model_by_pytest.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
# @Description : 信贷大模型pytest执行入口文件
#
# 使用说明：
# 在 main 函数中直接设置 env 和 group 变量，然后运行 python debug_model_by_pytest.py
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.handle_yaml import update_test_config, get_test_config
from utils.handle_log import log
from utils.handle_allure_report import get_case_count, open_allure_report, report_summary


MODEL_WEHOOK_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=33b27e52-f5ab-4690-a62c-e8d1e3ce1a67'


def load_latest_model_summary():
    summary_dir = Path('./report/model_intent_recognition')
    summary_files = sorted(summary_dir.glob('model_intent_recognition_summary_*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
    if not summary_files:
        return None
    with open(summary_files[0], encoding='utf-8') as file:
        summary = json.load(file)
    return summary[0] if summary else None


def report_model_summary(num_successd, num_failed, allure_report_url, env=None, group=None, elapsed_minutes=0.0):
    model_summary = load_latest_model_summary()
    extra_lines = []
    if model_summary:
        extra_lines.extend([
            "类型 | 用例数 | 通过率",
            f"单轮 | {model_summary.get('单轮用例数', 0)} | {model_summary.get('单轮通过率', 0)}%",
            f"多轮 | {model_summary.get('多轮用例数', 0)} | {model_summary.get('多轮通过率', 0)}%",
            "耗时 | 平均 | P90 | P95 | 最大",
            f"响应 | {model_summary.get('平均响应耗时', 0)}s | {model_summary.get('P90响应耗时', 0)}s | {model_summary.get('P95响应耗时', 0)}s | {model_summary.get('最大响应耗时', 0)}s"
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
    """
    设置测试配置，如果传入了env或group则更新配置文件
    :param env: 环境标识，可选值: 'stable', 'yn_stable', 'mxg_stable', 'yn_pro', 'mxg_pro', 'pre', 'pro'
    :param group: 分组标识，可选值: 'stable', 'project_109111228', 'project_10963208', 'default'
    :return: dict, 当前配置 {'env': str, 'group': str}
    """
    if env or group:
        log.info(f"正在更新配置文件...")
        log.info(f"  env: {env if env else '(保持不变)'}")
        log.info(f"  group: {group if group else '(保持不变)'}")
        update_test_config(env=env, group=group)

    return get_test_config()


if __name__ == '__main__':
    # ========================================================================
    # 【在这里设置测试环境】
    # ========================================================================
    # 直接修改下面两行来设置测试环境
    # 设置为 None 表示使用配置文件中的值
    # ========================================================================

    env = 'pre'
    group = 'default'
    single_turn_limit = None
    multi_turn_limit = None

    # ========================================================================
    # 执行测试
    # ========================================================================

    start_time = time.time()

    log.info("=" * 80)
    log.info("信贷大模型 pytest 测试执行器")
    log.info("=" * 80)

    config = set_test_config(env, group)
    os.environ['MODEL_SINGLE_TURN_LIMIT'] = 'None' if single_turn_limit is None else str(single_turn_limit)
    os.environ['MODEL_MULTI_TURN_LIMIT'] = 'None' if multi_turn_limit is None else str(multi_turn_limit)

    log.info("-" * 80)
    log.info("当前测试配置:")
    log.info(f"  环境 (env)  : {config['env']}")
    log.info(f"  分组 (group): {config['group']}")
    log.info(f"  单轮用例限制: {single_turn_limit if single_turn_limit is not None else '全部'}")
    log.info(f"  多轮用例限制: {multi_turn_limit if multi_turn_limit is not None else '全部'}")
    log.info("-" * 80)
    log.info("\n开始执行信贷大模型自动化测试...\n")

    pytest.main([
        './test_cases/test_model_intent_recognition.py',
        '-s',
        '--alluredir', './report/tmp',
        '--clean-alluredir'
    ])

    # ========================================================================
    # 生成、打开Allure报告并发送企微通知
    # ========================================================================

    os.system('allure generate ./report/tmp -o ./report/report --clean')
    # os.system('allure serve ./report/tmp')

    allure_report_url = open_allure_report('./report/report')
    num_successd, num_failed = get_case_count('./report/report/widgets/summary.json')
    elapsed_minutes = (time.time() - start_time) / 60
    report_model_summary(num_successd, num_failed, allure_report_url, config['env'], config['group'], elapsed_minutes=elapsed_minutes)

    os.system('allure serve ./report/tmp')
