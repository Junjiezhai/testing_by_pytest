# -*- coding: utf-8 -*-
"""
# @File    : mihawk_engine_exec.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""

from common.rpcAction import BaseRpc
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data
from utils.handle_path import Base_Path
from utils.handle_instanceid import generate_instance_id
import os
import inspect
from typing import Union
from datetime import datetime
import random
from assert_code.assert_decorators import schema_assert, retry


class MihawkEngine:
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

    def _generate_params(self, package_info: dict) -> dict:
        """
        米霍克决策接口入参组装，读取配置，生成指定格式接口入参
        :param package_info: dict，乐包相关信息
        :param field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: dict 返回决策接口调用入参
        """
        # 1，获取调用改方法的函数名
        func_name = inspect.stack()[1][3]

        # 2, 根据函数名读取yaml配置的流程入参格式
        base_form = read_yaml_data(file_dir=os.path.join(Base_Path, r'config\package_para_format.yaml'))[func_name]

        # 3, 判断函数类型，获取特定参数
        rcflow_id = package_info['rcFlowId']
        base_form[0]['rcFlowId'] = rcflow_id
        if 'make_decision' in func_name:
            base_form[0]['decisionNodeId'] = package_info['decisionNodeId']
            base_form[0]['packageSceneType'] = package_info.get('packageSceneType', 'trade')
        elif 'package_decision' in func_name:
            base_form[0]['packageId'] = package_info['packageId']

        # 4, 组装接口入参, 替换值
        uid = package_info['uid']
        order_id = self._get_order_id(uid)
        seq = generate_instance_id(uid)
        base_form[0]['uid'] = package_info['uid']
        base_form[0]['seq'] = seq
        base_form[0]['orderId'] = order_id
        base_form[0]['fieldSet'] = package_info.get('fieldSet', dict())

        log.info(f"{func_name}: {base_form}")

        # 5, 拼接全部关联参数
        reformed_data = {
            "uid": uid,
            "rcflow_id": rcflow_id,
            "seq": seq,
            "order_id": order_id,
            "decision_node_id": base_form[0].get("decisionNodeId", package_info.get('decisionNodeId', "")),
            "package_id": base_form[0].get("packageId", ""),
            "package_scene_type": base_form[0].get("packageSceneType", ""),
            "input_data": base_form
        }
        return reformed_data

    @schema_assert
    def online_exec_rcflow_decision(self, package_info: dict) -> dict:
        """
        在线决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.RcFlowDecisionService',
            'method': 'rcFlowDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-在线】--流程决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def ec_online_exec_rcflow_decision(self, package_info: dict) -> dict:
        """
        电商在线决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.RcFlowDecisionServiceEC',
            'method': 'rcFlowDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-电商在线】--流程决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_online_rcflow_decision_res(self, package_info: dict) -> dict:
        """
        查询流程决策结果
        :param package_info: 乐包入参信息，包含uid，order_id,seq等
        :return: dict
        """
        seq = package_info.get('seq')
        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.water.service.OnlineDecisionWaterService',
            'method': 'queryStrategyNodeDecision',
            'env': self.env,
            'group': self.group,
            'params': [{
                "orderId": package_info.get('order_id'),
                "uid": package_info.get('uid'),
                "seq": seq,
                "nodeId": package_info.get('decision_node_id') if package_info.get('decision_node_id') else "-1",
                "needInput": True,
                "needOutput": True,
                "createTime": f"{seq[1:5]}-{seq[5:7]}-{seq[7:9]} 00:00:00"
            }]
        }
        res = BaseRpc.exec_rpc(data, desc='【米霍克决策-在线】流程决策结果查询')

        return res

    @schema_assert
    def online_exec_make_decision(self, package_info: dict) -> dict:
        """
        在线决策 --- 米霍克节点决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.CommonSelfDecisionService',
            'method': 'makeDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-在线】--节点决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def ec_online_exec_make_decision(self, package_info: dict) -> dict:
        """
        电商在线决策 --- 米霍克节点决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.CommonSelfDecisionServiceEC',
            'method': 'makeDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-电商在线】--节点决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_online_make_decision_res(self, package_info: dict) -> dict:
        """
        查询节点决策结果
        :param package_info: 乐包入参信息，包含uid，order_id,seq等
        :return: dict
        """
        seq = package_info.get('seq')
        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.water.service.OnlineDecisionWaterService',
            'method': 'queryStrategyNodeDecision',
            'env': self.env,
            'group': self.group,
            'params': [{
                "orderId": package_info.get('order_id'),
                "uid": package_info.get('uid'),
                "seq": seq,
                "nodeId": package_info.get('decision_node_id'),
                "needInput": True,
                "needOutput": True,
                "createTime": f"{seq[1:5]}-{seq[5:7]}-{seq[7:9]} 00:00:00"
            }]
        }
        res = BaseRpc.exec_rpc(data, desc='【米霍克决策-在线】节点决策结果查询')

        return res

    @schema_assert
    def online_exec_package_decision(self, package_info: dict) -> dict:
        """
        在线决策 --- 米霍克乐包决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.PackageDecisionService',
            'method': 'packageDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-在线】--乐包决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def ec_online_exec_package_decision(self, package_info: dict) -> dict:
        """
        在线决策 --- 米霍克乐包决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.PackageDecisionServiceEC',
            'method': 'packageDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-电商在线】--乐包决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_online_package_decision_res(self, package_info: dict) -> dict:
        """
        查询乐包决策结果
        :param package_info: 乐包入参信息，包含uid，order_id,seq等
        :return: dict
        """
        seq = package_info.get('seq')
        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.water.service.OnlineDecisionWaterService',
            'method': 'queryStrategyNodeDecision',
            'env': self.env,
            'group': self.group,
            'params': [{
                "orderId": package_info.get('order_id'),
                "uid": package_info.get('uid'),
                "seq": seq,
                "nodeId": "-1",
                "needInput": True,
                "needOutput": True,
                "createTime": f"{seq[1:5]}-{seq[5:7]}-{seq[7:9]} 00:00:00"
            }]
        }
        res = BaseRpc.exec_rpc(data, desc='【米霍克决策-在线】节点决策结果查询')

        return res

    @schema_assert
    def batch_exec_rcflow_decision(self, package_info: dict) -> dict:
        """
        批跑决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.RcFlowDecisionServiceBatch',
            'method': 'rcFlowDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-批跑】--流程决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def batch_exec_make_decision(self, package_info: dict) -> dict:
        """
        批跑决策 --- 米霍克节点决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.CommonSelfDecisionServiceBatch',
            'method': 'makeDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-批跑】--节点决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def batch_exec_package_decision(self, package_info: dict) -> dict:
        """
        批跑决策 --- 米霍克乐包决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.PackageDecisionServiceBatch',
            'method': 'packageDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-批跑】--乐包决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def simulate_exec_rcflow_decision(self, package_info: dict) -> dict:
        """
        仿真决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.RcFlowOfflineDecisionServiceSimulate',
            'method': 'rcFlowDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-仿真】--流程决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @retry(max_attempts=3, delay=1)
    def query_simulate_rcflow_decision_res(self, package_info: dict) -> dict:
        """
        查询流程仿真决策结果
        :param package_info: 乐包入参信息，包含uid，order_id,seq等
        :return: dict
        """
        seq = package_info.get('seq')
        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.water.service.OfflineDecisionWaterService',
            'method': 'queryStrategyNodeTestDecision',
            'env': self.env,
            'group': self.group,
            'params': [{
                "orderId": package_info.get('order_id'),
                "uid": package_info.get('uid'),
                "seq": seq,
                "nodeId": package_info.get('decision_node_id') if package_info.get('decision_node_id') else "-1",
                # "nodeId": "-1",
                "needInput": True,
                "needOutput": True,
                "createTime": f"{seq[1:5]}-{seq[5:7]}-{seq[7:9]} 00:00:00"
            }]
        }
        res = BaseRpc.exec_rpc(data, desc='【米霍克决策-仿真】流程决策结果查询')

        return res

    @schema_assert
    def simulate_exec_make_decision(self, package_info: dict) -> dict:
        """
        仿真决策 --- 米霍克节点决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.CommonOfflineSelfDecisionServiceSimulate',
            'method': 'makeDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-仿真】--节点决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @schema_assert
    def simulate_exec_package_decision(self, package_info: dict) -> dict:
        """
        在线决策 --- 米霍克流程决策
        :param package_info: dict，乐包相关信息, field_set: dict，流程入参（内容相关），对应接口入参字段fieldSet
        :return: 返回决策结果和相关信息，包含res, uid, orderid
        """
        reformed_data = self._generate_params(package_info=package_info)

        data = {
            'interface': 'com.fenqile.rc_comm.hawk.decision.dispatcher.service.PackageDecisionServiceSimulate',
            'method': 'packageOfflineDecision',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【米霍克决策-仿真】--乐包决策')
        # print(type(reformed_data), reformed_data)

        return reformed_data


if __name__ == '__main__':
    pe = MihawkEngine(env='stable', group='stable')
    # 流程决策
    package_info ={
        "rcFlowId": "3561",
        # "packageId": "2681",
        "uid": "3064473",
        "fieldSet": {
            "total_amount": 10
        }
    }

    # res = pe.online_exec_rcflow_decision(package_info=package_info)
    # pe.query_online_rcflow_decision_res(package_info=res)
    res = pe.batch_exec_rcflow_decision(package_info=package_info)
    # pe.batch_exec_rcflow_decision(package_info=package_info)
    # res = pe.simulate_exec_rcflow_decision(package_info=package_info)
    # pe.query_simulate_rcflow_decision_res(package_info=res)

    # 节点决策
    # package_info = {"rcFlowId": "SP00000326", "decisionNodeId": "285861", "packageSceneType": "trade", "uid": "3064471",
    #                 "fieldSet": {"total_amount":10}}
    # package_info = {
    #     "rcFlowId": "SP00000326",
    #     "decisionNodeId": "285861",
    #     "packageSceneType": "trade",
    #     "uid": "3064471",
    #     "fieldSet": {"total_amount":10}
    # }
    # pe.online_exec_make_decision(package_info=package_info)
    # pe.batch_exec_make_decision(package_info=package_info)
    # pe.simulate_exec_make_decision(package_info=package_info)

    # 乐包决策
    # package_info = {"rcFlowId": "SP00000326", "packageId": "2680", "uid": "3064471",
    #                 "fieldSet": {"total_amount": 10}}
    # pe.online_exec_package_decision(package_info=package_info)
    # pe.batch_exec_package_decision(package_info=package_info)
    # pe.simulate_exec_package_decision(package_info=package_info)

    # package_info= {
    #     "order_id":"O20241021692119264471",
    #     "uid":3064471,
    #     "seq": "I2024102120411151178001147894471",
    #     "decision_node_id": "-1",
    # }
    # res = pe.query_online_package_decision_res(package_info=package_info)
    # print(type(res), res)
