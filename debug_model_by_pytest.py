# -*- coding: utf-8 -*-
"""
# @File    : debug_model_by_pytest.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
# @Description : 信贷大模型 pytest 调试入口文件

使用方式：
在 main 函数中直接修改 TestConfig 参数，然后在 IDE 内直接运行本文件。
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.handle_allure_report import build_allure_run_dirs, generate_allure_report, get_case_count, open_allure_report
from utils.handle_log import log
from utils.handle_wechat_notify import send_start_notice, send_end_notice
from utils.handle_yaml import get_test_config, update_test_config
from utils.handle_model_cases import ModelCaseHandler

import pytest


# ============================================================
# 测试配置（用户可修改的参数区域）
# ============================================================

@dataclass
class TestConfig:
    """测试配置（直接修改参数后运行本文件）"""
    # ---- 基础环境配置 ----
    env: str = 'pre'                          # 测试环境：'pre' / 'pro'
    group: str = 'default'                     # 测试分组

    # ---- 运行模式配置 ----
    # 可选值：'single_turn'（单轮）、'multi_turn'（多轮）、'summary'（汇总）、'all'（全部）
    case_type: str = 'single_turn'

    # ---- 用例文件配置 ----
    single_turn_case_file: str = './case_data/model_single_intent_cases.xlsx'
    multi_turn_case_file: str = './case_data/model_dialog_cases.xlsx'

    # ---- 断言模式配置 ----
    # 可选值：'intent_similarity'（一致性评分）、'intent_checklist'（细粒度清单）、'intent_with_post'（组合断言）
    assert_mode: str = 'intent_checklist'

    # ---- 知识库注入配置 ----
    # 是否将完整知识库注入系统提示词（评估更精准但 Token 消耗高）
    # True  : 注入完整知识库到系统提示词（默认，推荐正式测试）
    # False : 不注入系统提示词，使用传统简洁提示词（推荐调试，执行更快）
    inject_knowledge_as_system: bool = False

    # ---- 并发配置 ----
    # pytest-xdist 并发工作进程数；IDE 调试建议设为 1，避免并行断点混乱
    parallel_workers: int = 1

    # ---- 用例数量限制 ----
    # None 表示全部；调试时建议先跑 1 条
    single_turn_limit: Optional[int] = 2
    multi_turn_limit: Optional[int] = None

    # ---- pytest 过滤 ----
    # 指定 pytest -k 过滤，例如 'MIR_0001'；None 表示不过滤
    keyword: Optional[str] = None

    # ---- Allure 配置 ----
    # 是否在测试结束后启动 allure serve；IDE 调试建议 False，避免进程阻塞
    serve_allure: bool = True

    # ---- 企微通知配置 ----
    # 是否发送企微测试报告通知（调试时可设为 False，避免频繁打扰）
    send_wechat_notice: bool = False
    # 企微 Webhook 地址（默认使用测试群，可替换为业务群）
    wechat_webhook_url: str = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=33b27e52-f5ab-4690-a62c-e8d1e3ce1a67'

    # ---- 多轮断言安全阀 ----
    enable_intent_assert: bool = True
    enable_context_assert: bool = True
    enable_risk_assert: bool = True
    enable_asset_assert: bool = True
    require_all_assert_rounds_pass: bool = True
    require_last_round_pass: bool = True

    def to_env_dict(self) -> dict:
        """将配置转换为环境变量字典"""
        return {
            'MODEL_SINGLE_TURN_LIMIT': 'None' if self.single_turn_limit is None else str(self.single_turn_limit),
            'MODEL_MULTI_TURN_LIMIT': 'None' if self.multi_turn_limit is None else str(self.multi_turn_limit),
            'MODEL_ASSERT_MODE': self.assert_mode,
            'MODEL_INJECT_KNOWLEDGE_AS_SYSTEM': '1' if self.inject_knowledge_as_system else '0',
            'MODEL_ENABLE_INTENT_ASSERT': '1' if self.enable_intent_assert else '0',
            'MODEL_ENABLE_CONTEXT_ASSERT': '1' if self.enable_context_assert else '0',
            'MODEL_ENABLE_RISK_ASSERT': '1' if self.enable_risk_assert else '0',
            'MODEL_ENABLE_ASSET_ASSERT': '1' if self.enable_asset_assert else '0',
            'MODEL_REQUIRE_ALL_ASSERT_ROUNDS_PASS': '1' if self.require_all_assert_rounds_pass else '0',
            'MODEL_REQUIRE_LAST_ROUND_PASS': '1' if self.require_last_round_pass else '0',
        }

    def apply_env(self):
        """将配置应用到环境变量"""
        for key, value in self.to_env_dict().items():
            os.environ[key] = value

    def __str__(self) -> str:
        return (
            f"环境: {self.env}, 分组: {self.group}, "
            f"用例类型: {self.case_type}, 断言模式: {self.assert_mode}, "
            f"并发数: {self.parallel_workers}, "
            f"单轮限制: {self.single_turn_limit if self.single_turn_limit is not None else '全部'}, "
            f"多轮限制: {self.multi_turn_limit if self.multi_turn_limit is not None else '全部'}"
        )


# ============================================================
# 内部辅助函数
# ============================================================

TEST_FILE = './test_cases/test_model_intent_recognition.py'


def _set_test_config(env='pre', group='default'):
    if env or group:
        log.info('正在更新配置文件...')
        log.info(f"  env: {env if env else '(保持不变)'}")
        log.info(f"  group: {group if group else '(保持不变)'}")
        update_test_config(env=env, group=group)
    return get_test_config()


def _build_pytest_args(config: TestConfig) -> list:
    """
    构建 pytest 执行参数

    Args:
        config: 测试配置对象

    Returns:
        pytest 命令行参数列表
    """
    keyword_map = {
        'single_turn': 'test_single_turn_intent_recognition',
        'multi_turn': 'test_multi_turn_dialog_consistency',
        'summary': 'test_model_summary_report'
    }
    selected_keyword = config.keyword or keyword_map.get(config.case_type)
    pytest_args = [TEST_FILE]
    if selected_keyword:
        pytest_args.extend(['-k', selected_keyword])
    pytest_args.extend(['-n', str(config.parallel_workers)])
    pytest_args.extend(['-s'])
    return pytest_args


# ============================================================
# 主入口
# ============================================================

def main():
    """
    信贷大模型 pytest 调试执行器主入口
    使用方式：直接修改 TestConfig 参数后运行本文件
    """
    # ===================================================================
    # 【IDE 调试参数：直接修改 TestConfig 即可】
    # ===================================================================
    config = TestConfig(
        # 示例：只跑单轮，一致性评分模式
        # case_type='single_turn',
        # assert_mode='intent_similarity',
        # single_turn_limit=5,
        # parallel_workers=1,
    )
    # ===================================================================

    os.environ['PYTHONIOENCODING'] = 'utf-8'

    start_time = time.time()

    log.info('=' * 80)
    log.info('信贷大模型 pytest 调试执行器')
    log.info(f'配置: {config}')
    log.info('=' * 80)

    # 设置环境和分组
    _set_test_config(config.env, config.group)
    run_id = datetime.now().strftime('%Y%m%d%H%M%S')
    os.environ['MODEL_REPORT_RUN_ID'] = run_id

    # 应用断言模式等环境变量
    config.apply_env()

    result_dir, report_dir = build_allure_run_dirs()
    pytest_args = _build_pytest_args(config)
    pytest_args.extend(['--alluredir', result_dir])
    # 清理模式：如需每次覆盖历史报告，解除下面一行注释
    pytest_args.append('--clean-alluredir')

    log.info('-' * 80)
    log.info('当前测试配置:')
    log.info(f"  环境 (env)  : {config.env}")
    log.info(f"  分组 (group) : {config.group}")
    log.info(f"  用例类型    : {config.case_type}")
    log.info(f"  断言模式    : {config.assert_mode}")
    log.info(f"  并发工作数  : {config.parallel_workers}")
    log.info(f"  单轮限制    : {config.single_turn_limit if config.single_turn_limit is not None else '全部'}")
    log.info(f"  多轮限制    : {config.multi_turn_limit if config.multi_turn_limit is not None else '全部'}")
    log.info(f"  keyword     : {config.keyword if config.keyword else '(按用例类型自动选择)'}")
    log.info(f"  pytest参数  : {pytest_args}")
    log.info('-' * 80)

    # 根据配置决定是否发送企微通知
    if config.send_wechat_notice:
        send_start_notice(webhook_url=config.wechat_webhook_url)
    else:
        log.info('已跳过企微开始通知（send_wechat_notice=False）')

    pytest.main(pytest_args)

    generate_allure_report(result_dir, report_dir)
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

    # 根据配置决定是否发送企微通知
    if config.send_wechat_notice:
        send_end_notice(
            env=config.env,
            group=config.group,
            assert_mode=config.assert_mode,
            case_type=config.case_type,
            num_successd=num_successd,
            num_failed=num_failed,
            allure_report_url=allure_report_url,
            elapsed_minutes=elapsed_minutes,
            webhook_url=config.wechat_webhook_url,
        )
    else:
        log.info('已跳过企微结束通知（send_wechat_notice=False）')

    if config.serve_allure:
        log.info(f'Allure 报告已生成并打开: {allure_report_url}')


if __name__ == '__main__':
    main()
