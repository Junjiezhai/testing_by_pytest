# -*- coding: utf-8 -*-
'''
# @File    : assert_decorators.py
# @Date    : 2024-08-03
# @Author  : jeremyzhai
'''
import json, os
import time
from functools import wraps
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from utils.handle_yaml import read_yaml_data
from utils.handle_log import log
from utils.handle_path import Base_Path
from common.dbAction import DbAction
from assert_code.assertAction import camel_to_db_res, AssertAction
from datetime import datetime


def schema_assert(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 使用 __qualname__ 获取完整的函数名，包括类名
        full_function_name = func.__qualname__
        class_name = full_function_name.split('.')[0]
        func_name = full_function_name.split('.')[-1]

        # print(f"Class name: {class_name}")
        # print(f"Function name: {func_name}")

        try:
            # 调用原始函数
            exec_res = func(*args, **kwargs)
            output_data = json.dumps(exec_res['output_data'])
            # print("接口调用出参：", type(output_data), output_data)

            # 根据函数名读取yaml配置的流程决策出参格式
            # output_schema = read_yaml_data(file_dir=r'C:\Users\jeremyzhai\Desktop\整理归纳文档\python_for_jeremy'
            #                                         r'\making_decison_test\config\execute_res_schema.yaml')[class_name][func_name]
            output_schema = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_schema.yaml'))[class_name][
                    func_name]
            # print(type(output_schema), output_schema)

            # 执行格式断言, 验证 JSON 数据
            validate(instance=json.loads(output_data), schema=output_schema)
            log.info(f"[{class_name}--{func_name}]: 出参结构断言通过！")
            assert True

            exec_res['class_name'] = class_name
            exec_res['func_name'] = func_name

            # print(type(exec_res), exec_res)
            return exec_res

        except ValidationError as e:
            log.error(f"[{class_name}--{func_name}]: 出参结构断言失败，原因为：{e.message}")
            assert False

    return wrapper


def data_assert(func):
    @wraps(func)
    def wrapper(*args, **kwargs):

        try:
            # 调用原始函数
            exec_res = func(*args, **kwargs)

            class_name = exec_res.get('class_name')
            func_name = exec_res.get('func_name')

            # print(f"Class name: {class_name}")
            # print(f"Function name: {func_name}")

            output_data = camel_to_db_res(exec_res['output_data'])
            # print("接口调用出参：", type(output_data), output_data)
            #
            # 根据函数名读取yaml配置的流程决策出参格式
            db_config = read_yaml_data(file_dir='../config/execute_res_db_assert.yaml')[class_name][func_name]
            # print(type(db_config), db_config)

            # 执行数据断言, 验证 接口出参和库表数据一致性
            finstance_id = exec_res['instance_id']
            db_info = db_config['db_info']
            assert_rules = db_config['assert_rules']
            db_info['condition'] = str(db_config['db_info'].get('condition')).replace('{}', f'{finstance_id}')
            # processenginedb = {
            #     'sql_type': 'select',
            #     'target_table': "process_instance_##_db.t_process_instance_result_#",
            #     'condition': f"finstance_id = '{finstance_id}'",
            #     'key_indicator': 'finstance_id',
            #     'target_column': "*",
            #     'order_by': False,
            #     'ret_col': ['Fcode', 'Fstatus', 'Fdata']
            # }
            # print(db_info)

            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                print(type(db_res), db_res)

            try:
                AssertAction.base_assert(res=output_data, exp=db_res)
                # value_assert(data=db_res, assert_rules=assert_rules, exp=case_res) # 断言每一条用例结果
                log.info(f"[{class_name}--{func_name}]: 数据断言通过！")
                assert True
            except Exception as e:
                log.info(f"[{class_name}--{func_name}]: 数据断言失败！异常为：{e}")
                assert False

            # print(type(exec_res), exec_res)
            return exec_res

        except ValidationError as e:
            log.error(f"决策出参数据库表断言失败，原因为：{e.message}")
            assert False

    return wrapper


# 决策结果查询接口重试
def retry(max_attempts=3, delay=1):
    def decorator(func):
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    res = func(*args, **kwargs)
                    if res:  # 查询结果不为空
                        return res
                    else:
                        raise
                except Exception as e:
                    log.warning(f"{e} --|-- Attempt {attempts + 1}: failed. Retrying in {delay} seconds.")
                    attempts += 1
                    time.sleep(delay)

            log.warning(f"{func.__name__} exceed max retry attempts!")
            raise Exception(f"接口返回值为空，无实际结果！！！")

        return wrapper

    return decorator


def post_loan_touch_assert(func):
    @wraps(func)
    def wrapper(*args, **kwargs):

        try:
            # 调用原始函数
            exec_res = func(*args, **kwargs)

            # print(exec_res)

            # db参数核对
            time.sleep(1)  # 强制沉睡等待
            env = 'stable'
            # print('################  催收发短记录表(CollectionDB)   ##########################')
            t_send_res = {
                'sql_type': 'select',
                'target_table': f"collection_send_2025_db.t_collection_send_msg_record_{datetime.now().strftime('%m%d')}",
                'condition': f"Fuid = '{exec_res['uid']}' and Fsend_code='{exec_res['send_code']}'",# and Fqueue_code='{query_info['queue_code']}'",
                # 'key_indicator': 'uid',
                'target_column': "*",
                'show': True,
                'order_by': True,
                'limits': 1
            }
            with DbAction(instance_name='CollectionDB', env=env) as CollectionDB:
                log.info('################  催收发短记录表(CollectionDB)   ##########################')
                CollectionDB.send_sql_fetch_res(inData=t_send_res)

            # output_data = camel_to_db_res(exec_res['output_data'])
            # # print("接口调用出参：", type(output_data), output_data)
            # #
            # # 根据函数名读取yaml配置的流程决策出参格式
            # db_config = read_yaml_data(file_dir='../config/execute_res_db_assert.yaml')[class_name][func_name]
            # # print(type(db_config), db_config)
            #
            # # 执行数据断言, 验证 接口出参和库表数据一致性
            # finstance_id = exec_res['instance_id']
            # db_info = db_config['db_info']
            # assert_rules = db_config['assert_rules']
            # db_info['condition'] = str(db_config['db_info'].get('condition')).replace('{}', f'{finstance_id}')
            # # processenginedb = {
            # #     'sql_type': 'select',
            # #     'target_table': "process_instance_##_db.t_process_instance_result_#",
            # #     'condition': f"finstance_id = '{finstance_id}'",
            # #     'key_indicator': 'finstance_id',
            # #     'target_column': "*",
            # #     'order_by': False,
            # #     'ret_col': ['Fcode', 'Fstatus', 'Fdata']
            # # }
            # # print(db_info)
            #
            # with DbAction(instance_name=db_config['instance_name']) as db_conn:
            #     db_res = db_conn.send_sql_fetch_res(inData=db_info)
            #     print(type(db_res), db_res)
            #
            # try:
            #     AssertAction.base_assert(res=output_data, exp=db_res)
            #     # value_assert(data=db_res, assert_rules=assert_rules, exp=case_res) # 断言每一条用例结果
            #     log.info(f"[{class_name}--{func_name}]: 数据断言通过！")
            #     assert True
            # except Exception as e:
            #     log.info(f"[{class_name}--{func_name}]: 数据断言失败！异常为：{e}")
            #     assert False

            # print(type(exec_res), exec_res)
            return exec_res

        except ValidationError as e:
            log.error(f"数据库表断言失败，原因为：{e.message}")
            assert False

    return wrapper
