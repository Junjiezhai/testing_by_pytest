# -*- coding: utf-8 -*-
"""
# @File    : handle_cases.py
# @Date    : 2024-08-14
# @Author  : jeremyzhai
"""
import pandas as pd
import os
from utils.handle_yaml import get_test_config


def filter_rows_by_type(xlsx_name='process_test_cases.xlsx', target_type='execute_online'):
    """
    从指定用例文件中读取文件内容
    :param xlsx_name: 文件名
    :param target_type: 类型条件，枚举，与函数名保持一致
    :return:
    """
    # 定义文件路径，位于上一级的 case_data 文件夹中
    xlsx_file_path = os.path.join(os.path.dirname(__file__), '..', 'case_data', xlsx_name)

    # 强制所有列读取为字符串，避免类型转换导致“看起来截断”
    df = pd.read_excel(xlsx_file_path, engine='openpyxl', dtype=str)
    # 去除单元格中常见的隐藏字符（可选，按需）
    df = df.replace(r'[\r\n\t]', '', regex=True)

    # #################查看单元格内容#############################
    # wb = load_workbook(xlsx_file_path)
    # ws = wb.active
    # print(ws['D69'].value)  # 替换为实际单元格

    # 筛选 "类型" 列值为 target_type 的行
    filtered_rows_df = df[df['类型'] == target_type]

    # 将筛选后的 DataFrame 转换为列表，列表中的每个元素是一个字典
    filtered_rows_list = filtered_rows_df.to_dict('records')

    return filtered_rows_list


def assemble_case_params(engine_type: str, exec_type: str):
    """
    组装流程决策用例，满足如下格式
    @pytest.mark.parametrize('a,b', [(1, 2), (3, 4), (5, 6)])  # ('变量名',[1,2,3])
    :param engine_type: 引擎类型， process, package, feature
    :param exec_type: 决策类型，
    process: execute_online, execute_batch, execute_simulate
    package: online_exec_rcflow_decision, online_exec_make_decision, online_exec_package_decision
    feature: field_batch, ruleengine_proxy, simulate_proxy, business_proxy, offline_proxy
    :return: ('变量名1,变量名2', [变量值1,变量值2])
    """
    # 从配置文件读取env和group
    config = get_test_config()
    env = config['env']
    group = config['group']

    # 以下是不同环境的配置示例（已注释，现在从test_config.yaml读取）
    # env, group = 'mxg_stable', 'project_10963208'
    # env, group = 'mxg_pro', 'default'
    # env, group = 'yn_stable', 'project_109111228'
    # env, group = 'yn_pro', 'default'
    # env, group = 'stable', 'stable'
    # env, group = 'pro', 'default'

    case_res = filter_rows_by_type(xlsx_name=f'{env}_{engine_type}_test_cases.xlsx', target_type=exec_type)
    var_list = f'{engine_type}_info, assert_rules, env, group'
    value_list = []

    for i in range(len(case_res)):
        process_info = eval(case_res[i]["入参"])
        assert_rules = eval(case_res[i]["预期结果"])
        # if i==69:
        #     print(case_res[i]["预期结果"])
        #     print(i, repr(case_res[i]["入参"]), repr(case_res[i]["预期结果"]))
        value_list.append((process_info, assert_rules, env, group))

    return var_list, value_list


def get_case_desc(engine_type:str, exec_type: str):
    """
    获取流程决策用例标题
    :param engine_type: 引擎类型， process, package, feature
    :param exec_type: 决策类型，
    process: execute_online, execute_batch, execute_simulate
    package: online_exec_rcflow_decision, online_exec_make_decision, online_exec_package_decision
    feature: field_batch, ruleengine_proxy, simulate_proxy, business_proxy, offline_proxy
    :return: list, 用例描述列表
    """
    # 从配置文件读取env
    config = get_test_config()
    env = config['env']

    case_res = filter_rows_by_type(xlsx_name=f'{env}_{engine_type}_test_cases.xlsx', target_type=exec_type)
    case_desc_list = []
    for i in range(len(case_res)):
        case_desc_list.append(case_res[i]["场景"])

    return case_desc_list


if __name__ == '__main__':
    # result = filter_rows_by_type()
    # print(assemble_case_params(engine_type='process', exec_type='execute_online'))

    print(assemble_case_params(engine_type='feature', exec_type='field_batch'))

    # v = {
    #     "invoker": "5",
    #     "uid": 3000001,
    #     "orderId": "10",
    #     "fieldNameList": [
    #         "kj_no_script_feature_test_automation_integer"
    #     ]
    # }
    # print(eval(str(v)))