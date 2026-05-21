# -*- coding: utf-8 -*-
"""
# @File    : model_intent_recogntion_exec.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
# @Description  : 脚本描述
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
from common.dbAction import DbAction
from common.postLoanAction import PostLoanPlat


class ModelIntentRecognition:
    def __init__(self, env, group='stable'):
        self.env = env
        self.group = group

    def _generate_params(self, msg_info: dict) -> dict:
        """
        发短接口入参组装，读取配置，生成指定格式接口入参
        :param msg_info: dict，短信相关信息
        :return: dict 返回决策接口调用入参
        """
        #  拼接全部关联参数
        reformed_data = {
            "env": self.env,
            "group": self.group,
            "input_data": [{
                "chatId": msg_info.get('chatId') or f"chat_{self.env}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                "bizLineId": "BL001",
                "bizSceneKey": "CREDIT_LIMIT",
                "bizSceneTypeKey": "CREDIT_LIMIT",
                "customerSourceType": "LOGGED_IN_INSTANT_MESSAGING_CUSTOMER",
                "entityId": "entity_pre_001",
                "uid": msg_info['uid'],
                "externalUserId": msg_info['uid'],
                "userId": msg_info['uid'],
                "userName": "预发测试用户",
                "url": "",
                "chatType": "NORMAL",
                "isRetry": 0,
                "messageExtend": "",
                "external": "",
                "msgContextList": msg_info.get('msgContextList', [
                    {
                        "direction": "CUSTOMER_2_STAFF",
                        "msgId": f"msg_{self.env}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                        "content": msg_info['content'],
                        "msgType": "TEXT",
                        "mediaFileMap": {}
                    }
                ])
            }]
        }

        return reformed_data

    def send_msg_to_model(self, msg_info: dict) -> dict:
        """
        在线实时决策接口
        :param msg_info: dict，用户msg信息
        :return: 返回决策结果和相关信息，包含res, uid, orderid, processid 和instanceid
        """
        reformed_data = self._generate_params(msg_info=msg_info)

        data = {
            'interface': 'com.fenqile.rc.agent.adapter.service.FrontImChatService',
            'method': 'chat',
            'env': self.env,
            'group': self.group,
            'params': reformed_data['input_data']
        }
        reformed_data['request_data'] = data
        reformed_data['output_data'] = BaseRpc.exec_rpc(data, desc='【模型意图识别】')
        log.info(f"【模型意图识别】完整执行结果：{reformed_data}")

        return reformed_data


if __name__ == '__main__':
    msg_info = {
        "uid": "4089534",
        "content": "我要提额"
    }
    mr = ModelIntentRecognition(env='pre', group='default')
    mr.send_msg_to_model(msg_info=msg_info)

