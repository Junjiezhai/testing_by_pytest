# -*- coding: utf-8 -*-
"""
# @File    : model_intent_recogntion_exec.py
# @Date    : 2026-05-20
# @Author  : jeremyzhai
# @Description  : 脚本描述
"""
import os
import time
import functools

from common.rpcAction import BaseRpc
from utils.handle_log import log
from utils.handle_yaml import read_yaml_data
from utils.handle_path import Base_Path
from utils.rate_limiter import global_rate_limiter
import random
from typing import Union
from datetime import datetime



def poll_result(max_wait_seconds=120, interval_s=5):
    """
    轮询装饰器：当函数返回空列表时，按间隔时间重新发起查询，直到超时。
    :param max_wait_seconds: 最大等待时间（秒），默认120秒
    :param interval_s: 每次轮询间隔（秒），默认5秒
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            poll_count = 0
            while True:
                poll_count += 1
                result = func(*args, **kwargs)
                if result:  # 结果不为空列表，返回成功
                    return result
                elapsed = time.time() - start_time
                if elapsed >= max_wait_seconds:
                    raise TimeoutError(f"异步查询超时，已超过最大等待时间 {max_wait_seconds} 秒，interval={interval_s}s，轮询次数={poll_count}")
                log.info(f"【异步轮询】第 {poll_count} 次轮询，等待 {interval_s}s 后重试...")
                time.sleep(interval_s)
        return wrapper
    return decorator


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
                "chatId": msg_info.get('chatId') or f"chat_{self.env}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{random.randint(1, 9)}",
                "bizLineId": "BL001",
                "bizSceneKey": msg_info.get('biz_scene_key',"BSK2605181039042973"),
                "bizSceneTypeKey": "BSK2605181039042973",
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
                        "msgId": f"msg_{self.env}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{random.randint(1, 9)}",
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
        发起模型聊天，支持异步模式自动轮询
        :param msg_info: dict，用户msg信息
        :return: 返回结果和相关信息
        """
        # 请求前获取令牌（如启用了限流则阻塞等待）
        global_rate_limiter.acquire()

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

        # 判断是否触发异步模式：chatType=NORMAL 且 replyContents 中存在 value=AS2605261028460912 的 ASSET
        output_data = reformed_data.get('output_data', {})
        if self._is_async_trigger(output_data):
            log.info("【模型意图识别】检测到异步模式触发条件，开始异步查询...")
            async_result = self._handle_async_mode(reformed_data)
            if async_result is not None:
                reformed_data['output_data'] = async_result

        log.info(f"【模型意图识别】完整执行结果：{reformed_data}")

        return reformed_data

    @classmethod
    def _get_async_trigger_biz_types(cls) -> set:
        """
        从YAML配置中获取所有需要触发异步模式的业务类型值集合
        """
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'model_intent_reply_rules.yaml')
            rules = read_yaml_data(config_path) or {}
            biz_types = rules.get('biz_types', {})
            return set(biz_types.keys()) if isinstance(biz_types, dict) else set()
        except Exception as e:
            log.warning(f"【异步模式】读取biz_types配置失败：{e}")
            return set()

    @classmethod
    def _is_async_trigger(cls, output_data: dict) -> bool:
        """
        判断是否触发异步模式：
        chatType == NORMAL，且 replyContents 中存在 type='ASSET' 且 value 在 biz_types 配置中的元素
        """
        if not isinstance(output_data, dict):
            return False
        data = output_data.get('data', {})
        chat_type = str(data.get('chatType', '')).upper()
        if chat_type != 'NORMAL':
            return False
        reply_contents = data.get('replyContents', [])
        if not isinstance(reply_contents, list):
            return False
        async_biz_types = cls._get_async_trigger_biz_types()
        for item in reply_contents:
            if isinstance(item, dict):
                item_type = str(item.get('type', '')).upper()
                item_value = str(item.get('value', ''))
                if item_type == 'ASSET' and item_value in async_biz_types:
                    return True
        return False

    def _handle_async_mode(self, reformed_data: dict) -> dict:
        """
        处理异步模式：提取查询参数，发起异步轮询，转换结果格式
        :param reformed_data: 包含请求入参和模型返回的完整数据
        :return: 转换后的 output_data 格式
        """
        # 提取异步查询参数
        input_data_list = reformed_data.get('input_data', [])
        if not input_data_list:
            log.warning("【异步模式】无法从 input_data 提取参数")
            return reformed_data.get('output_data')

        input_data = input_data_list[0]
        uid = input_data.get('uid')
        biz_scene_key = input_data.get('bizSceneKey')

        # 从 output_data 的 replyContents 中提取 session_id 和 plan_id
        output_data = reformed_data.get('output_data', {})
        data_section = output_data.get('data', {})
        reply_contents = data_section.get('replyContents', [])

        session_id = ''
        plan_id = ''
        for item in reply_contents:
            if isinstance(item, dict) and str(item.get('type', '')).upper() == 'ASSET':
                biz_param_info = item.get('bizParamInfo', {}) if isinstance(item.get('bizParamInfo'), dict) else {}
                session_id = biz_param_info.get('sessionId', '')
                plan_id = biz_param_info.get('planId', '') or biz_param_info.get('plan_id', '')
                break

        if not all([uid, biz_scene_key, session_id, plan_id]):
            log.warning(f"【异步模式】异步查询参数不完整：uid={uid}, biz_scene_key={biz_scene_key}, "
                        f"session_id={session_id}, plan_id={plan_id}")
            return output_data

        query_info = {
            'uid': uid,
            'biz_scene_key': biz_scene_key,
            'session_id': session_id,
            'plan_id': plan_id
        }

        log.info(f"【异步模式】开始异步查询，参数：{query_info}")
        async_results = self.fetch_model_final_res_with_poll(query_info)
        log.info(f"【异步模式】异步查询结果：{async_results}")

        # 转换异步结果为同步格式
        transformed = self._transform_async_result(async_results, output_data)
        return transformed

    def _transform_async_result(self, async_results: list, original_output_data: dict) -> dict:
        """
        将异步查询结果转换为同步格式，兼容当前断言逻辑
        :param async_results: 异步查询返回的列表结果
        :param original_output_data: 原始的 output_data
        :return: 转换后的 output_data 字典
        """
        if not async_results or not isinstance(async_results, list):
            log.warning("【异步模式】异步结果为空，返回原始数据")
            return original_output_data

        # 取第一个结果
        result = async_results[0]
        if not isinstance(result, dict):
            log.warning("【异步模式】异步结果格式异常，返回原始数据")
            return original_output_data

        # 提取 text 和 cards
        text = result.get('text', '')
        cards = result.get('cards', [])
        if not isinstance(cards, list):
            cards = []

        # 构建 replyContents
        reply_contents = []
        if text:
            reply_contents.append({
                "type": "TEXT",
                "value": text
            })

        for card in cards:
            if not isinstance(card, dict):
                continue
            card_id = card.get('card_id', '')
            biz_ref_id = card.get('biz_ref_id', [])
            if not isinstance(biz_ref_id, list):
                biz_ref_id = [biz_ref_id] if biz_ref_id else []

            reply_contents.append({
                "type": "ASSET",
                "value": card_id,
                "bizParamInfo": {
                    "biz_ref_id": biz_ref_id
                }
            })

        # 组装转换后的 output_data，保持原有结构
        transformed = {
            "data": {
                "chatType": "NORMAL",
                "handoffReason": "",
                "replyContents": reply_contents,
                "intent": original_output_data.get('data', {}).get('intent', ''),
                "intentCode": original_output_data.get('data', {}).get('intentCode', ''),
                "intentName": original_output_data.get('data', {}).get('intentName', ''),
            }
        }

        # 保留原始 output_data 中的其他字段
        if isinstance(original_output_data, dict):
            for key, value in original_output_data.items():
                if key != 'data':
                    transformed[key] = value

        return transformed

    @poll_result(max_wait_seconds=120, interval_s=5)
    def fetch_model_final_res_with_poll(self, query_info: dict) -> list:
        """
        带轮询的异步查询入口，装饰器会自动处理轮询逻辑
        :param query_info: dict，异步查询参数
        :return: list，异步结果列表
        """
        return self.fetch_model_final_res(query_info)

    def fetch_model_final_res(self, query_info: dict) -> list:
        """
        发起模型异步结果查询（单次）
        :param query_info: dict，用户会话信息
        :return: list，返回结果列表，为空则继续轮询
        """
        data = {
            'interface': 'com.fenqile.rc.agent.adapter.service.FrontAsyncPlanService',
            'method': 'queryPlan',
            'env': self.env,
            'group': self.group,
            'params': [{
                "planId": query_info["plan_id"],
                "userId": query_info["uid"],
                "sessionId": query_info["session_id"],
                "bizSceneKey": query_info["biz_scene_key"],
            }],
        }
        res = BaseRpc.exec_rpc(data, desc='【模型结果异步查询】')

        # 判断是否需要重新查询
        final_res = []
        if_need_continue = res.get("should_continue", True)
        if not if_need_continue:
            final_res_data = res.get('final_result') or {}
            final_res = final_res_data.get('message', []) if isinstance(final_res_data, dict) else []
        log.info(f"当前if_need_continue：{if_need_continue}, 模型结果参数为：{final_res}")

        return final_res


if __name__ == '__main__':
    # ========================================
    # 【同步模式调用样例】
    # ========================================
    mr = ModelIntentRecognition(env='pre', group='default')

    # msg_info_sync = {
    #     "uid": "4089534",
    #     "content": "我想申请提额"
    # }
    # # 同步模式：直接调用 send_msg_to_model
    # sync_res = mr.send_msg_to_model(msg_info=msg_info_sync)
    # print("【同步模式】返回结果：", sync_res)

    # ========================================
    # 【异步模式调用样例】
    # ========================================
    # 模拟异步模式触发场景：模型返回 AS2605261028460912 业务卡片
    msg_info_async = {
        "uid": "4089534",
        "content": "我想提额到120000"
    }
    # 异步模式：send_msg_to_model 内部会自动检测异步条件并触发轮询
    # 当返回的 replyContents 中存在 type='ASSET' 且 value='AS2605261028460912' 时，
    # 会自动提取 session_id、plan_id 等参数，调用 fetch_model_final_res_with_poll 进行轮询
    async_res = mr.send_msg_to_model(msg_info=msg_info_async)
    print("【异步模式】返回结果：", async_res)

    # ========================================
    # 【手动异步查询调用样例】
    # ========================================
    # 如需手动发起异步查询，可直接调用 fetch_model_final_res_with_poll（带轮询）
    # 或 fetch_model_final_res（单次查询）
    # query_info = {
    #     "plan_id": "6b3f9a0b0cd24beea4246b4fa559a4a1",
    #     "uid": "4089534",
    #     "session_id": "chat_pre_20260528142417980453",
    #     "biz_scene_key": "BSK2605181039042973"
    # }
    # # 单次查询
    # single_res = mr.fetch_model_final_res(query_info=query_info)
    # print("【手动单次异步查询】结果：", single_res)
    # # 轮询查询（推荐）
    # poll_res = mr.fetch_model_final_res_with_poll(query_info=query_info)
    # print("【手动轮询异步查询】结果：", poll_res)
