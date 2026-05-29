# -*- coding: utf-8 -*-
"""
# @File    : exec_pytest.py
# @Date    : 2024-08-14
# @Author  : jeremyzhai
# @Description : pytest执行入口文件
#
# 使用说明：
# 在 main 函数中直接设置 env 和 group 变量，然后运行 python exec_pytest.py
#
# ============================================================================
# 【支持的环境配置】
# ============================================================================
# stable       + stable                (国内稳定环境，支持MySQL断言)
# yn_stable    + project_109111228     (印尼稳定环境，支持ClickHouse断言)
# mxg_stable   + project_10963208      (墨西哥稳定环境，支持ClickHouse断言)
# yn_pro       + default               (印尼生产环境)
# mxg_pro      + default               (墨西哥生产环境)
# pro          + default               (生产环境)
# ============================================================================
"""

import pytest
import os
import sys

# ���加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.handle_yaml import update_test_config, get_test_config
from utils.handle_log import log
from utils.handle_allure_report import build_allure_run_dirs, generate_allure_report, get_case_count, open_allure_report, report_summary


def set_test_config(env='pro', group='default'):
    """
    设置测试配置，如果传入了env或group则更新配置文件

    :param env: 环境标识，可选值: 'stable', 'yn_stable', 'mxg_stable', 'yn_pro', 'mxg_pro', 'pro'
    :param group: 分组标识，可选值: 'stable', 'project_109111228', 'project_10963208', 'default'
    :return: dict, 当前配置 {'env': str, 'group': str}
    """
    # 如果传入了env或group，更新配置文件
    if env or group:
        log.info(f"正在更新配置文件...")
        log.info(f"  env: {env if env else '(保持不变)'}")
        log.info(f"  group: {group if group else '(保持不变)'}")
        update_test_config(env=env, group=group)

    # 返回当前配置
    return get_test_config()


if __name__ == '__main__':
    # ========================================================================
    # 【在这里设置测试环境】
    # ========================================================================
    # 直接修改下面两行来设置测试环境
    # 设置为 None 表示使用配置文件中的值
    # ========================================================================

    env = 'pre'  # 可选: 'stable', 'yn_stable', 'mxg_stable', 'yn_pro', 'mxg_pro', 'pro'
    group = 'default'  # 可选: 'stable', 'project_109111228', 'project_10963208', 'default'

    # 示例1: 印尼稳定环境
    # env = 'yn_stable'
    # group = 'project_109111228'

    # 示例2: 国内稳定环境
    # env = 'stable'
    # group = 'stable'

    # 示例3: 生产环境
    # env = 'pro'
    # group = 'default'

    # ========================================================================
    # 执行测试
    # ========================================================================

    log.info("=" * 80)
    log.info("pytest 测试执行器")
    log.info("=" * 80)

    # 设置测试配置
    config = set_test_config(env, group)

    log.info("-" * 80)
    log.info("当前测试配置:")
    log.info(f"  环境 (env)  : {config['env']}")
    log.info(f"  分组 (group): {config['group']}")
    log.info("-" * 80)
    log.info("\n开始执行测试...\n")

    # ========================================================================
    # 执行pytest测试
    # ========================================================================

    result_dir, report_dir = build_allure_run_dirs()
    pytest_args = [
        './test_cases/test_feature_platform.py',
        '-s',
        '--alluredir', result_dir
    ]
    # 清理模式：如需每次覆盖历史报告，解除下面两行注释，并配合下方 allure generate --clean 命令使用
    # pytest_args = ['./test_cases/test_feature_platform.py', '-s', '--alluredir', './report/tmp']
    # pytest_args.append('--clean-alluredir')
    pytest.main(pytest_args)

    # ========================================================================
    # 生成、打开Allure报告并发送企微通知
    # ========================================================================

    generate_allure_report(result_dir, report_dir)
    # 清理模式：如需每次覆盖历史报告，解除下面一行注释，并注释上面的 generate_allure_report
    # os.system('allure generate ./report/tmp -o ./report/report --clean')
    # os.system(f'allure serve {result_dir}')

    # 发送企微报告信息
    allure_report_url = open_allure_report(report_dir)
    num_successd, num_failed = get_case_count(os.path.join(report_dir, 'widgets', 'summary.json'))
    report_summary(num_successd, num_failed, allure_report_url, config['env'], config['group'])
