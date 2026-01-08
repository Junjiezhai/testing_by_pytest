# -*- coding: utf-8 -*-
"""
# @File    : process_engine_exec.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""
import os
from common.rpcAction import BaseRpc
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data
from utils.handle_path import Base_Path
from utils.handle_instanceid import generate_instance_id
import inspect
from typing import Union
from datetime import datetime
import random
from assert_code.assert_decorators import schema_assert, data_assert, retry


class ProcessEngine:
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

    def _get_process_attr_by_id(self, process_id: str) -> dict:
        """
        根据流程id获取流程相关信息
        :param process_id:
        :return:
        """
        data = {
            'interface': 'com.fenqile.process.engine.console.service.process.ProcessQueryService',
            'method': 'queryOnlineEdition',
            'env': self.env,
            'group': self.group,
            'params': [f"{process_id}"]
        }
        res = BaseRpc.exec_rpc(data, desc='【获取流程相关信息】', print_res=False)

        process_info = {
            'editionId': res.get("editionId", ""),
            'bizType': res.get('bizType', ""),
            'creditCardType': res.get('creditCardType', ""),
            'pricingBusinessScene': res.get("pricingBusinessScene", ""),
            'quotaType': res.get('quotaType', ""),
            'processSceneType': res.get('sceneType', "")
        }
        # print(type(process_info), process_info)
        return process_info

    def _generate_params(self, process_info: dict) -> dict:
        """
        流程决策接口入参组装，读取配置，生成指定格式接口入参
        :param process_info: dict，流程相关信息
        :return: dict 返回决策接口调用入参
        """
        # 1，获取调用改方法的函数名
        func_name = inspect.stack()[1][3]

        # 2, 根据函数名读取yaml配置的流程入参格式
        base_form = read_yaml_data(file_dir=os.path.join(Base_Path, r'config\process_para_format.yaml'))[func_name]

        # 3, 获取uid和process_id
        uid = process_info['uid']
        process_id = process_info['processId']
        process_attr = self._get_process_attr_by_id(process_id=process_id)
        order_id = self._get_order_id(uid)
        instance_id = generate_instance_id(uid)

        # 4, 组装接口入参, 替换值
        base_form[0]['uid'] = uid
        base_form[0]['instanceId'] = instance_id
        base_form[0]['processId'] = process_id
        base_form[0]['version'] = process_attr['editionId']
        base_form[0]['inputs']['orderId'] = order_id
        base_form[0]['inputs']['processSceneType'] = process_attr['processSceneType']
        base_form[0]['inputs']['creditCardType'] = process_attr['creditCardType']
        base_form[0]['inputs']['quotaType'] = process_attr['quotaType']
        base_form[0]['inputs']['fieldSet'] = process_info['fieldSet']
        # 批跑接口透传批次号，暂设置为instance—id
        if "batchId" in base_form[0]['inputs'].keys():
            base_form[0]['inputs']['batchId'] = instance_id

        log.info(f"{func_name}: {base_form}")

        # 5, 拼接全部关联参数
        reformed_data = {
            "env": self.env,
            "group": self.group,
            "uid": uid,
            "process_id": process_id,
            "order_id": order_id,
            "instance_id": instance_id,
            "input_data": base_form
        }
        return reformed_data

    # @data_assert
    @schema_assert
    def execute_online(self, process_info: dict) -> dict:
        """
        在线实时决策接口
        :param process_info: dict，流程相关信息
        :return: 返回决策结果和相关信息，包含res, uid, orderid, processid 和instanceid
        """
        reformed_data = self._generate_params(process_info=process_info)

        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessService',
            'method': 'execute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【流程引擎--在线实时决策】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_online_exec_res(self, instance_id: str) -> dict:
        """
        查询在线决策结果
        :param instance_id: str
        :return: dict
        """
        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessService',
            'method': 'query',
            'env': self.env,
            'group': self.group,
            'params': [f'{instance_id}']
        }
        res = BaseRpc.exec_rpc(data, desc='【流程引擎--在线实时决策结果查询】')

        return res

    # @data_assert
    @schema_assert
    def execute_ec_online(self, process_info: dict) -> dict:
        """
        电商集群在线实时决策接口
        :param process_info: dict，流程相关信息
        :return: 返回决策结果和相关信息，包含res, uid, orderid, processid 和instanceid
        """
        reformed_data = self._generate_params(process_info=process_info)

        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessEcService',
            'method': 'execute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【流程引擎--电商在线实时决策】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_ec_online_exec_res(self, instance_id: str) -> dict:
        """
        查询在线决策结果
        :param instance_id: str
        :return: dict
        """
        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessEcService',
            'method': 'query',
            'env': self.env,
            'group': self.group,
            'params': [f'{instance_id}']
        }
        res = BaseRpc.exec_rpc(data, desc='【流程引擎--电商在线实时决策结果查询】')

        return res

    # @data_assert
    @schema_assert
    def execute_batch(self, process_info: dict) -> dict:
        """
        批跑决策接口
        :param process_info: dict，流程相关信息
        :return: 返回决策结果和相关信息，包含res, uid, orderid, processid 和instanceid
        """
        reformed_data = self._generate_params(process_info=process_info)

        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessBatchService',
            'method': 'execute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【流程引擎--离线批跑决策】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_batch_exec_res(self, instance_id: str) -> dict:
        """
        离线批跑决策结果
        :param instance_id: str
        :return: dict
        """
        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessBatchService',
            'method': 'query',
            'env': self.env,
            'group': self.group,
            'params': [f'{instance_id}']
        }
        res = BaseRpc.exec_rpc(data, desc='【流程引擎--离线批跑决策结果查询】')

        return res

    # @data_assert
    @schema_assert
    def execute_simulate(self, process_info: dict) -> dict:
        """
        仿真决策接口
        :param process_info: dict，流程相关信息
        :return: 返回决策结果和相关信息，包含res, uid, orderid, processid 和instanceid
        """
        reformed_data = self._generate_params(process_info=process_info)

        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessSimulateService',
            'method': 'execute',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【流程引擎--仿真测试决策】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_simulate_exec_res(self, instance_id: str) -> dict:
        """
        仿真测试决策结果
        :param instance_id: str
        :return: dict
        """
        data = {
            'interface': 'com.fenqile.process.engine.client.service.ProcessSimulateService',
            'method': 'query',
            'env': self.env,
            'group': self.group,
            'params': [f'{instance_id}']
        }
        res = BaseRpc.exec_rpc(data, desc='【流程引擎--仿真测试决策结果查询】')

        return res


if __name__ == '__main__':
    # process_info = {"processId": "SP00000330", "uid": "3117951",
    #                 "fieldSet": {"all_user_moa": 10, "total_amount": 520}}
    # pe = ProcessEngine(env='mxg_stable', group='project_109110229')
    # pe.execute_online(process_info=process_info)

    # # mock流程入参
    # from common.riskMock import RiskMock
    #
    # mock_req = {
    #     "approval_result": "0",
    #     "cause": [""],
    #     "disposal_codes": "",
    #     "tag_codes": "",
    #     "untag_codes": [],
    #     "credit_extra_data": {},
    #     "offer_code":100,
    #     "price": 21,
    #     "max_period": 18,
    #     "min_period": 3,
    #     "credit_limit": 8000,
    #     "credit_cash": 8000
    # }
    # # mock_req= {
    # #     "approval_result": "0",
    # #     "cause": [""],
    # #     "disposal_codes": "",
    # #     "tag_codes": "",
    # #     "untag_codes": [],
    # #     "credit_extra_data": {},
    # #     "offer_code":102,
    # #     "offer_status":2,
    # #     "price": 0,
    # #     "max_period": 1,
    # #     "min_period": 1,
    # #     "credit_limit": 7000,
    # #     "credit_cash": 7000,
    # #     "effective_end_time":"20241130"
    # # }
    # RiskMock('stable').process_mock_v2(uid='3125163', process_id='SP00000504', mock_req=mock_req)
    #
    # # 执行在线实时流程决策
    # # process_info = {
    # #     "uid": "4085322",
    # #     "processId": "P00000297",
    # #     "fieldSet": {}
    # # }
    process_info = {
        "uid": "4089534",
        "processId": "P00000193",
        "fieldSet": {
            # "user_all_credit_tag_code": "QKCJJLJS",
            # "repeatcreit_highpass_flag": "0",
            # "fif_wld_cxs_all": 1,
            # "new_user_sub_flag": 31
        }
    }
    # pe = ProcessEngine(env='stable', group='stable')
    pe = ProcessEngine(env='pre', group='default')

    # pe.execute_online(process_info=process_info)
    pe.execute_batch(process_info=process_info)
    # # pe.query_online_exec_res(instance_id='I2024110849268524750529134080302')
    #
    # # # DB数据查看
    # from common.dbAction import quota_test_credit
    #
    # # quota_test_credit(uid=process_info['uid'])
