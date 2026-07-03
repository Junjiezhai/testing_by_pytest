# -*- coding: utf-8 -*-
"""
# @File    : debug_model_by_pytest.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
# @Description : 信贷/贷后大模型 pytest 调试入口文件

使用方式：
在 TestConfig 中通过 scene 参数切换场景（'credit' 或 'postloan'），
参数名通过 credit_ / postloan_ 前缀区分场景，直接修改后运行本文件。
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.handle_allure_report import build_allure_run_dirs, generate_allure_report, get_case_count, open_allure_report
from utils.handle_log import log
from utils.handle_wechat_notify import send_start_notice, send_end_notice, send_end_notice_batch
from utils.handle_yaml import get_test_config, update_test_config
from utils.handle_model_cases import ModelCaseHandler

import pytest

# 脚本所在目录（用于计算绝对路径，避免受当前工作目录影响）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# 测试配置（统一配置类，通过参数名和注释区分信贷/贷后）
# ============================================================

@dataclass
class TestConfig:
    """统一测试配置 —— 通过 scene 参数切换信贷/贷后场景

    参数命名约定：
    - credit_xxx  : 仅信贷场景生效的配置
    - postloan_xxx: 仅贷后场景生效的配置
    - 无前缀      : 两个场景通用的公共配置
    """

    # 告诉 pytest 不要收集这个类（避免 PytestCollectionWarning）
    __test__ = False

    # ---- 场景选择（公共） ----
    # 'credit'   : 信贷模型意图识别
    # 'postloan' : 贷后模型意图识别
    scene: str = 'postloan'

    # ---- 基础环境配置（公共） ----
    env: str = 'pre'                          # 测试环境：'pre' / 'pro'
    group: str = 'default'                     # 测试分组

    # ---- 运行模式配置（公共） ----
    # 信贷可选值：'single_turn'（单轮）、'multi_turn'（多轮）、'summary'（汇总）
    # 贷后固定值：'postloan_single_turn', 'postloan_multi_turn'
    case_type: str = 'postloan_multi_turn'

    # ---- case_type 枚举值（新增场景时只需修改这里）----
    CASE_TYPE_SINGLE_TURN: str = 'single_turn'
    CASE_TYPE_MULTI_TURN: str = 'multi_turn'
    CASE_TYPE_POSTLOAN_SINGLE_TURN: str = 'postloan_single_turn'
    CASE_TYPE_POSTLOAN_MULTI_TURN: str = 'postloan_multi_turn'

    # 单轮/多轮分类集合（新增场景时只需修改这里）
    SINGLE_TURN_TYPES: ClassVar[set] = {'single_turn', 'postloan_single_turn'}
    MULTI_TURN_TYPES: ClassVar[set] = {'multi_turn', 'postloan_multi_turn'}

    @classmethod
    def is_single_turn(cls, case_type: str) -> bool:
        return case_type in cls.SINGLE_TURN_TYPES

    @classmethod
    def is_multi_turn(cls, case_type: str) -> bool:
        return case_type in cls.MULTI_TURN_TYPES

    # ==== 信贷：用例文件配置 ====
    credit_single_turn_case_file: str = './case_data/model_single_intent_test_cases.xlsx'
    credit_multi_turn_case_file: str = './case_data/model_multi_intent_test_cases.xlsx'

    # ==== 贷后：用例文件配置（目前仅支持单轮） ====
    postloan_single_turn_case_file: str = './case_data/postloan_single_intent_test_cases.xlsx'
    postloan_multi_turn_case_file: str = './case_data/postloan_multi_intent_test_cases.xlsx'

    # ---- 用例数量限制（公共） ----
    # None 表示全部；调试时建议先跑 1 条
    single_turn_limit: Optional[int] = None  # 单轮用例限制（信贷/贷后通用）
    multi_turn_limit: Optional[int] = 1  # 信贷多轮：多轮用例限制（仅信贷场景生效）
    postloan_multi_turn_limit: Optional[int] = None  # 贷后多轮：多轮用例限制（仅贷后场景生效）

    # ==== 信贷：多轮对话批量评估通过阈值 ====
    multi_turn_pass_threshold: int = 70  # 信贷多轮对话外部模型评估的通过分数线（0~100）

    # ==== 贷后：多轮对话批量评估通过阈值 ====
    postloan_multi_turn_pass_threshold: int = 70  # 贷后多轮对话外部模型评估的通过分数线（0~100）

    # ---- 断言模式配置（公共） ----
    # 可选值：'intent_similarity'（一致性评分）、'intent_checklist'（细粒度清单）、'intent_with_post'（组合断言）
    assert_mode: str = 'intent_checklist'

    # ---- 知识库注入配置（公共） ----
    # True  : 注入完整知识库到系统提示词（默认，推荐正式测试）
    # False : 不注入系统提示词，使用传统简洁提示词（推荐调试，执行更快）
    inject_knowledge_as_system: bool = True

    # ---- 批量断言配置（公共） ----
    # True  : 启用批量断言模式（测试阶段只调用模型，断言在 session finish 中批量执行）
    # False : 逐条断言模式（默认，每条用例执行后实时调用外部模型断言）
    enable_batch_assert: bool = True
    batch_max_group_size: int = 5              # 单轮每组最大用例数（控制单次 prompt 长度）
    batch_max_group_size_multi: int = 1         # 信贷多轮：每组最大用例数（多轮 prompt 较长，建议设小）
    batch_judge_model: str = 'deepseek-v4-pro'  # 批量断言使用的外部模型名称

    # ---- 并发配置（公共） ----
    parallel_workers: int = 1                  # pytest-xdist 并发工作进程数

    # ---- 限流配置（公共） ----
    enable_rate_limiter: bool = True             # True: 保护下游服务；False: 调试时关闭加速
    model_rpm: float = 15                        # 每分钟请求数（RPM）
    model_burst: int = 3                         # 突发令牌数

    # ==== 信贷：多轮本地断言配置 ====
    local_assert_strict_mode: bool = True          # True=一票否决；False=宽松模式
    local_assert_max_fail_ratio: float = 0.0      # 宽松模式下允许的最大失败轮次比例
    local_assert_per_round: bool = True            # True=逐轮检查；False=只检查最后一轮

    # ==== 信贷：多轮增强评估配置 ====
    # True  : 启用增强评估（增加 Token 消耗，但评估维度更完整）
    # False : 关闭增强评估（默认，不影响主流程断言）
    enable_enhanced_multi_turn_eval: bool = False
    enhanced_eval_llm_judge_model: str = 'kimi-k2.6'
    enhanced_eval_enable_llm_judge: bool = True
    enhanced_eval_enable_state_validation: bool = True
    enhanced_eval_enable_consistency_check: bool = True
    enhanced_eval_state_validation_mode: str = 'strict'  # 'strict'（严格）/ 'lenient'（宽松）/ 'category'（分类）

    # ---- pytest 指定用例（公共） ----
    keyword: Optional[str] = None #'INTENT-RC-'               # 指定用例 ，例如 'MIR_0001'

    # ---- Allure 配置（公共） ----
    serve_allure: bool = True                      # False: IDE 调试避免进程阻塞

    # ---- 企微通知开关（公共） ----
    send_wechat_notice: bool = True

    # ==== 信贷：企微通知配置 ====
    credit_wechat_webhook_url: str = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=33b27e52-f5ab-4690-a62c-e8d1e3ce1a67'

    # ==== 贷后：企微通知配置 ====
    postloan_wechat_webhook_url: str = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=3e5af0ab-360b-4007-aed1-fd42263147b3'

    @property
    def current_webhook_url(self) -> str:
        """根据当前场景返回对应的企微 Webhook URL"""
        return self.credit_wechat_webhook_url if self.scene == 'credit' else self.postloan_wechat_webhook_url

    def to_env_dict(self) -> dict:
        """将配置转换为环境变量字典（根据 scene 自动切换环境变量名）"""
        env = {
            'MODEL_SCENE': self.scene,
            'MODEL_ASSERT_MODE': self.assert_mode,
            'MODEL_INJECT_KNOWLEDGE_AS_SYSTEM': '1' if self.inject_knowledge_as_system else '0',
            'MODEL_BATCH_ASSERT': '1' if self.enable_batch_assert else '0',
            'MODEL_BATCH_MAX_GROUP_SIZE': str(self.batch_max_group_size),
            'MODEL_BATCH_JUDGE_MODEL': self.batch_judge_model,
            'MODEL_RPM_ENABLE': '1' if self.enable_rate_limiter else '0',
            'MODEL_RPM': str(self.model_rpm),
            'MODEL_BURST': str(self.model_burst),
        }

        if self.scene == 'credit':
            env.update({
                'MODEL_SINGLE_TURN_LIMIT': 'None' if self.single_turn_limit is None else str(self.single_turn_limit),
                'MODEL_MULTI_TURN_LIMIT': 'None' if self.multi_turn_limit is None else str(self.multi_turn_limit),
                'MODEL_BATCH_MAX_GROUP_SIZE_MULTI': str(self.batch_max_group_size_multi),
                'MODEL_MULTI_TURN_PASS_THRESHOLD': str(self.multi_turn_pass_threshold),
                'MODEL_LOCAL_ASSERT_STRICT_MODE': '1' if self.local_assert_strict_mode else '0',
                'MODEL_LOCAL_ASSERT_MAX_FAIL_RATIO': str(self.local_assert_max_fail_ratio),
                'MODEL_LOCAL_ASSERT_PER_ROUND': '1' if self.local_assert_per_round else '0',
                'MODEL_ENHANCED_MULTI_TURN_EVAL': '1' if self.enable_enhanced_multi_turn_eval else '0',
                'MODEL_ENHANCED_LLM_JUDGE_MODEL': self.enhanced_eval_llm_judge_model,
                'MODEL_ENHANCED_ENABLE_LLM_JUDGE': '1' if self.enhanced_eval_enable_llm_judge else '0',
                'MODEL_ENHANCED_ENABLE_STATE_VALIDATION': '1' if self.enhanced_eval_enable_state_validation else '0',
                'MODEL_ENHANCED_ENABLE_CONSISTENCY_CHECK': '1' if self.enhanced_eval_enable_consistency_check else '0',
                'MODEL_ENHANCED_STATE_VALIDATION_MODE': self.enhanced_eval_state_validation_mode,
                'MODEL_SINGLE_TURN_CASE_FILE': os.path.normpath(os.path.join(_SCRIPT_DIR, self.credit_single_turn_case_file)),
                'MODEL_MULTI_TURN_CASE_FILE': os.path.normpath(os.path.join(_SCRIPT_DIR, self.credit_multi_turn_case_file)),
            })
        else:  # postloan
            env.update({
                'POSTLOAN_SINGLE_TURN_LIMIT': 'None' if self.single_turn_limit is None else str(self.single_turn_limit),
                'POSTLOAN_MULTI_TURN_LIMIT': 'None' if self.postloan_multi_turn_limit is None else str(self.postloan_multi_turn_limit),
                'MODEL_POSTLOAN_MULTI_TURN_PASS_THRESHOLD': str(self.postloan_multi_turn_pass_threshold),
                'MODEL_SINGLE_TURN_CASE_FILE': os.path.normpath(os.path.join(_SCRIPT_DIR, self.postloan_single_turn_case_file)),
                'MODEL_MULTI_TURN_CASE_FILE': os.path.normpath(os.path.join(_SCRIPT_DIR, self.postloan_multi_turn_case_file)),
            })

        return env

    def apply_env(self):
        """将配置应用到环境变量"""
        for key, value in self.to_env_dict().items():
            os.environ[key] = value

    def __str__(self) -> str:
        parts = [
            f"场景: {self.scene}",
            f"环境: {self.env}",
            f"分组: {self.group}",
            f"用例类型: {self.case_type}",
            f"断言模式: {self.assert_mode}",
            f"批量断言: {'开启' if self.enable_batch_assert else '关闭'} "
            f"(单轮组大小={self.batch_max_group_size}, 模型: {self.batch_judge_model})",
            f"限流: {'开启' if self.enable_rate_limiter else '关闭'} "
            f"({self.model_rpm}RPM/{self.model_burst}burst)",
            f"并发数: {self.parallel_workers}",
            f"单轮限制: {self.single_turn_limit if self.single_turn_limit is not None else '全部'}",
        ]

        if self.scene == 'credit':
            parts.append(f"多轮限制: {self.multi_turn_limit if self.multi_turn_limit is not None else '全部'}")
            parts.append(f"增强评估: {'开启' if self.enable_enhanced_multi_turn_eval else '关闭'}")

        return ", ".join(parts)


# ============================================================
# 内部辅助函数
# ============================================================

TEST_FILE = './test_cases/test_model_intent_recognition.py'
TEST_FILE_POSTLOAN = './test_cases/test_postloan.py'


def _get_test_file(config: TestConfig) -> str:
    """根据场景选择对应的测试文件"""
    if config.scene == 'postloan':
        return TEST_FILE_POSTLOAN
    return TEST_FILE


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
    """
    keyword_map = {
        'single_turn': 'test_single_turn_intent_recognition or test_model_summary_report',
        'multi_turn': 'test_multi_turn_dialog_consistency or test_model_summary_report',
        'summary': 'test_model_summary_report',
        'postloan_single_turn': 'test_postloan_single_turn_intent_recognition or test_postloan_summary_report',
        'postloan_multi_turn': 'test_postloan_multi_turn_dialog_consistency or test_postloan_summary_report',
    }
    selected_keyword = config.keyword or keyword_map.get(config.case_type)

    # 当用户自定义 keyword 时，需要确保 summary 方法也能被收集（用于触发批量断言和挂载报告）
    if config.keyword and config.case_type:
        if config.case_type == 'postloan_single_turn':
            selected_keyword = f"({config.keyword}) or test_postloan_summary_report"
        elif config.case_type == 'summary':
            selected_keyword = config.keyword
        else:
            selected_keyword = f"({config.keyword}) or test_model_summary_report"

    pytest_args = [_get_test_file(config)]
    if selected_keyword:
        pytest_args.extend(['-k', selected_keyword])
    pytest_args.extend(['-n', str(config.parallel_workers)])
    pytest_args.extend(['-s'])
    return pytest_args


def _calc_type_stats(report_rows: list) -> dict:
    """
    计算按类型统计（单轮/多轮）
    """
    if not report_rows:
        return {'single': {'pass': 0, 'fail': 0, 'total': 0, 'rate': '0.00%'},
                'multi': {'pass': 0, 'fail': 0, 'total': 0, 'rate': '0.00%'}}

    single_rows = [r for r in report_rows if TestConfig.is_single_turn(r.get('case_type', ''))]
    multi_rows = [r for r in report_rows if TestConfig.is_multi_turn(r.get('case_type', ''))]

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
# 公共运行逻辑（根据 scene 自动适配场景）
# ============================================================

def _run_tests(config: TestConfig, title: str):
    """
    公共测试运行逻辑 — 根据 config.scene 自动适配信贷/贷后场景
    """
    os.environ['PYTHONIOENCODING'] = 'utf-8'

    start_time = time.time()

    log.info('=' * 80)
    log.info(f'{title} pytest 调试执行器')
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
    pytest_args.append('--clean-alluredir')

    log.info('-' * 80)
    log.info('当前测试配置:')
    log.info(f"  场景        : {config.scene}")
    log.info(f"  环境 (env)  : {config.env}")
    log.info(f"  分组 (group) : {config.group}")
    log.info(f"  用例类型    : {config.case_type}")
    log.info(f"  断言模式    : {config.assert_mode}")
    log.info(f"  批量断言    : {'开启' if config.enable_batch_assert else '关闭'} (每组 {config.batch_max_group_size} 条, 模型: {config.batch_judge_model})")
    log.info(f"  限流控制    : {'开启' if config.enable_rate_limiter else '关闭'} (RPM={config.model_rpm}, burst={config.model_burst})")
    log.info(f"  并发工作数  : {config.parallel_workers}")

    # ---- 用例文件配置（根据 case_type 针对性打印） ----
    is_single_turn = TestConfig.is_single_turn(config.case_type)
    is_multi_turn = TestConfig.is_multi_turn(config.case_type)

    if config.scene == 'credit':
        if is_single_turn:
            log.info(f"  单轮用例文件: {config.credit_single_turn_case_file}")
        elif is_multi_turn:
            log.info(f"  多轮用例文件: {config.credit_multi_turn_case_file}")
        else:
            log.info(f"  单轮用例文件: {config.credit_single_turn_case_file}")
            log.info(f"  多轮用例文件: {config.credit_multi_turn_case_file}")
    else:
        if is_single_turn:
            log.info(f"  单轮用例文件: {config.postloan_single_turn_case_file}")
        elif is_multi_turn:
            log.info(f"  多轮用例文件: {config.postloan_multi_turn_case_file}")
        else:
            log.info(f"  单轮用例文件: {config.postloan_single_turn_case_file}")
            log.info(f"  多轮用例文件: {config.postloan_multi_turn_case_file}")

    # ---- 用例数量限制配置 ----
    if is_single_turn:
        log.info(f"  单轮限制    : {config.single_turn_limit if config.single_turn_limit is not None else '全部'}")
    elif is_multi_turn:
        if config.scene == 'credit':
            log.info(f"  多轮限制    : {config.multi_turn_limit if config.multi_turn_limit is not None else '全部'}")
        else:
            log.info(f"  多轮限制    : {config.postloan_multi_turn_limit if config.postloan_multi_turn_limit is not None else '全部'}")
    else:
        log.info(f"  单轮限制    : {config.single_turn_limit if config.single_turn_limit is not None else '全部'}")
        if config.scene == 'credit':
            log.info(f"  多轮限制    : {config.multi_turn_limit if config.multi_turn_limit is not None else '全部'}")
        else:
            log.info(f"  多轮限制    : {config.postloan_multi_turn_limit if config.postloan_multi_turn_limit is not None else '全部'}")

    log.info(f"  keyword     : {config.keyword if config.keyword else '(按用例类型自动选择)'}")
    log.info(f"  pytest参数  : {pytest_args}")
    log.info('-' * 80)

    # 根据配置决定是否发送企微通知
    if config.send_wechat_notice:
        send_start_notice(webhook_url=config.current_webhook_url)
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
        # 根据场景筛选报告行
        if config.scene == 'postloan':
            postloan_rows = [r for r in report_rows if TestConfig.is_single_turn(r.get('case_type', ''))]
            if postloan_rows:
                ModelCaseHandler.save_model_run_reports(postloan_rows)
                log.info(f'本轮贷后聚合完成：{len(postloan_rows)} 条用例')
            else:
                log.info('本轮无贷后模型测试结果')
        else:
            ModelCaseHandler.save_model_run_reports(report_rows)
            log.info(f'本轮聚合完成：{len(report_rows)} 条用例')
    else:
        log.info('本轮无模型测试结果')

    # 根据配置决定是否发送企微通知
    if config.send_wechat_notice:
        # 批量模式：使用批量断言专用通知（信贷 + 贷后场景通用）
        if config.enable_batch_assert:
            batch_summary = None
            try:
                import glob
                batch_result_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report', 'model_intent_recognition', 'batch_assert')
                batch_result_files = glob.glob(os.path.join(batch_result_dir, 'batch_assert_result_*.json'))
                if batch_result_files:
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

            response_stats = _calc_response_stats(report_rows)
            if response_stats:
                log.info(f"【批量断言】响应耗时统计：平均={response_stats['avg']}, P90={response_stats['p90']}, P95={response_stats['p95']}, 最大={response_stats['max']}")

            # 批量断言模式下，用批量断言的实际结果替换 Allure 的 pytest 结果
            # （pytest 在批量模式下都是通过的，真实结果来自批量评估）
            if batch_summary:
                batch_num_successd = batch_summary['pass_count']
                batch_num_failed = batch_summary['failed_count']
            else:
                batch_num_successd = num_successd
                batch_num_failed = num_failed

            send_end_notice_batch(
                env=config.env,
                group=config.group,
                assert_mode=config.assert_mode,
                case_type=config.case_type,
                num_successd=batch_num_successd,
                num_failed=batch_num_failed,
                allure_report_url=allure_report_url,
                elapsed_minutes=elapsed_minutes,
                webhook_url=config.current_webhook_url,
                batch_summary=batch_summary,
                response_stats=response_stats,
            )
        else:
            # 信贷非批量 / 贷后场景：使用普通通知
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
                webhook_url=config.current_webhook_url,
                type_stats=type_stats,
                response_stats=response_stats,
            )
    else:
        log.info('已跳过企微结束通知（send_wechat_notice=False）')

    if config.serve_allure:
        log.info(f'Allure 报告已生成并打开: {allure_report_url}')


# ============================================================
# 主入口
# ============================================================

def main():
    """
    大模型 pytest 调试执行器主入口
    使用方式：直接修改 TestConfig 参数（scene='credit' 或 scene='postloan'）后运行本文件
    """
    # ===================================================================
    # 【IDE 调试参数：直接修改 TestConfig 即可，通过 scene 切换信贷/贷后】
    # ===================================================================
    config = TestConfig(
        # scene='credit',   # 信贷场景（默认）
        # scene='postloan', # 贷后场景
        # case_type='single_turn',
        # assert_mode='intent_similarity',
        # single_turn_limit=5,
        # parallel_workers=1,
    )
    # ===================================================================

    scene_title_map = {
        'credit': '信贷大模型',
        'postloan': '贷后催收大模型',
    }
    title = scene_title_map.get(config.scene, '大模型')
    _run_tests(config, title)


if __name__ == '__main__':
    main()
