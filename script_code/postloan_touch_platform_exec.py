# -*- coding: utf-8 -*-
"""
# @File    : postloan_touch_platform_exec.py
# @Date    : 2025-07-09
# @Author  : jeremyzhai
"""

import os
import time

from common.rpcAction import BaseRpc
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data
from utils.handle_path import Base_Path
import inspect
from typing import Union
from datetime import datetime
from assert_code.assert_decorators import post_loan_touch_assert
from common.dbAction import DbAction
from common.postLoanAction import PostLoanPlat


class TouchPlatform:
    def __init__(self, env, group='stable'):
        self.env = env
        self.group = group

    def _generate_params(self, msg_info: dict) -> dict:
        """
        发短接口入参组装，读取配置，生成指定格式接口入参
        :param msg_info: dict，短信相关信息
        :return: dict 返回决策接口调用入参
        """
        # 5, 拼接全部关联参数
        reformed_data = {
            "env": self.env,
            "group": self.group,
            "input_data": [msg_info]
        }

        return reformed_data

    def query_msg_record_from_db(self, query_info: dict) -> None:
        """
        从db查询短信发送记录
        :param query_info: dict，db查询入参
        :return:
        """

        # print('################  催收发短记录表(CollectionDB)   ##########################')
        t_send_res = {
            'sql_type': 'select',
            'target_table': f"collection_send_2025_db.t_collection_send_msg_record_{datetime.now().strftime('%m%d')}",
            'condition': f"Fuid = '{query_info['uid']}' and Fsend_code='{query_info['send_code']}'",
            # and Fqueue_code='{query_info['queue_code']}'",
            # 'key_indicator': 'uid',
            'target_column': "*",
            'show': True,
            'order_by': True,
            'limits': query_info.get('limit', 100)
        }
        with DbAction(instance_name='CollectionDB', env=self.env) as CollectionDB:
            log.info('################  催收发短记录表(CollectionDB)   ##########################')
            CollectionDB.send_sql_fetch_res(inData=t_send_res)

    @post_loan_touch_assert
    def negotiate_repay_send_sms(self, msg_info: dict) -> dict:
        """
        协商还场景发短
        :param msg_info: 短信入参
        :return: str, msg_id 短信id
        """
        reformed_data = self._generate_params(msg_info=msg_info)

        data = {
            'interface': 'com.fenqile.credit.collection.service.send.CollectionSendService',
            'method': 'sendSms',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【协商还-发短】')

        # 用于装饰器断言
        reformed_data["uid"] = msg_info['uid']
        reformed_data["send_code"] = msg_info['tplId']

        return reformed_data

    @post_loan_touch_assert
    def lawyer_letter_send_sms(self, msg_info: dict) -> dict:
        """
        协商还场景发短
        :param msg_info: 短信入参
        :return: str, msg_id 短信id
        """
        reformed_data = self._generate_params(msg_info=msg_info)

        data = {
            'interface': 'com.fenqile.credit.collection.service.lawletter.CollectionLawerLetterService',
            'method': 'sendLawerLetterSMS',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【律师函-发短】')

        # 用于装饰器断言
        reformed_data["uid"] = msg_info['uid']
        reformed_data["send_code"] = msg_info['msgTemplate']

        return reformed_data

    @post_loan_touch_assert
    def system_send_sms(self, msg_info: list) -> dict:
        """
        系统发送短信
        :param msg_info: 短信入参
        :return: str, msg_id 短信id
        """
        reformed_data = {
            "env": self.env,
            "group": self.group,
            "uid": msg_info[0],
            "send_code": msg_info[1]["factualTplId"],
            "input_data": msg_info
        }

        data = {
            'interface': 'com.fenqile.credit.collection.service.message.CollectionMessageTemplateService',
            'method': 'sendMsgByUid',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【系统发送短信-RPC】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @post_loan_touch_assert
    def system_send_app_sms(self, msg_info: list) -> dict:
        """
        系统发送APP消息
        :param msg_info: 短信入参
        :return: str, msg_id 短信id
        """
        reformed_data = {
            "env": self.env,
            "group": self.group,
            "uid": msg_info[0],
            "send_code": msg_info[1]["factualTplId"],
            "input_data": msg_info
        }

        data = {
            'interface': 'com.fenqile.credit.collection.service.message.CollectionMessageTemplateService',
            'method': 'sendMsgByUid',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【系统发送APP消息-RPC】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @post_loan_touch_assert
    def system_send_wx_sms(self, msg_info: list) -> dict:
        """
        系统发送微信消息
        :param msg_info: 短信入参
        :return: str, msg_id 短信id
        """
        reformed_data = {
            "env": self.env,
            "group": self.group,
            "uid": msg_info[0],
            "send_code": msg_info[1]["factualTaskId"],
            "input_data": msg_info
        }

        data = {
            'interface': 'com.fenqile.credit.collection.service.message.CollectionMessageTemplateService',
            'method': 'sendMsgByUid',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【系统发送微信消息-RPC】')
        # print(type(reformed_data), reformed_data)

        return reformed_data

    @post_loan_touch_assert
    def inbound_send_sms(self, msg_info: dict) -> dict:
        """
        inbound进电场景发短
        :param msg_info: 短信入参
        :return: str, msg_id 短信id
        """
        reformed_data = self._generate_params(msg_info=msg_info)

        data = {
            'interface': 'com.fenqile.credit.collection.front.service.message.CollectionCaseSendMessageService',
            'method': 'inboundSendSms',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【InBound进电-发短】')

        # 用于装饰器断言
        reformed_data["uid"] = msg_info['uid']
        reformed_data["send_code"] = msg_info['actualTplId']

        return reformed_data


# 批量执行短信触达
def batch_exec_send_ms(env='stable', group='project_1093914'):
    plp = PostLoanPlat(env=env, use_proxy=True)  # 贷后系统管理端实例
    tp = TouchPlatform(env=env, group=group)  # 贷后执行端实例

    # log.debug("################## HTTP 接口触发场景 ########################")
    # # 系统发送短信
    # plp.system_send_sms(msg_info={
    #     "actual_tpl_id": "collection100067",
    #     "msg_list": [{"uid": 3109737, "case_id": 3109737, "queue_code": "NC223"}],
    #     "sell_channel_id": 1
    # })
    #
    # # 系统发送APP信息
    # plp.system_send_app_sms(msg_info={
    #     "actual_tpl_id": "APP202405281041414",
    #     "msg_list": [{"uid": 3109737, "case_id": 3109737, "queue_code": "NC223"}],
    #     "sell_channel_id": 1
    # })
    #
    # # 个人发送APP信息
    # plp.person_send_app_sms(msg_info={
    #     "actual_tpl_id": "APP202405281041414",
    #     "sell_channel_id": 1,
    #     "case_id": 3109737,
    # })
    #
    # # 投诉案件发送短信
    # plp.send_complaint_case_sms(msg_info={
    #     "uid": 3311476,
    #     "actual_tpl_id": "SMS202209290351170",
    #     "handle_result": 0,
    #     "operation": 30,
    # })
    #
    # # 个人发送短信信息
    # plp.person_send_sms(msg_info={
    #     "uid": 3311476,
    #     "actual_tpl_id": "SMS202502111167766",
    #     "sell_channel_id": 1
    # })
    #
    # # 第三方代还发送APP信息
    # plp.notify_others_app_sms(msg_info={
    #     "uid": 3034508,
    #     "actual_tpl_id": "APP2020010810"
    # })
    #
    # log.debug("################## RPC 接口触发场景 ########################")
    # # tp = TouchPlatform(env='stable', group='project_1093914')
    # # 协商还发送短信 --RPC
    # msg_info = {
    #     "collectionSendModel": "USER_MANUAL",
    #     "scene": "还款工具",
    #     "uid": 3311476,
    #     "mobile": "13433638155",
    #     "tplId": "SMS202408021313380",
    #     "contentData": {
    #         "name": "张三",
    #         "url": "http://short.url/123",
    #         "customer_hotline": "400-800-9000"
    #     }
    # }
    # tp.negotiate_repay_send_sms(msg_info=msg_info)
    #
    # # 律师函发送短信 --RPC
    # msg_info = {
    #     "uid": "3034508",
    #     "contractUrl": "http://img1.fenqile.com/eleccontract3/M00/02/52/oZ8BAF6EC4-AaMGiAARxLTk8vXM557.pdf",
    #     "msgTemplate": "SMS202003102",
    #     "contractId": "S20200401128114950A0910DC4737508",
    #     "token": f"{plp.token}"
    # }
    # tp.lawyer_letter_send_sms(msg_info=msg_info)
    #
    # # 系统发送短信 --RPC
    # msg_info = [
    #     3109737,
    #     {
    #         "fmode": 2,
    #         "sendOne": True,
    #         "fmsgTplId": 110,
    #         "ftplName": "heos自动短信",
    #         "fchannelType": 0,
    #         "fsendType": 20,
    #         "fsendObject": "[]",
    #         "fchannelId": 40,
    #         "fuserTagTypes": "[\"s3\",\"w1\",\"s2\",\"w2\",\"s1\"]",
    #         "fsellChannelIds": "[1]",
    #         "fsellChannelId": 1,
    #         "foverdueDays": "[\"100\"]",
    #         "fsendTime": "18:22",
    #         "factualTplId": "SMS202212201540962",
    #         "fopMemo": "",
    #         "foperator": "heoszhou",
    #         "fuseFlag": 1,
    #         "fcreateTime": "2025-07-11 16:39:11",
    #         "fmodifyTime": "2025-07-11 18:21:26",
    #         "fversion": 0,
    #         "fjgAutoTestId": "",
    #         "fuidSuffixs": "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]",
    #         "fqueueCodes": "[\"NC223\"]",
    #         "fdeliveryChannel": 0,
    #         "fappointedTime": "17",
    #         "fappointedOverdueDay": 0,
    #         "fqueueType": 10,
    #         "fdeliveryChannels": "",
    #         "factualTaskId": "",
    #         "ftemplateType": 0,
    #         "ftemplateContent": "",
    #         "ftemplatePic": "",
    #         "fworkplaces": "[]",
    #         "frandomRange": "",
    #         "fcompanyIdS": "[]",
    #         "fplatformType": 0,
    #         "fdetailChannelId": "",
    #         "fextendFields": "{}",
    #         "fallQueues": 0
    #     }
    # ]
    # tp.system_send_sms(msg_info=msg_info)
    #
    # # 系统发送APP消息 --RPC
    # msg_info = [
    #     3109737,
    #     {
    #         "fmode": 2,
    #         "sendOne": True,
    #         "fmsgTplId": 114,
    #         "ftplName": "heos-app自动",
    #         "fchannelType": 1,
    #         "fsendType": 20,
    #         "fsendObject": "[]",
    #         "fchannelId": 39,
    #         "fuserTagTypes": "[\"s3\",\"w1\",\"s2\",\"w2\",\"s1\"]",
    #         "fsellChannelIds": "[1]",
    #         "fsellChannelId": 1,
    #         "foverdueDays": "[\"100\"]",
    #         "fsendTime": "16:15",
    #         "factualTplId": "APP202304281355146",
    #         "fopMemo": "",
    #         "foperator": "heoszhou",
    #         "fuseFlag": 1,
    #         "fcreateTime": "2025-07-11 16:39:11",
    #         "fmodifyTime": "2025-07-11 18:21:26",
    #         "fversion": 0,
    #         "fjgAutoTestId": "",
    #         "fuidSuffixs": "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]",
    #         "fqueueCodes": "[\"NC223\"]",
    #         "fdeliveryChannel": 0,
    #         "fappointedTime": "17",
    #         "fappointedOverdueDay": 0,
    #         "fqueueType": 10,
    #         "fdeliveryChannels": "",
    #         "factualTaskId": "",
    #         "ftemplateType": 0,
    #         "ftemplateContent": "",
    #         "ftemplatePic": "",
    #         "fworkplaces": "[]",
    #         "frandomRange": "",
    #         "fcompanyIdS": "[]",
    #         "fplatformType": 0,
    #         "fdetailChannelId": "",
    #         "fextendFields": "{}",
    #         "fallQueues": 0
    #     }
    # ]
    # tp.system_send_app_sms(msg_info=msg_info)
    #
    # # Inbound进电发送短信 --RPC
    # msg_info = {
    #     "uid": 3109737,
    #     "actualTplId": "SMS202502111167766",
    #     "phone": "13433638155",
    #     "seqNum": "2224356",
    #     "icd": 145,
    #     "operatorId": 520,
    #     "contactRelation": "本人",
    #     "sellChannelId": 1,
    #     "token": f"{plp.token}"
    # }
    # tp.inbound_send_sms(msg_info=msg_info)

    # 系统发送微信消息 --RPC
    msg_info = [
        3112356,
        {
            "fmode": 1,
            "sendOne": True,
            "fmsgTplId": 119,
            "ftplName": "heos-微信",
            "fchannelType": 4,
            "fsendType": 20,
            "fsendObject": "[]",
            "fchannelId": 44,
            "fuserTagTypes": "[\"s3\",\"w1\",\"s2\",\"w2\",\"s1\"]",
            "fsellChannelIds": "[1]",
            "fsellChannelId": 1,
            "foverdueDays": "[\"0\"]",
            "fsendTime": "16:00",
            "factualTplId": "WX22020900015",
            "fopMemo": "",
            "foperator": "heoszhou",
            "fuseFlag": 1,
            "fcreateTime": "2025-07-11 16:39:11",
            "fmodifyTime": "2025-07-11 18:21:26",
            "fversion": 0,
            "fjgAutoTestId": "",
            "fuidSuffixs": "",
            "fqueueCodes": "[\"NC223\"]",
            "fdeliveryChannel": 0,
            "fappointedTime": "17",
            "fappointedOverdueDay": 0,
            "fqueueType": 10,
            "fdeliveryChannels": "",
            "factualTaskId": "T220209175324278",
            "ftemplateType": 0,
            "ftemplateContent": "",
            "ftemplatePic": "",
            "fworkplaces": "[]",
            "frandomRange": "",
            "fcompanyIdS": "[]",
            "fplatformType": 0,
            "fdetailChannelId": "",
            "fextendFields": "{}",
            "fallQueues": 0
        }
    ]
    tp.system_send_wx_sms(msg_info=msg_info)


if __name__ == '__main__':
    batch_exec_send_ms(env='stable', group='project_1093914')
