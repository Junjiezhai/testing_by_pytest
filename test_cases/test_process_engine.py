# -*- coding: utf-8 -*-
"""
# @File    : test_process_engine.py
# @Date    : 2024-08-13
# @Author  : jeremyzhai
"""
import os
import time

from script_code.process_engine_exec import ProcessEngine
from utils.handle_yaml import read_yaml_data
from utils.handle_log import log
from utils.handle_path import Base_Path
from common.dbAction import DbAction
from common.ckAction import CkAction
from assert_code.assertAction import camel_to_db_res, AssertAction, db_res_str_transfer

import pytest
import allure
from utils.handle_cases import assemble_case_params, get_case_desc

YN_WAIT_TIME = 180


@allure.feature('流程引擎')  # 一级标签
@pytest.mark.process
class TestProcessEngine:
    @allure.story('在线实时决策')
    @pytest.mark.process_online
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='process', exec_type='execute_online')),
                             ids=get_case_desc(engine_type='process', exec_type='execute_online'))
    def test_execute_online(self, process_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】流程引擎--在线实时决策
        :param process_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)流程引擎--在线实时决策 =============\n")
        # 1, 执行决策（出参结构断言）
        pe = ProcessEngine(env=env, group=group)
        exec_res = pe.execute_online(process_info=process_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = pe.query_online_exec_res(instance_id=exec_res['instance_id'])
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["ProcessEngine"][
                    "execute_online"]
            finstance_id = exec_res['instance_id']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).replace('{}', f'{finstance_id}')
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        elif env == 'yn_stable':  # 兼容印尼环境
            # 兼容印尼环境ck延迟60s更新
            time.sleep(YN_WAIT_TIME)

            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["ProcessEngine"][
                    "execute_online"]

            finstance_id = exec_res['instance_id']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(finstance_id)

            with CkAction(env='yn_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果, 非空即为通过
            for value in ck_res.values():
                assert value

        elif env == 'mxg_stable':  # 兼容墨西哥环境
            # 兼容印尼环境ck延迟60s更新
            time.sleep(YN_WAIT_TIME)

            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["ProcessEngine"][
                    "execute_online"]

            finstance_id = exec_res['instance_id']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(finstance_id)

            with CkAction(env='mxg_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果, 非空即为通过
            for value in ck_res.values():
                assert value

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.story('电商在线实时决策')
    @pytest.mark.process_ec_online
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='process', exec_type='execute_ec_online')),
                             ids=get_case_desc(engine_type='process', exec_type='execute_ec_online'))
    def test_execute_ec_online(self, process_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】流程引擎--电商集群在线实时决策
        :param process_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)流程引擎--电商在线实时决策 =============\n")
        # 1, 执行决策（出参结构断言）
        pe = ProcessEngine(env=env, group=group)
        exec_res = pe.execute_ec_online(process_info=process_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = pe.query_ec_online_exec_res(instance_id=exec_res['instance_id'])
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["ProcessEngine"][
                    "execute_ec_online"]
            finstance_id = exec_res['instance_id']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).replace('{}', f'{finstance_id}')
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.story('离线批跑决策')
    @pytest.mark.process_batch
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='process', exec_type='execute_batch')),
                             ids=get_case_desc(engine_type='process', exec_type='execute_batch'))
    def test_execute_batch(self, process_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】流程引擎--离线批跑决策
        :param process_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)流程引擎--在线实时决策 =============\n")
        # 1, 执行决策（出参结构断言）
        pe = ProcessEngine(env=env, group=group)
        exec_res = pe.execute_batch(process_info=process_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = pe.query_batch_exec_res(instance_id=exec_res['instance_id'])
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env=='stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["ProcessEngine"]["execute_batch"]
            finstance_id = exec_res['instance_id']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).replace('{}', f'{finstance_id}')
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")
        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")
