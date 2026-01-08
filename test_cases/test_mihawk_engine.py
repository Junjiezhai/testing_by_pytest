# -*- coding: utf-8 -*-
"""
# @File    : test_mihawk_engine.py
# @Date    : 2024-08-16
# @Author  : jeremyzhai
"""

import os
import time

from script_code.mihawk_engine_exec import MihawkEngine
from utils.handle_yaml import read_yaml_data
from utils.handle_log import log
from utils.handle_path import Base_Path
from common.dbAction import DbAction
from common.ckAction import CkAction
from assert_code.assertAction import camel_to_db_res, AssertAction, db_res_str_transfer

import pytest
import allure
from utils.handle_cases import assemble_case_params, get_case_desc

YN_WAIT_TIME = 90


@allure.epic('决策引擎（米霍克）')  # 一级标签
@pytest.mark.package
class TestMihawkEngine:
    @allure.feature("在线决策")
    @allure.story('流程决策')
    # @allure.severity("critical")
    # @allure.tag("登录", "认证")
    # @allure.link("https://example.com/issues/123", name="相关需求文档")
    @pytest.mark.package_online_exec_rcflow_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='online_exec_rcflow_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='online_exec_rcflow_decision'))
    def test_online_exec_rcflow_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】在线决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)在线决策--米霍克流程决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.online_exec_rcflow_decision(package_info=package_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_rcflow_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_rcflow_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id'] if exec_res['decision_node_id'] else '-1'
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, node_id)

            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        elif env == 'yn_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_rcflow_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id'] if exec_res['decision_node_id'] else '-1'
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq, node_id)

            with CkAction(env='yn_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
                ck_res = db_res_str_transfer(db_res=ck_res)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("在线决策")
    @allure.story('节点决策')
    @pytest.mark.package_online_exec_make_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='online_exec_make_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='online_exec_make_decision'))
    def test_online_exec_make_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】在线决策 --- 米霍克节点决策
        :param package_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)在线决策--米霍克节点决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.online_exec_make_decision(package_info=package_info)

        # 兼容印尼环境ck延迟60s更新
        time.sleep(YN_WAIT_TIME)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_make_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_make_decision"]
            seq, decision_node_id = exec_res['seq'], exec_res['decision_node_id']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, decision_node_id)
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        elif env == 'yn_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_make_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq, node_id)

            with CkAction(env='yn_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        elif env == 'mxg_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_make_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq, node_id)

            with CkAction(env='mxg_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("在线决策")
    @allure.story('乐包决策')
    @pytest.mark.package_online_exec_package_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='online_exec_package_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='online_exec_package_decision'))
    def test_online_exec_package_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】在线决策 --- 米霍克乐包决策
        :param package_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)在线决策--米霍克乐包决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.online_exec_package_decision(package_info=package_info)

        # 兼容印尼环境ck延迟60s更新
        time.sleep(YN_WAIT_TIME)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_package_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_package_decision"]
            seq = exec_res['seq']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq)
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        elif env == 'yn_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_package_decision"]

            seq = exec_res['seq']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq)

            with CkAction(env='yn_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        elif env == 'mxg_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "online_exec_package_decision"]

            seq = exec_res['seq']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq)

            with CkAction(env='mxg_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("电商在线决策")
    @allure.story('流程决策')
    @pytest.mark.package_ec_online_exec_rcflow_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='ec_online_exec_rcflow_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='ec_online_exec_rcflow_decision'))
    def test_ec_online_exec_rcflow_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】电商在线决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)电商在线决策--米霍克流程决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.ec_online_exec_rcflow_decision(package_info=package_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_rcflow_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "ec_online_exec_rcflow_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id'] if exec_res['decision_node_id'] else '-1'
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, node_id)

            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("电商在线决策")
    @allure.story('节点决策')
    @pytest.mark.package_ec_online_exec_make_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='ec_online_exec_make_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='ec_online_exec_make_decision'))
    def test_ec_online_exec_make_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】电商在线决策 --- 米霍克节点决策
        :param package_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)电商在线决策--米霍克节点决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.ec_online_exec_make_decision(package_info=package_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_make_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "ec_online_exec_make_decision"]
            seq, decision_node_id = exec_res['seq'], exec_res['decision_node_id']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, decision_node_id)
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("电商在线决策")
    @allure.story('乐包决策')
    @pytest.mark.package_ec_online_exec_package_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='ec_online_exec_package_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='ec_online_exec_package_decision'))
    def test_ec_online_exec_package_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】电商在线决策 --- 米霍克乐包决策
        :param package_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)电商在线决策--米霍克乐包决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.ec_online_exec_package_decision(package_info=package_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_package_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "ec_online_exec_package_decision"]
            seq = exec_res['seq']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq)
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("批跑决策")
    @allure.story('流程决策')
    @pytest.mark.package_batch_exec_rcflow_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='batch_exec_rcflow_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='batch_exec_rcflow_decision'))
    def test_batch_exec_rcflow_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】批跑决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)批跑决策--米霍克流程决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.batch_exec_rcflow_decision(package_info=package_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_rcflow_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "batch_exec_rcflow_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id'] if exec_res['decision_node_id'] else '-1'
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, node_id)

            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")
        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("批跑决策")
    @allure.story('节点决策')
    @pytest.mark.package_batch_exec_make_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='batch_exec_make_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='batch_exec_make_decision'))
    def test_batch_exec_make_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】批跑决策 --- 米霍克节点决策
        :param package_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)批跑决策--米霍克节点决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.batch_exec_make_decision(package_info=package_info)

        # 兼容印尼环境ck延迟60s更新
        # time.sleep(YN_WAIT_TIME)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_make_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "batch_exec_make_decision"]
            seq, decision_node_id = exec_res['seq'], exec_res['decision_node_id']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, decision_node_id)
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        elif env == 'yn_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "batch_exec_make_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq, node_id)

            with CkAction(env='yn_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("批跑决策")
    @allure.story('乐包决策')
    @pytest.mark.package_batch_exec_package_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='batch_exec_package_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='batch_exec_package_decision'))
    def test_batch_exec_package_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】批跑决策 --- 米霍克乐包决策
        :param package_info: dict，流程相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)批跑决策--米霍克乐包决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.batch_exec_package_decision(package_info=package_info)

        # 兼容印尼环境ck延迟60s更新
        # time.sleep(YN_WAIT_TIME)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_online_package_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "batch_exec_package_decision"]
            seq = exec_res['seq']
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq)
            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")

        elif env == 'yn_stable':
            # 4, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】CK信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "batch_exec_package_decision"]

            seq = exec_res['seq']
            ck_info = db_config['ck_info']
            ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq)

            with CkAction(env='yn_stable') as ck_engine:
                ck_res = ck_engine.exec_query(ck_info=ck_info)
            log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")

            # 比对ck结果和用例预期结果
            AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")

        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")

    @allure.feature("仿真决策")
    @allure.story('流程决策')
    @pytest.mark.package_simulate_exec_rcflow_decision
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='package', exec_type='simulate_exec_rcflow_decision')),
                             ids=get_case_desc(engine_type='package', exec_type='simulate_exec_rcflow_decision'))
    def test_simulate_exec_rcflow_decision(self, package_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【测试】仿真决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return:
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)仿真决策--米霍克流程决策 =============\n")
        # 1, 执行决策（出参结构断言）
        me = MihawkEngine(env=env, group=group)
        exec_res = me.simulate_exec_rcflow_decision(package_info=package_info)

        log.info(f"\n============== 【当前环境：env={env}, group={group}】决策结果信息查询 =============\n")
        # 2, 查询决策结果
        query_res = me.query_simulate_rcflow_decision_res(package_info=exec_res)
        query_res = camel_to_db_res(query_res)  # 转换接口出参为数据库字段命名格式
        log.info(f"接口查询结果：{type(query_res)}, {query_res}")

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=query_res, assert_rules=assert_rules, desc="接口查询结果")

        if env == 'stable':
            # 3, 根据函数名读取yaml配置的决策结果查询库表信息
            log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
            db_config = \
                read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
                    "simulate_exec_rcflow_decision"]

            seq = exec_res['seq']
            node_id = exec_res['decision_node_id'] if exec_res['decision_node_id'] else '-1'
            db_info = db_config['db_info']
            db_info['condition'] = str(db_config['db_info'].get('condition')).format(seq, node_id)

            with DbAction(instance_name=db_config['instance_name']) as db_conn:
                db_res = db_conn.send_sql_fetch_res(inData=db_info)
                db_res = db_res_str_transfer(db_res=db_res)
            log.info(f"DB查询结果: {type(db_res)}, {db_res}")

            # 比对db结果和用例预期结果
            AssertAction.value_assert(data=db_res, assert_rules=assert_rules, desc="DB查询结果")
        else:
            log.warning("非stable环境，无法直连数据库，不做DB信息查询断言！！！")
