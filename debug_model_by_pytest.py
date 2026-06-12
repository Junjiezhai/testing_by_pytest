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
from utils.handle_wechat_notify import send_start_notice, send_end_notice, send_end_notice_batch
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
    case_type: str = 'multi_turn'

    # ---- 用例文件配置 ----
    single_turn_case_file: str = './case_data/model_single_intent_test_cases.xlsx'
    multi_turn_case_file: str = './case_data/model_multi_intent_test_cases.xlsx'

    # ---- 断言模式配置 ----
    # 可选值：'intent_similarity'（一致性评分）、'intent_checklist'（细粒度清单）、'intent_with_post'（组合断言）
    assert_mode: str = 'intent_checklist'

    # ---- 知识库注入配置 ----
    # 是否将完整知识库注入系统提示词（评估更精准但 Token 消耗高）
    # True  : 注入完整知识库到系统提示词（默认，推荐正式测试）
    # False : 不注入系统提示词，使用传统简洁提示词（推荐调试，执行更快）
    inject_knowledge_as_system: bool = True

    # ---- 批量断言配置 ----
    # 批量断言：跑完全部用例后汇总结果，一次性注入知识库做批量评估（大幅降低 Token 消耗）
    # True  : 启用批量断言模式（测试阶段只调用信贷模型，断言在 session finish 中批量执行）
    # False : 逐条断言模式（默认，当前行为，每条用例执行后实时调用外部模型断言）
    # 注意：批量模式下，pytest 的通过/失败只反映接口调用结果，真实语义断言结果在 Allure 报告中查看
    enable_batch_assert: bool = True

    # 批量模式下，每组最大用例数（控制单次 prompt 长度，防止超出模型 token 限制）
    # 建议值：5~15；值越小单次请求越快，但总请求次数会增加
    batch_max_group_size: int = 5

    # 多轮对话批量模式下，每组最大用例数（多轮 prompt 较长，建议设小一些）
    # 建议值：1~3；值越小单次请求越快，但总请求次数会增加
    batch_max_group_size_multi: int = 1

    # 批量断言使用的外部模型名称（用于语义相似度评估）
    # 可选值：'deepseek-v4-pro'（默认，推荐）
    batch_judge_model: str = 'deepseek-v4-pro'#'deepseek-v4-pro'

    # ---- 并发配置 ----
    # pytest-xdist 并发工作进程数；IDE 调试建议设为 1，避免并行断点混乱
    parallel_workers: int = 1

    # ---- 限流配置 ----
    # 是否启用模型请求限流（保护下游信贷模型服务）
    # True  : 启用限流（推荐正式测试或模型负载较高时启用）
    # False : 关闭限流（默认，调试时关闭可加速执行）
    enable_rate_limiter: bool = True
    # 模型请求限流速率（每分钟请求数，RPM），enable_rate_limiter=True 时生效
    # 建议值：30 ~ 120；值越小对模型保护越强，但执行总时长会增加
    model_rpm: float = 15
    # 突发令牌数（允许短时的突发请求数），建议值：2 ~ 10
    model_burst: int = 3

    # ---- 用例数量限制 ----
    # None 表示全部；调试时建议先跑 1 条
    single_turn_limit: Optional[int] = None
    multi_turn_limit: Optional[int] = 1

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

    # ---- 多轮对话批量评估通过阈值 ----
    # 多轮对话外部模型评估的通过分数线（0~100），默认70分
    # 低于此分数视为评估未通过
    multi_turn_pass_threshold: int = 70

    # ---- 多轮本地断言配置 ----
    # 本地断言严格模式：
    # True  : 一票否决（任意一轮 ASSET/转人工失败，整体失败）—— 推荐生产环境
    # False : 宽松模式（允许部分轮次失败，整体仍算通过）
    local_assert_strict_mode: bool = True
    # 宽松模式下，允许的最大失败轮次比例（0.0 ~ 1.0，仅在 strict_mode=False 时生效）
    local_assert_max_fail_ratio: float = 0.0
    # 是否启用逐轮本地断言（True=逐轮检查，False=只检查最后一轮）
    local_assert_per_round: bool = True

    # ---- 多轮增强评估配置 ----
    # 是否启用多轮增强评估（LLM Judge + 状态转移验证 + 信息一致性检查）
    # True  : 启用增强评估（增加 Token 消耗，但评估维度更完整）
    # False : 关闭增强评估（默认，不影响主流程断言）
    enable_enhanced_multi_turn_eval: bool = False
    # 增强评估使用的 LLM Judge 模型名称
    enhanced_eval_llm_judge_model: str = 'kimi-k2.6'
    # 增强评估 LLM Judge 开关
    enhanced_eval_enable_llm_judge: bool = True
    # 增强评估状态转移验证开关
    enhanced_eval_enable_state_validation: bool = True
    # 增强评估信息一致性检查开关
    enhanced_eval_enable_consistency_check: bool = True
    # 状态转移验证模式：'strict'（严格）/ 'lenient'（宽松）/ 'category'（分类）
    enhanced_eval_state_validation_mode: str = 'strict'

    def to_env_dict(self) -> dict:
        """将配置转换为环境变量字典"""
        return {
            'MODEL_SINGLE_TURN_LIMIT': 'None' if self.single_turn_limit is None else str(self.single_turn_limit),
            'MODEL_MULTI_TURN_LIMIT': 'None' if self.multi_turn_limit is None else str(self.multi_turn_limit),
            'MODEL_ASSERT_MODE': self.assert_mode,
    'MODEL_INJECT_KNOWLEDGE_AS_SYSTEM': '1' if self.inject_knowledge_as_system else '0',
            # 多轮增强评估配置
            'MODEL_ENHANCED_MULTI_TURN_EVAL': '1' if self.enable_enhanced_multi_turn_eval else '0',
            'MODEL_ENHANCED_LLM_JUDGE_MODEL': self.enhanced_eval_llm_judge_model,
            'MODEL_ENHANCED_ENABLE_LLM_JUDGE': '1' if self.enhanced_eval_enable_llm_judge else '0',
            'MODEL_ENHANCED_ENABLE_STATE_VALIDATION': '1' if self.enhanced_eval_enable_state_validation else '0',
            'MODEL_ENHANCED_ENABLE_CONSISTENCY_CHECK': '1' if self.enhanced_eval_enable_consistency_check else '0',
            'MODEL_ENHANCED_STATE_VALIDATION_MODE': self.enhanced_eval_state_validation_mode,
            # 批量断言配置
            'MODEL_BATCH_ASSERT': '1' if self.enable_batch_assert else '0',
            'MODEL_BATCH_MAX_GROUP_SIZE': str(self.batch_max_group_size),
            'MODEL_BATCH_MAX_GROUP_SIZE_MULTI': str(self.batch_max_group_size_multi),
            'MODEL_BATCH_JUDGE_MODEL': self.batch_judge_model,
            # 多轮对话评估阈值配置
            'MODEL_MULTI_TURN_PASS_THRESHOLD': str(self.multi_turn_pass_threshold),
            # 多轮本地断言配置
            'MODEL_LOCAL_ASSERT_STRICT_MODE': '1' if self.local_assert_strict_mode else '0',
            'MODEL_LOCAL_ASSERT_MAX_FAIL_RATIO': str(self.local_assert_max_fail_ratio),
            'MODEL_LOCAL_ASSERT_PER_ROUND': '1' if self.local_assert_per_round else '0',
            # 限流配置
            'MODEL_RPM_ENABLE': '1' if self.enable_rate_limiter else '0',
            'MODEL_RPM': str(self.model_rpm),
            'MODEL_BURST': str(self.model_burst),
            # 用例文件路径配置
            'MODEL_SINGLE_TURN_CASE_FILE': os.path.abspath(self.single_turn_case_file),
            'MODEL_MULTI_TURN_CASE_FILE': os.path.abspath(self.multi_turn_case_file),
        }

    def apply_env(self):
        """将配置应用到环境变量"""
        for key, value in self.to_env_dict().items():
            os.environ[key] = value

    def __str__(self) -> str:
        return (
            f"环境: {self.env}, 分组: {self.group}, "
            f"用例类型: {self.case_type}, 断言模式: {self.assert_mode}, "
            f"批量断言: {'开启' if self.enable_batch_assert else '关闭'} "
            f"(单轮组大小={self.batch_max_group_size}, 多轮组大小={self.batch_max_group_size_multi}), "
            f"限流: {'开启' if self.enable_rate_limiter else '关闭'} "
            f"({self.model_rpm}RPM/{self.model_burst}burst), "
            f"并发数: {self.parallel_workers}, "
            f"单轮限制: {self.single_turn_limit if self.single_turn_limit is not None else '全部'}, "
            f"多轮限制: {self.multi_turn_limit if self.multi_turn_limit is not None else '全部'}, "
            f"增强评估: {'开启' if self.enable_enhanced_multi_turn_eval else '关闭'}"
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
        'single_turn': 'test_single_turn_intent_recognition or test_model_summary_report',
        'multi_turn': 'test_multi_turn_dialog_consistency or test_model_summary_report',
        'summary': 'test_model_summary_report'
    }
    selected_keyword = config.keyword or keyword_map.get(config.case_type)
    pytest_args = [TEST_FILE]
    if selected_keyword:
        pytest_args.extend(['-k', selected_keyword])
    pytest_args.extend(['-n', str(config.parallel_workers)])
    pytest_args.extend(['-s'])
    return pytest_args


def _calc_type_stats(report_rows: list) -> dict:
    """
    计算按类型统计（单轮/多轮）

    :param report_rows: 报告行列表
    :return: {
        'single': {'pass': int, 'fail': int, 'total': int, 'rate': str},
        'multi': {'pass': int, 'fail': int, 'total': int, 'rate': str},
    }
    """
    if not report_rows:
        return {'single': {'pass': 0, 'fail': 0, 'total': 0, 'rate': '0.00%'},
                'multi': {'pass': 0, 'fail': 0, 'total': 0, 'rate': '0.00%'}}

    single_rows = [r for r in report_rows if r.get('case_type') == 'single_turn']
    multi_rows = [r for r in report_rows if r.get('case_type') == 'multi_turn']

    single_pass = sum(1 for r in single_rows if r.get('is_pass') is True)
    single_fail = len(single_rows) - single_pass
    single_total = len(single_rows)
    single_rate = f'{single_pass / single_total * 100:.2f}%' if single_total else '0.00%'

    multi_pass = sum(1 for r in multi_rows if r.get('is_pass') is True)
    multi_fail = len(multi_rows) - multi_pass
    multi_total = len(multi_rows)
    multi_rate = f'{multi_pass / multi_total * 100:.2f}%' if multi_total else '0.00%'

    return {
        'single': {'pass': single_pass, 'fail': single_fail, 'total': single_total, 'rate': single_rate},
        'multi': {'pass': multi_pass, 'fail': multi_fail, 'total': multi_total, 'rate': multi_rate},
    }


def _calc_response_stats(report_rows: list) -> dict:
    """
    计算响应耗时统计

    :param report_rows: 报告行列表
    :return: {
        'avg': str,   # 平均耗时
        'p90': str,   # P90
        'p95': str,   # P95
        'max': str,   # 最大耗时
    }
    """
    if not report_rows:
        return {'avg': 'N/A', 'p90': 'N/A', 'p95': 'N/A', 'max': 'N/A'}

    response_times = [float(r.get('response_time', 0)) for r in report_rows if r.get('response_time') is not None]
    if not response_times:
        return {'avg': 'N/A', 'p90': 'N/A', 'p95': 'N/A', 'max': 'N/A'}

    sorted_times = sorted(response_times)
    n = len(sorted_times)
    avg = sum(sorted_times) / n
    p90 = sorted_times[int(n * 0.9)] if n > 1 else sorted_times[0]
    p95 = sorted_times[int(n * 0.95)] if n > 1 else sorted_times[0]
    max_val = sorted_times[-1]

    return {
        'avg': f'{avg:.3f}s',
        'p90': f'{p90:.3f}s',
        'p95': f'{p95:.3f}s',
        'max': f'{max_val:.3f}s',
    }


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
    log.info(f"  批量断言    : {'开启' if config.enable_batch_assert else '关闭'} (每组 {config.batch_max_group_size} 条, 模型: {config.batch_judge_model})")
    log.info(f"  限流控制    : {'开启' if config.enable_rate_limiter else '关闭'} (RPM={config.model_rpm}, burst={config.model_burst})")
    log.info(f"  并发工作数  : {config.parallel_workers}")
    log.info(f"  单轮限制    : {config.single_turn_limit if config.single_turn_limit is not None else '全部'}")
    log.info(f"  多轮限制    : {config.multi_turn_limit if config.multi_turn_limit is not None else '全部'}")
    log.info(f"  keyword     : {config.keyword if config.keyword else '(按用例类型自动选择)'}")
    log.info(f"  pytest参数  : {pytest_args}")
    log.info('-' * 80)

    # 根据配置决定是否发送企微通知
    if config.send_wechat_notice:
        send_start_notice(webhook_url=config.wechat_webhook_url)
        pass
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
        # 批量模式：使用批量断言专用模板
        if config.enable_batch_assert:
            # 批量模式下，读取所有进程生成的批量断言结果文件
            batch_summary = None
            try:
                import json
                import glob
                batch_result_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report', 'model_intent_recognition', 'batch_assert')
                batch_result_files = glob.glob(os.path.join(batch_result_dir, 'batch_assert_result_*.json'))
                if batch_result_files:
                    # 合并所有进程的结果
                    total = 0
                    pass_count = 0
                    failed_count = 0
                    for batch_result_file in batch_result_files:
                        with open(batch_result_file, 'r', encoding='utf-8') as f:
                            single_summary = json.load(f)
                        total += single_summary.get('total', 0)
                        pass_count += single_summary.get('pass_count', 0)
                        failed_count += single_summary.get('failed_count', 0)
                    batch_summary = {
                        'total': total,
                        'pass_count': pass_count,
                        'failed_count': failed_count,
                        'pass_rate': f'{round(pass_count / total * 100, 2)}%' if total else 'N/A',
                    }
                    log.info(f"【批量断言】读取到 {len(batch_result_files)} 个进程的批量断言结果：通过 {pass_count} / 失败 {failed_count}")
                else:
                    log.warning(f"【批量断言】未找到批量断言结果文件")
            except Exception as e:
                log.warning(f"【批量断言】读取批量断言结果失败：{e}")

            # 计算响应耗时统计（从持久化的 report_rows 中提取，支持多进程）
            response_stats = _calc_response_stats(report_rows)
            if response_stats:
                log.info(f"【批量断言】响应耗时统计：平均={response_stats['avg']}, P90={response_stats['p90']}, P95={response_stats['p95']}, 最大={response_stats['max']}")

            send_end_notice_batch(
                env=config.env,
                group=config.group,
                assert_mode=config.assert_mode,
                case_type=config.case_type,
                num_successd=num_successd,
                num_failed=num_failed,
                allure_report_url=allure_report_url,
                elapsed_minutes=elapsed_minutes,
                webhook_url=config.wechat_webhook_url,
                batch_summary=batch_summary,
                response_stats=response_stats,
            )
        # 非批量模式：使用原有模板（恢复原来的报告格式）
        else:
            # 计算按类型统计和响应耗时统计
            type_stats = _calc_type_stats(report_rows)
            response_stats = _calc_response_stats(report_rows)

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
                type_stats=type_stats,
                response_stats=response_stats,
            )
    else:
        log.info('已跳过企微结束通知（send_wechat_notice=False）')

    if config.serve_allure:
        log.info(f'Allure 报告已生成并打开: {allure_report_url}')


if __name__ == '__main__':
    main()
