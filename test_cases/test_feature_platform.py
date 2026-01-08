# -*- coding: utf-8 -*-
"""
# @File    : test_feature_platform.py
# @Date    : 2025-06-20
# @Author  : jeremyzhai
"""
import os
import time

from script_code.feature_platform_exec import FeaturePlatform
from utils.handle_yaml import read_yaml_data
from utils.handle_log import log
from utils.handle_path import Base_Path
from assert_code.assertAction import camel_to_db_res, AssertAction, db_res_str_transfer

import pytest
import allure
from utils.handle_cases import assemble_case_params, get_case_desc


@allure.feature('特征平台')  # 一级标签
@pytest.mark.feature_platform
class TestFeaturePlatform:
    @allure.story('授信代理层')
    @pytest.mark.feature_field_batch
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='feature', exec_type='field_batch')),
                             ids=get_case_desc(engine_type='feature', exec_type='field_batch'))
    def test_execute_field_batch_compute(self, feature_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【授信代理层--字段拉取】
        :param feature_info: dict，字段相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)授信代理层--字段拉取 =============\n")
        # 执行字段拉取（出参结构断言）
        fp = FeaturePlatform(env=env, group=group)
        exec_res = fp.execute_field_batch_compute(feature_info=feature_info)

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=exec_res['output_data'], assert_rules=assert_rules, desc="接口返回结果")

    @allure.story('交易代理层')
    @pytest.mark.feature_ruleengine_proxy
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='feature', exec_type='ruleengine_proxy')),
                             ids=get_case_desc(engine_type='feature', exec_type='ruleengine_proxy'))
    def test_execute_ruleengine_proxy_compute(self, feature_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【交易代理层-字段获取】
        :param feature_info: dict，字段相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)交易代理层-字段获取 =============\n")
        # 执行字段拉取（出参结构断言）
        fp = FeaturePlatform(env=env, group=group)
        exec_res = fp.execute_ruleengine_proxy_compute(feature_info=feature_info)

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=exec_res['output_data'], assert_rules=assert_rules, desc="接口返回结果")

    @allure.story('仿真代理层')
    @pytest.mark.feature_simulate_proxy
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='feature', exec_type='simulate_proxy')),
                             ids=get_case_desc(engine_type='feature', exec_type='simulate_proxy'))
    def test_execute_simulate_proxy_compute(self, feature_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【仿真代理层-字段获取】
        :param feature_info: dict，字段相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)仿真代理层-字段获取 =============\n")
        # 执行字段拉取（出参结构断言）
        fp = FeaturePlatform(env=env, group=group)
        exec_res = fp.execute_simulate_proxy_compute(feature_info=feature_info)

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=exec_res['output_data'], assert_rules=assert_rules, desc="接口返回结果")

    @allure.story('业务代理层')
    @pytest.mark.feature_business_proxy
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='feature', exec_type='business_proxy')),
                             ids=get_case_desc(engine_type='feature', exec_type='business_proxy'))
    def test_execute_business_proxy_compute(self, feature_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【业务代理层-字段获取】
        :param feature_info: dict，字段相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)业务代理层-字段获取 =============\n")
        # 执行字段拉取（出参结构断言）
        fp = FeaturePlatform(env=env, group=group)
        exec_res = fp.execute_business_proxy_compute(feature_info=feature_info)

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=exec_res['output_data'], assert_rules=assert_rules, desc="接口返回结果")

    @allure.story('离线代理层')
    @pytest.mark.feature_offline_proxy
    @pytest.mark.parametrize(*(assemble_case_params(engine_type='feature', exec_type='offline_proxy')),
                             ids=get_case_desc(engine_type='feature', exec_type='offline_proxy'))
    def test_execute_offline_proxy_compute(self, feature_info: dict, assert_rules: dict, env: str, group: str) -> None:
        """
        【离线代理层-字段获取】
        :param feature_info: dict，字段相关信息
        :param env: str 环境标识
        :param group: str group标识
        :param assert_rules: dict, 预期结果
        :return: None
        """
        log.info(f"\n==============【当前环境：env={env}, group={group}】(测试)离线代理层-字段获取 =============\n")
        # 执行字段拉取（出参结构断言）
        fp = FeaturePlatform(env=env, group=group)
        exec_res = fp.execute_offline_proxy_compute(feature_info=feature_info)

        # 比对接口结果和用例预期结果
        AssertAction.value_assert(data=exec_res['output_data'], assert_rules=assert_rules, desc="接口返回结果")
