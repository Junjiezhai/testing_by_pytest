# -*- coding: utf-8 -*-
"""
# @File    : postloan_model_cases.py
# @Date    : 2026-06-17
# @Author  : jeremyzhai
# @Description : 贷后催收用例加载工具
#
# 作用：
#   - 加载贷后单轮用例（postloan_single_intent_test_cases.xlsx）
#   - 加载贷后多轮用例（postloan_multi_intent_test_cases.xlsx）
#   - 组装 pytest parametrize 参数
#   - 获取用例描述列表（用于 pytest ids）
#
# 与 handle_model_cases.py 的关系：
#   - 复用 ModelCaseHandler 的基础能力
#   - 指定贷后专用用例文件路径
#   - 支持独立的环境变量控制
"""

import os

from utils.handle_model_cases import ModelCaseHandler


# ============================================================
# 贷后用例文件路径
# ============================================================
POSTLOAN_SINGLE_TURN_CASE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'case_data', 'postloan_single_intent_test_cases.xlsx'
)

POSTLOAN_MULTI_TURN_CASE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'case_data', 'postloan_multi_intent_test_cases.xlsx'
)

# 环境变量名
POSTLOAN_SINGLE_TURN_LIMIT_ENV = 'POSTLOAN_SINGLE_TURN_LIMIT'
POSTLOAN_MULTI_TURN_LIMIT_ENV = 'POSTLOAN_MULTI_TURN_LIMIT'


# ============================================================
# 贷后单轮用例加载
# ============================================================

def get_postloan_single_turn_cases(limit=None, case_file=None):
    """
    获取贷后单轮用例

    复用 ModelCaseHandler.get_single_turn_cases() 逻辑，
    但指定贷后专用用例文件路径。

    Args:
        limit: 限制用例数量，None 表示全部
        case_file: 用例文件路径，None 时使用默认贷后用例文件

    Returns:
        用例列表
    """
    if case_file is None:
        case_file = POSTLOAN_SINGLE_TURN_CASE_FILE
    return ModelCaseHandler.get_single_turn_cases(limit=limit, case_file=case_file)


# ============================================================
# 贷后多轮用例加载
# ============================================================

def get_postloan_multi_turn_cases(limit=None, case_file=None):
    """
    获取贷后多轮用例

    复用 ModelCaseHandler.get_model_cases() 逻辑，
    但指定贷后专用多轮用例文件路径。

    Args:
        limit: 限制用例数量，None 表示全部
        case_file: 用例文件路径，None 时使用默认贷后多轮用例文件

    Returns:
        用例列表
    """
    if case_file is None:
        case_file = POSTLOAN_MULTI_TURN_CASE_FILE
    return ModelCaseHandler.get_model_cases(
        case_type='multi_turn',
        limit=limit,
        case_file=case_file,
    )


# ============================================================
# 组装 pytest parametrize 参数
# ============================================================

def assemble_postloan_case_params(case_type='single_turn', limit=None):
    """
    组装贷后用例参数（用于 pytest @pytest.mark.parametrize）

    Args:
        case_type: 用例类型（'single_turn' 或 'multi_turn'）
        limit: 限制用例数量

    Returns:
        (var_list, value_list) 元组
    """
    if case_type == 'single_turn':
        if limit is None:
            limit = ModelCaseHandler.get_env_limit(env_name=POSTLOAN_SINGLE_TURN_LIMIT_ENV, default=None)
        case_list = get_postloan_single_turn_cases(limit=limit)
    elif case_type == 'multi_turn':
        if limit is None:
            limit = ModelCaseHandler.get_env_limit(env_name=POSTLOAN_MULTI_TURN_LIMIT_ENV, default=None)
        case_list = get_postloan_multi_turn_cases(limit=limit)
    else:
        raise ValueError(f"不支持的贷后用例类型: {case_type}，可选: single_turn, multi_turn")

    var_list = 'case_info'
    value_list = case_list
    if not value_list:
        value_list = [None]
    return var_list, value_list


# ============================================================
# 获取用例描述列表（pytest ids）
# ============================================================

def get_postloan_case_desc(case_type='single_turn', limit=None):
    """
    获取贷后用例ID列表（用于 pytest parametrize 的 ids 参数）

    Args:
        case_type: 用例类型
        limit: 限制用例数量

    Returns:
        用例ID列表（case_id）
    """
    if case_type == 'single_turn':
        if limit is None:
            limit = ModelCaseHandler.get_env_limit(env_name=POSTLOAN_SINGLE_TURN_LIMIT_ENV, default=None)
        case_list = get_postloan_single_turn_cases(limit=limit)
    elif case_type == 'multi_turn':
        if limit is None:
            limit = ModelCaseHandler.get_env_limit(env_name=POSTLOAN_MULTI_TURN_LIMIT_ENV, default=None)
        case_list = get_postloan_multi_turn_cases(limit=limit)
    else:
        raise ValueError(f"不支持的贷后用例类型: {case_type}，可选: single_turn, multi_turn")

    if not case_list:
        return ['无可执行用例']
    return [case.get('case_id', f'贷后用例-{i}') for i, case in enumerate(case_list)]
