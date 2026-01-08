# -*- coding: utf-8 -*-
"""
# @File    : feature_platform_exec.py
# @Date    : 2025-06-20
# @Author  : jeremyzhai
"""

import os
from common.rpcAction import BaseRpc
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data
from utils.handle_path import Base_Path
import inspect
from typing import Union
from datetime import datetime
import random
from assert_code.assert_decorators import schema_assert, data_assert, retry
import hashlib


class FeaturePlatform:
    def __init__(self, env, group='stable'):
        self.env = env
        self.group = group

    def _get_order_id(self, uid: Union[str, int]) -> str:
        """
        指定uid, 生成测试账号
        :param uid:支持传入int/str类型
        :return: str, order_id
            """
        # 获取当前日期并格式化为YYYYMMDD
        date_str = datetime.now().strftime('%Y%m%d')

        # 生成19位随机数字
        random_numbers = ''.join([str(random.randint(0, 9)) for _ in range(8)])

        # 取uid尾号后四位
        uid_tails = (str(uid))[-4:]

        # 拼接最终的字符串
        order_id = 'O' + date_str + random_numbers + uid_tails

        return order_id

    def _encrypt_credit_id(self, credit_id: Union[str, int]) -> str:
        """
        使用 MD5 加密身份证号
        :param credit_id: 身份证号字符串
        :return: MD5 加密后的十六进制字符串
        """
        # 判断身份证号是否为18位明文，是的话需要加密，否则认为是密文
        if len(credit_id) != 18:
            return credit_id

        # 创建 MD5 对象
        md5 = hashlib.md5()

        # 更新 MD5 对象的内容，需要将身份证号转换为字节
        md5.update(credit_id.encode('utf-8'))

        # 获取 MD5 加密后的十六进制字符串
        encrypted_credit_id = md5.hexdigest()

        return encrypted_credit_id

    def _generate_params(self, feature_info: dict) -> dict:
        """
        字段拉取接口入参组装，读取配置，生成指定格式接口入参
        :param feature_info: dict，字段相关信息
        :return: dict 返回接口调用入参
        """
        # 1，获取调用改方法的函数名
        func_name = inspect.stack()[1][3]
        #
        # # 2, 根据函数名读取yaml配置的流程入参格式
        # base_form = read_yaml_data(file_dir=os.path.join(Base_Path, r'config\feature_para_format.yaml'))[func_name]
        #
        # # 3, 获取uid相关信息，如果存在order_id以传入为准，否则随机生成
        # uid = feature_info['uid']
        # order_id = feature_info.get('order_id', self._get_order_id(uid))
        #
        # # 4, 组装接口入参, 替换值
        # base_form[0]['uid'] = uid
        # base_form[0]['orderId'] = order_id
        # if "macCode" in feature_info.keys():
        #     base_form[0]['macCode'] = feature_info['macCode']
        # if "creditId" in feature_info.keys():
        #     base_form[0]['creditId'] = feature_info['creditId']
        #     # self._encrypt_credit_id(feature_info['creditId'])
        # base_form[0]['fieldNameList'] = feature_info['fieldNameList']

        base_form = [feature_info]
        base_form[0]['invoker'] = "1218"
        base_form[0]['appSecret'] = "ZR7wwC0vPgs4Lstn"
        log.info(f"{func_name}: {base_form}")

        # 5, 拼接全部关联参数
        reformed_data = {
            "env": self.env,
            "group": self.group,
            # "uid": uid,
            # "order_id": order_id,
            "input_data": base_form
        }
        return reformed_data

    @schema_assert
    def execute_field_batch_compute(self, feature_info: dict) -> dict:
        """
        授信代理层-字段获取接口
        :param feature_info: dict，字段相关信息
        :return: 返回字段拉取结果和相关信息
        """
        reformed_data = self._generate_params(feature_info=feature_info)

        data = {
            'interface': 'com.fenqile.anti_fraud.field_computing.service.FieldBatchComputeService',
            'method': 'compute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【字段拉取--授信代理层】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def execute_ruleengine_proxy_compute(self, feature_info: dict) -> dict:
        """
        交易代理层-字段获取接口
        :param feature_info: dict，字段相关信息
        :return: 返回字段拉取结果和相关信息
        """
        reformed_data = self._generate_params(feature_info=feature_info)

        data = {
            'interface': 'com.fenqile.anti_fraud.field_computing.ruleengine_proxy.service.RuleengineProxyFieldComputingService',
            'method': 'compute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【字段拉取--交易代理层】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def execute_simulate_proxy_compute(self, feature_info: dict) -> dict:
        """
        仿真代理层-字段获取接口
        :param feature_info: dict，字段相关信息
        :return: 返回字段拉取结果和相关信息
        """
        reformed_data = self._generate_params(feature_info=feature_info)

        data = {
            'interface': 'com.fenqile.anti_fraud.field_computing.simulate_proxy.service.SimulateProxyFieldComputingService',
            'method': 'compute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【字段拉取--仿真代理层】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def execute_business_proxy_compute(self, feature_info: dict) -> dict:
        """
        业务代理层-字段获取接口
        :param feature_info: dict，字段相关信息
        :return: 返回字段拉取结果和相关信息
        """
        reformed_data = self._generate_params(feature_info=feature_info)

        data = {
            'interface': 'com.fenqile.anti_fraud.field_computing.business_proxy.service.BusinessProxyFieldComputingService',
            'method': 'compute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【字段拉取--业务代理层】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def execute_offline_proxy_compute(self, feature_info: dict) -> dict:
        """
        离线代理层-字段获取接口
        :param feature_info: dict，字段相关信息
        :return: 返回字段拉取结果和相关信息
        """
        reformed_data = self._generate_params(feature_info=feature_info)

        data = {
            'interface': 'com.fenqile.anti_fraud.field_computing.offline_proxy.service.OfflineProxyFieldComputingService',
            'method': 'compute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【字段拉取--离线代理层】')
        # print(type(reformed_data), reformed_data)

        return reformed_data


if __name__ == '__main__':
    feature_info = {
        "uid": "3201279",
        "orderId": "O20250512029866600472",
        "macCode": "R2",
        "creditId": "161C419883E2F4F473D3305C98E14474",
        "fieldNameList": [
            "junhong_script_feature_test_long",
            "junhong_script_feature_test_long_double"
        ]
    }
    fp = FeaturePlatform(env='stable', group='stable')
    # fp.execute_field_batch_compute(feature_info=feature_info)
    # fp.execute_ruleengine_proxy_compute(feature_info=feature_info)
    # fp.execute_simulate_proxy_compute(feature_info=feature_info)
    # fp.execute_business_proxy_compute(feature_info=feature_info)
    fp.execute_offline_proxy_compute(feature_info=feature_info)
