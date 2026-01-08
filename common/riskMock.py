# -*- coding: utf-8 -*-
"""
# @File    : riskMock.py
# @Date    : 2024-10-29
# @Author  : jeremyzhai
"""

# import requests
# import json
# from common.httpAction import HttpAction
from utils.handle_log import log
from common.rpcAction import BaseRpc
from datetime import datetime


# 风控mock，支持mock FSM字段和风控流程
class RiskMock:
    def __init__(self, env='stable', group='stable'):
        self.cur_env = env
        self.group = group

    # fsm 字段mock
    def fsm_mock(self, uid, data: dict):
        """
        fsm字段mock函数，支持单字段和多个字段
        :param uid: 用户uid,
        :param data: dict格式， 如 {'rr_level_daily_combo_1point5': 'R1', 'rr_fq_lc_daily_combo_1point5': '0.0001'},
        :return: 返回mock结果，
            全部成功返回为 {"ret_msg":"success","ret_code":"0"}, 如果有失败，返回{"ret_msg":"fail","ret_code":"错误码"，"error_fsm":['字段名']}
        """
        if not isinstance(data, dict):
            raise Exception("输入的请求参数不是dict类型！")

        # 设置初始返回值，默认成功
        resp = {
            'ret_msg': 'success',
            'ret_code': '0',
            'error_fsm': []
        }

        ''' http 接口mock'''
        # for key in data.keys():
        #     tmp_data = {"uid": uid, "field_name": key, "field_value": data[key]}
        #     tmp_resp = self.send_http(tmp_data)
        #     if tmp_resp['retmsg'] != 'success':
        #         # 如果某个字段mock失败，修改返回结果
        #         resp['error_fsm'].append(key)
        #         resp['ret_code'] = '5200001'
        #         resp['ret_msg'] = 'fail'
        # log.info(f"mock结果: {resp}")

        ''' rpc 接口mock'''
        for key in data.keys():
            tmp_params = {"uid": uid, "fieldName": str(key), "fieldValue": str(data[key]), "status": 1}
            # 1，组装rpc接口参数
            mock_data = {
                'interface': 'com.fenqile.rc.credit.manage.service.RcCreditFsmFieldMockService',
                'method': 'updateField',
                'env': self.cur_env,
                'group': self.group,
                'params': [tmp_params]
            }
            # 2，执行rpc接口调用
            tmp_resp = BaseRpc.exec_rpc(mock_data, "FSM字段mock：")

            # 如果某个字段mock失败，修改返回结果
            if tmp_resp['errcode'] != 0:
                resp['error_fsm'].append(key)
                resp['ret_code'] = '5200001'
                resp['ret_msg'] = 'fail'

        log.info(f"mock结果: {resp}")
        return resp

    # 风控1.0， 流程mock
    def process_mock_v1(self, uid, process_id, mock_req: dict):
        """
        风控1.0 流程mock，支持授信流程和米霍克系统流程
        :param uid: 用户uid，支持int，str类型
        :param process_id: 流程id，授信流程通常以Q+数字组合，系统流程为纯数字
        :param mock_req: 需要mock的参数，dict类型
            授信流程： {"risk_pricing":2400 #定价,"approval_result":1#决策结果（1通过，2转人工，3拒绝）,"credit_cash":15000#取现额度,"credit_limit":15000#乐卡额度}, --- mock通过时，额度和决策结果必填
            系统流程：{"approval_result":1,"cause_codes":[],"risk_code":''}，--- 系统流程，仅approval_result必填
        :return: mock结果
        """
        if not isinstance(mock_req, dict):
            raise Exception("输入的请求参数不是dict类型！")

        ''' http 接口'''
        # # 1，新增流程
        # add_data = {"uid": uid, "mock_type": 1, "rc_process_id_list": [str(process_id)], 'operator': 'system'}
        # add_resp = self.send_http(data=add_data, req_type='add_process')
        # log.info(f"风控1.0流程{process_id}添加结果：{add_resp}")
        # # 如果返回值为19401014，则表示流程已添加
        # if add_resp['retmsg'] != 'success' and int(add_resp['retcode']) != 19401014:
        #     raise Exception(f'添加异常，结果返回为{add_resp}')  # 添加异常，抛错
        #
        # # 2, 查询流程列表，获取index
        # # 判断process_id 是授信流程还是系统流程
        # if isinstance(process_id, int) or process_id.isdecimal():
        #     # 纯数字，米霍克系统流程
        #     query_data = {
        #         'url': f'?uid={uid}&rc_process_id={process_id}&app_id=&operator=&page=1&limit=10&valid_status=&process_id=&flow_source=2'
        #     }
        # else:
        #     # 非纯数字，授信平台流程
        #     query_data = {
        #         'url': f'?uid={uid}&rc_process_id={process_id}&app_id=&operator=&page=1&limit=10&valid_status=&process_id=&flow_source=1'
        #     }
        # query_resp = self.send_http(data=query_data, req_type='query_process')
        # index = query_resp['result_rows'][0]['index']
        # log.info(f'风控1.0流程{process_id}对应的index为: {index}')
        #
        # # 3，执行流程mock，组装mock入参
        # # 判断process_id 是授信流程还是系统流程
        # if isinstance(process_id, int) or process_id.isdecimal():
        #     # 纯数字，米霍克系统流程
        #     mock_data = {
        #         'index': index,
        #         "mock_type": 1,
        #         'operator': 'system',
        #         'mock_result_bean': {
        #             "risk_pricing": 3600,
        #             "approval_result": mock_req['approval_result'],
        #             "cause_codes": mock_req['cause_codes'] if 'cause_codes' in mock_req else [],
        #             "flow_mock_type": "1",
        #             "credit_cash": 10000,
        #             "credit_limit": 10000
        #         }
        #     }
        #     # 部分流程通过risk_code赋值，如定价
        #     if 'risk_code' in mock_req:
        #         mock_data['mock_result_bean']['risk_code'] = str(mock_req['risk_code'])
        # else:
        #     mock_data = {
        #         'index': index,
        #         "mock_type": 1,
        #         'operator': 'system',
        #         'mock_result_bean': {
        #             "risk_pricing": mock_req['risk_pricing'],
        #             "approval_result": mock_req['approval_result'],
        #             "cause_codes": [],
        #             "credit_cash": mock_req['credit_cash'],
        #             "credit_limit": mock_req['credit_limit'],
        #             "block_codes": [],
        #             "custermer_level": 1
        #         }
        #     }
        # mock_resp = self.send_http(data=mock_data, req_type='mock_process')
        # log.info(f"风控1.0流程{process_id}mock结果：{mock_resp}")

        ''' rpc 接口'''
        # 1，判断process_id 是授信流程还是系统流程
        if isinstance(process_id, int) or process_id.isdecimal():
            # 系统流程，纯数字
            flow_source = '2'
        elif isinstance(process_id, str) and process_id[0] == 'Q' and process_id[1:].isdecimal():
            # 授信流程，以Q开头, 其余均为数字
            flow_source = '1'
        else:
            raise ValueError(f"传入的流程id：{process_id}，不合法！")

        # 2, 新增流程
        add_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
            'method': 'saveRcCreditTestPlan',
            'env': self.cur_env,
            'group': self.group,
            'params': [{
                "mockResultBean": {},
                "mockType": "1",
                "rcProcessIdList": [f"{process_id}"],
                "uid": uid,
                "operator": "ZSPT_system",
                "flowSource": flow_source,
                "status": "1"
            }]
        }

        # 执行rpc接口调用
        add_resp = BaseRpc.exec_rpc(add_data)

        # 结果判断，正常添加，返回1
        if isinstance(add_resp, int):
            log.info(f"流程{process_id}添加成功！")
        else:
            if add_resp['errcode'] == 19401014 and '无需重复添加' in add_resp['errmsg']:
                log.warning(add_resp['errmsg'])
            else:
                raise Exception(f"流程{process_id}添加异常,错误码：{add_resp['errcode']}，错误信息：{add_resp['errmsg']}")

        # 2, 查询流程对应的index
        query_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
            'method': 'queryTestPlanByUid',
            'env': self.cur_env,
            'group': self.group,
            'params': [{
                "uid": uid,
                "rcProcessId": str(process_id),
                "mockType": 1,
                "status": 1
            }]
        }
        query_resp = BaseRpc.exec_rpc(query_data)
        index = query_resp['index']

        # 3，执行流程mock
        if flow_source == '2':
            # 系统流程mock
            mock_data = {
                'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
                'method': 'updateMockResult',
                'env': self.cur_env,
                'group': self.group,
                'params': [
                    {
                        "index": index,
                        "mockResultBean": {
                            "riskPricing": 3600,
                            "approvalResult": mock_req['approval_result'],
                            "causeCodes": mock_req.get('cause_codes', []),
                            "flowMockType": 1,
                            "creditCash": 10000,
                            "creditLimit": 10000,
                            "riskCode": str(mock_req.get('risk_code', ''))
                        },
                        "mockType": 1,
                        "operator": "ZSPT_system"
                    }
                ]
            }
        else:
            # 授信流程mock
            mock_data = {
                'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
                'method': 'updateMockResult',
                'env': self.cur_env,
                'group': self.group,
                'params': [
                    {
                        "index": index,
                        "mockResultBean": {
                            "riskPricing": mock_req.get('risk_pricing', 0),
                            "approvalResult": mock_req['approval_result'],
                            "causeCodes": [],
                            "flowMockType": 2,
                            "creditCash": mock_req.get('credit_cash', mock_req['credit_limit']),
                            "creditLimit": mock_req['credit_limit'],
                            "riskCode": ''
                        },
                        "mockType": 1,
                        "operator": "ZSPT_system"
                    }
                ]
            }

        # 执行rpc接口调用
        mock_resp = BaseRpc.exec_rpc(mock_data)

        if isinstance(mock_resp, int):
            log.info(f"流程{process_id}mock成功！")

        # return mock_resp

    # 风控1.0， 节点mock
    def process_node_mock(self, uid, process_id, mock_req: list):
        """
        风控1.0 节点mock，支持授信流程和米霍克系统流程
        :param uid: 用户uid，支持int，str类型
        :param process_id: 流程id，授信流程通常以Q+数字组合，系统流程为纯数字
        :param mock_req: 需要mock的节点列表，支持多节点mock，list类型
            mock输入示例：
            [{
                "ruleSetId": 98563,#决策节点id
                "nodeMockType": 2,#mock类型（1-修改输入，2-修改输出）
                "opMemo": "",#备注，非必填
                "fieldInfo": [{
                    "fieldName": "approval_result",#字段名
                    "fieldValue": "3"#字段值
                }]
            }]
        :return: mock结果
        """
        if not isinstance(mock_req, list):
            raise Exception("输入的请求参数非list类型")

        ''' rpc 接口'''
        # 1，判断process_id 是授信流程还是系统流程
        if isinstance(process_id, int) or process_id.isdecimal():
            # 系统流程，纯数字
            flow_source = '2'
        elif isinstance(process_id, str) and process_id[0] == 'Q' and process_id[1:].isdecimal():
            # 授信流程，以Q开头, 其余均为数字
            flow_source = '1'
        else:
            raise Exception(f"传入的流程id：{process_id}，不合法")

        # 2, 新增流程，指定mock类型-节点mock，mockType=2
        add_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
            'method': 'saveRcCreditTestPlan',
            'env': self.cur_env,
            'params': [{
                "mockResultBean": {},
                "mockType": "2",
                "rcProcessIdList": [f"{process_id}"],
                "uid": uid,
                "operator": "ZSPT_system",
                "flowSource": flow_source,
                "status": "1"
            }]
        }

        # 执行rpc接口调用
        add_resp = BaseRpc.exec_rpc(add_data)

        # 结果判断，正常添加，返回1
        if isinstance(add_resp, int):
            log.info(f"流程{process_id}添加成功！")
        else:
            if add_resp['errcode'] == 19401014 and '无需重复添加' in add_resp['errmsg']:
                log.warning(add_resp['errmsg'])
            else:
                raise Exception(f"流程{process_id}添加异常,错误码：{add_resp['errcode']}，错误信息：{add_resp['errmsg']}")

        # 3, 查询授信or系统流程mock类型mockType和index
        index, mock_type = self.process_node_mock_index(uid=uid, process_id=process_id)

        # 4, 根据查询到的mock类型判断是否需要进行变更
        if mock_type != 2:
            log.info(f"流程mock类型: {mock_type}, 不是节点mock，变更类型为节点mock")
            self.process_node_mock_type(index=index, mock_type=2, uid=uid, process_id=process_id)

        # 5, 编辑节点mock结果
        mock_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditNodeMockService',
            'method': 'updateNodeMock',
            'env': self.cur_env,
            'params': [{
                "operator": "ZSPT_system",
                "planId": index,
                "listNode": mock_req
            }]
        }
        mock_resp = BaseRpc.exec_rpc(mock_data)
        if mock_resp['errcode'] == 0:
            log.info(f"流程{process_id}, 节点mock成功， mock结果为：{mock_req}")
        else:
            raise Exception("节点mock接口调用异常，mock失败！")

    # 风控1.0， 节点mock，获取授信or系统流程index&mockType方法
    def process_node_mock_index(self, uid, process_id):
        """
        风控1.0 节点mock，获取授信or系统流程index&mock_type
        :param uid: 用户uid，支持int，str类型
        :param process_id: 流程id
        :return: 流程index&mock_type
        """

        ''' rpc 接口'''
        # 1，判断process_id 是授信流程还是系统流程
        if isinstance(process_id, int) or process_id.isdecimal():
            # 系统流程，纯数字
            flow_source = '2'
        elif isinstance(process_id, str) and process_id[0] == 'Q' and process_id[1:].isdecimal():
            # 授信流程，以Q开头, 其余均为数字
            flow_source = '1'
        else:
            raise Exception(f"传入的流程id：{process_id}，不合法")

        # 3, 查询授信or系统流程mock类型mockType和index
        query_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
            'method': 'pageList',
            'env': self.cur_env,
            'params': [{
                "uid": uid,
                "page": "1",
                "limit": "10",
                "flowSource": flow_source,
                "rcProcessId": process_id
            }]
        }
        query_resp = BaseRpc.exec_rpc(query_data)
        # 4, 解析json数据，提取mockType和index
        index = query_resp['resultRows'][0]['index']
        mock_type = query_resp['resultRows'][0]['mockType']
        # 5, 判断输出的mockType和index是否合法
        if not (isinstance(index, int) or isinstance(index, str)):
            raise Exception("输出的index非int类型")
        if not (mock_type == 1 or mock_type == 2):
            raise Exception("输出的mock_type不合法")
        return index, mock_type

    # 风控1.0， 节点mock，变更授信or系统流程mock类型
    def process_node_mock_type(self, index, mock_type, uid, process_id):
        """
        风控1.0， 节点mock，更改授信or系统流程mockType
        :param index: 流程index
        :param mock_type: 流程mock类型（1-流程mock，2-节点mock）
        :param uid: 用户uid，支持int，str类型
        :param process_id: 流程id
        """
        # 1, 变更授信or系统流程mock类型
        batch_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
            'method': 'updateMockResult',
            'env': self.cur_env,
            'params': [
                {
                    "index": index,
                    "mockResultBean": {
                        "riskPricing": 3600,
                        "approvalResult": 1,
                        "causeCodes": [],
                        "flowMockType": 1,
                        "creditCash": 10000,
                        "creditLimit": 10000,
                        "riskCode": ''
                    },
                    "mockType": mock_type,
                    "operator": "ZSPT_system"
                }
            ]
        }
        # 2, 执行rpc接口调用
        batch_resp = BaseRpc.exec_rpc(batch_data)
        if isinstance(batch_resp, int):
            log.info("rpc接口调用成功")
            # 3, 查询变更后的mockType是否正确
            mock_resp = self.process_node_mock_index(uid=uid, process_id=process_id)[1]
            if mock_resp == mock_type:
                log.info(f"更改流程mockType={mock_type}成功！")
            else:
                raise Exception(f"流程mockType={mock_type}变更失败！")

    # 风控1.0， 流程失效/生效
    def process_mock_valid(self, status, uid, process_id: str):
        """
        风控1.0， 流程失效
        :param status: 流程状态（1-生效，2-失效） int型
        :param uid: 用户uid，支持int，str类型
        :param process_id: 流程id
        """
        ''' rpc 接口'''
        # 1，判断process_id 是授信流程还是系统流程
        if isinstance(process_id, int) or process_id.isdecimal():
            # 系统流程，纯数字
            flow_source = '2'
        elif isinstance(process_id, str) and process_id[0] == 'Q' and process_id[1:].isdecimal():
            # 授信流程，以Q开头, 其余均为数字
            flow_source = '1'
        else:
            raise Exception(f"传入的流程id：{process_id}，不合法")
        # 2，获取流程index
        index = self.process_node_mock_index(uid=uid, process_id=str(process_id))[0]
        mock_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
            'method': 'updateStatus',
            'env': self.cur_env,
            'params': [
                {
                    "index": index,
                    "status": status,
                    "opMemo": "ZSPT",
                    "operator": "ZSPT_system"
                }
            ]
        }
        # 3，调用rpc接口
        mock_resp = BaseRpc.exec_rpc(mock_data)
        if isinstance(mock_resp, int):
            log.info("rpc接口调用成功")
            # 4，查询流程是否失效
            query_data = {
                'interface': 'com.fenqile.rc.credit.manage.service.RcCreditTestPlanService',
                'method': 'pageList',
                'env': self.cur_env,
                'params': [{
                    "uid": uid,
                    "page": "1",
                    "limit": "10",
                    "flowSource": flow_source,
                    "rcProcessId": process_id
                }]
            }
            query_resp = BaseRpc.exec_rpc(query_data)
            process_status = query_resp['resultRows'][0]['status']
            if process_status == 2:
                log.info(f"更改流程状态为失效status={process_status}成功！")
            elif process_status == 1:
                log.info(f"更改流程状态为生效status={process_status}成功！")
            else:
                raise Exception(f"流程状态={process_status}异常！")

    # 风控2.0， 流程mock
    def process_mock_v2(self, uid, process_id, mock_req: dict, valid_status=0):
        """
        风控2.0 流程mock
        :param valid_status: 0表示生效，1表示失效
        :param uid: 用户uid，支持int，str类型
        :param process_id: 流程id
        :param mock_req: 需要mock的参数，dict类型, 格式如下，仅"approval_result" 必填
            {
                "approval_result":1, #必填，0通过，1转人工，2拒绝， 99中断
                "price": 20.48, #定价
                "credit_limit": 15000 #额度，整数
                'env': 'stable' #环境标识，默认stable
            }
        :return: mock结果
        """
        if not isinstance(mock_req, dict):
            raise Exception("输入的请求参数不是dict类型！")

        ''' http接口调用 '''
        # # 1，新增流程引擎流程
        # add_data = {"uid": uid, "mock_type": 0, "process_id_list": [process_id], 'operator': 'system'}
        # add_resp = self.send_http(data=add_data, req_type='add_process')
        # log.info(f"风控2.0流程{process_id}，添加结果：{add_resp}")
        #
        # # 2, 执行mock
        # mock_data = {
        #     "uid": uid,
        #     "process_id": process_id,
        #     "mock_type": 0,
        #     "valid_status": 0,
        #     "operator": 'system',
        #     "mock_result": {
        #         "approval_result": mock_req['approval_result'],
        #         "output": {
        #             "approval_result": mock_req['approval_result'],
        #             "cause": [""],
        #             "disposal_codes": "",
        #             "tag_codes": [],
        #             "untag_codes": [],
        #             "credit_extra_data": {},
        #             "price": mock_req['price'] if 'price' in mock_req else 24,
        #             "credit_limit": mock_req['credit_limit'] if 'credit_limit' in mock_req else 10000,
        #             "credit_cash": mock_req['credit_cash'] if 'credit_cash' in mock_req else 10000
        #         }
        #     }
        # }
        # mock_resp = self.send_http(data=mock_data, req_type='mock_process')
        # log.info(f"风控2.0流程{process_id}，mock结果：{mock_resp}")

        '''RPC接口调用'''
        # 1，组装rpc接口参数
        mock_data = {
            'interface': 'com.fenqile.process.engine.console.service.mock.ProcessMockService',
            'method': 'saveProcessMockResult',
            'env': self.cur_env,
            'params': [
                {
                    "processId": process_id,
                    "uid": uid,
                    "mockType": 0,
                    "validStatus": valid_status,
                    "mockResult": {
                        "approvalResult": mock_req['approval_result'],
                        "output": {
                            "approval_result": mock_req['approval_result'],
                            "cause": ["pass"],
                            "disposal_codes": mock_req.get('disposal_codes', ''),
                            "tag_codes": [],
                            "untag_codes": [],
                            "credit_extra_data": {},
                            # "price": mock_req.get('price', 24),
                            # "credit_limit": mock_req.get('credit_limit', 100000),
                            # "credit_cash": mock_req.get('credit_cash', 100000)
                        }
                        # "output": mock_req
                    }
                }
            ]
        }
        # 将mock_req中的其他参数添加到output中
        for k, v in mock_req.items():
            if k not in mock_data['params'][0]['mockResult']['output'].keys():
                mock_data['params'][0]['mockResult']['output'][k] = v

        # 2，执行rpc接口调用
        mock_resp = BaseRpc.exec_rpc(mock_data)

        # 若接口返回值不为0，接口调用失败
        if mock_resp['retcode'] != '0':
            log.error(f"mock失败，接口返回值为：{mock_resp}")
            raise Exception(f"mock失败，接口返回值为：{mock_resp}")

        log.info(f"mock成功，rpc接口返回值为：{mock_resp['retcode']}，返回信息为：{mock_resp['retmsg']}")

        return mock_resp

    # 交易定价mock
    def price_mock(self, uid, price, businessType=10, businessScene=10, mockType='2.0'):
        """
        mock 指定用户的交易定价
        :param uid: 用户uid， int/str格式
        :param price: 定价， int/str格式
        :param mockType: mock类型，区分1.0和2.0， str格式，默认风控2.0
        :param bussinessType: 业务类型， int格式， 10表示现金，20乐花卡，30电商
        :param bussinessScne: 业务场景， int格式， 10普通借钱， 230精细化运营， 具体场景还需要结合业务穷举一下
        :return:
        """

        if float(price) > 24 or float(price) <= 0:
            raise Exception(f"传入的price：{price} 超出正常范围(0,24]")

        ''' 风控1.0 mock '''
        if mockType == '1.0':
            # 1，定价mock
            process_id = '1585'
            mock_req = {
                "approval_result": 1,
                'risk_code': str(price)
            }
            self.process_mock_v1(uid=uid, process_id=process_id, mock_req=mock_req)


        elif mockType == '2.0':
            ''' 风控2.0 mock '''
            # 定价更新接口
            update_data = {
                'interface': 'com.fenqile.order.billing.service.pricing.GeneralAdjustPriceService',
                'method': 'adjustPrice',
                'env': self.cur_env,
                'group': self.group,
                'params': [{
                    "operator": "ZSPT_system",
                    "uid": uid,
                    "memo": "调价",
                    "businessType": businessType,
                    "businessScene": businessScene,
                    "currentPrice": price,
                    "adjustTime": datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S"),
                    "effectWay": "50",
                    "checkFlag": "-1"
                }]
            }
            # 执行rpc接口调用
            update_resp = BaseRpc.exec_rpc(update_data)

            # 对接口返回进行判断
            if update_resp['errcode'] == 0:
                log.info(f"接口调价成功，调整定价为:{price}")
            else:
                if update_resp['errcode'] == 10871029 and ('不调价' in update_resp['errmsg']):
                    log.warning(update_resp['errmsg'])
                else:
                    raise Exception("接口调用异常，调价失败！")

        else:
            raise Exception(f"传入的mockType：{mockType}，非1.0或2.0！")

        # 实时定价查询
        query_data = {
            'interface': 'com.fenqile.order.billing.service.pricing.RealTimeQueryPriceService',
            'method': 'getUserRealTimePrice',
            'env': self.cur_env,
            'group': self.group,
            'params': [
                {
                    "totalAmount": 10000,
                    "fqNum": 3,
                    "businessType": businessType,
                    "busnessScene": 999,
                    "orderType": 280,
                    "saleType": 6510,
                    "scene": 1,
                    "uid": uid
                }
            ]
        }
        # 执行rpc接口调用
        quey_resp = BaseRpc.exec_rpc(query_data)
        # 若接口返回值中不存在price，接口调用失败
        if 'price' not in quey_resp:
            log.error(f"定价查询接口调用失败，接口返回值为：{quey_resp}")
            raise Exception(f"定价查询接口调用失败，接口返回值为：{quey_resp}")

        log.info(f"风控{mockType}: 【用户定价】mock结果：{quey_resp['price']}")

        return price

    # 额度mock
    def quota_mock(self, uid, credit_limit):
        """
        mock 用户的总额度
        :param uid: 用户uid， int/str格式
        :param credit_limit: 总额度，int格式
        :return:
        """

        if not (isinstance(credit_limit, (int, float)) and credit_limit > 0):
            raise Exception(f"传入的credit_limit：{type(credit_limit)} 不是正整数！")

        # 1, 组装额度mock入参，默认乐卡额度
        mock_data = {
            'interface': 'com.fenqile.rc.credit.manage.service.RcWhitelistService',
            'method': 'updateQuotaInfo',
            'env': self.cur_env,
            'group': self.group,
            'params': [
                {
                    "creditGrowth": 0,
                    "creditTemp": 0,
                    "uid": int(uid),
                    "creditGeneralPool": 0,
                    "tempBeginTime": "1970-01-01 00:00:00",
                    "creditCash": int(credit_limit),
                    "creditLimit": int(credit_limit),
                    "tempEndTime": "1970-01-01 23:59:59",
                    "creditCardType": 100,
                    "creditShadow": 0,
                    "creditShort": 0,
                    "operator": "ZSPT_system"
                }
            ]
        }
        # 2，执行rpc接口mock
        mock_resp = BaseRpc.exec_rpc(mock_data)

        if mock_resp['errcode'] == 0:
            log.info("额度mock接口调用成功！")
        else:
            raise Exception("额度更新接口调用异常，mock失败！")

        # 3，rpc接口查询当前乐卡总额度
        query_data = {
            'interface': 'com.fenqile.server.quota.business.service.UserCurrentCreditQueryService',
            'method': 'creditQuery',
            'env': self.cur_env,
            'params': [int(uid)]
        }
        query_resp = BaseRpc.exec_rpc(query_data)

        if query_resp:
            log.info(f"{uid}的当前乐卡额度金额为：{query_resp.get('creditLine', '-1')}")
        else:
            raise Exception("额度查询接口调用异常，未正确返回！")

    # 用户风险等级mock
    def rr_v2_mock(self, uid, rr_level="R2", orderId="O12456789"):
        """
        mock 用户RR等级
        :param uid: 用户uid， int/str格式
        :param rr_level: rr等级， str格式，枚举 R1~R8 , 默认R2
        :param orderId: 订单id，授信流程mock建议传入授信单号
        :return:
        """
        rr_set = ['R1', 'R2', 'R3', 'R4', 'R5', 'R6', 'R7', 'R8']
        if not (isinstance(rr_level, str) and (rr_level in rr_set)):
            raise Exception(f"传入的rr_level：{type(rr_level)} -- {rr_level} 格式不正确！")

        # 1, mock rr_level
        mock_data = {
            'interface': 'com.fenqile.realtime.rr.service.UpdateRrService',
            'method': 'updateRr',
            'env': self.cur_env,
            'group': self.group,
            'params': [{
                "uid": uid,
                "rrLevel": rr_level,
                "rrVersion": "V1",
                "scene": 199,
                "businessId": orderId
            }]
        }
        # 执行rpc接口调用
        mock_resp = BaseRpc.exec_rpc(mock_data)
        if mock_resp['errcode'] != 0:
            log.error(f"mock失败，接口返回值为：{mock_resp}")
            raise Exception(f"mock失败，接口返回值为：{mock_resp}")

        # 2，rr_level 查询
        query_data = {
            'interface': 'com.fenqile.anti_fraud.afstatistics.service.RuleEngineParamsAfStatisticsService',
            'method': 'getRcEngineParams',
            'env': self.cur_env,
            'params': [{
                "className": "rcEngineParamsRrLevelService",
                "functionName": "rrLevel",
                "uid": uid
            }]
        }
        # 执行rpc接口调用
        quey_resp = BaseRpc.exec_rpc(query_data)
        if ('result_rows' not in quey_resp) and ('rr_level_v2' not in quey_resp['result_rows'][0]):
            log.error(f"rr_level查询失败，接口返回值为：{quey_resp}")
            raise Exception(f"rr_level查询失败，接口返回值为：{quey_resp}")

        log.info(f"mock成功，uid: {uid} 的 rr_level值为：{quey_resp['result_rows'][0]['rr_level_v2']}")

        return True


# class MockOperation:
#     def __init__(self):
#         self.proxies = {'http': 'http://10.9.22.52'}  # 预留可设置代理
#         self.headers = {'Content-Type': 'application/json',
#                         'Cookie': 'client_type=h5; fs_tag=7FA2565E2CBE36DB2DF0974F273F65AB; isc=LINK_BUYCART.MES202003270237290; _ISC={"key":"_ISC","value":"99VIP_DDXQY_TITLE","time_stamp":1656322248541}; choose_product_id=1; _CSC={"key":"_CSC","value":"CASH.HOME.00000001","expire":300,"priority":0,"time_stamp":1662633884779}; x-s3-tid=7fde1908ad7a3ae2c7b8f11332cabd924ab67863::c0e1cb32-0393-4f35-b5d2-9d89fcd19ba5:fbb4d70c83%3Bbd985eb005de78b80a9b4411c7c5dfde%3A2a9bc719927d52e91f5dcc37111b3062%3A56a04966a34766e80feb4b165730a850%3Aa6982533cdafb4f88b964a7b23f35e39; x-s3-s4e=D90aAmddrvxMv2h71vJm%2FIk2MoOPO48e8TGXVNhQZIJxPVj3Xuh5rHclEpvGgKCFMtX2cRwL06sXK%2Bp33xPJrpRVW2ozqI0C39XmgN%2BBQ7U45S9SROJVJjdgxV4hjh8EX7BiHsgQ58YM7BriXbQ2bClIbXTstUUqKYsPi50FmPag1IRkjaRKtDW7BkqaOacj3kBRSC4VhD1nxFMd54qjQaNBNzrrPJimGAgZ2V2DJisl1yVWZcLUDEL8%2F%2FsvKKn4utfKzRm%2Frf1yeV8QkT9h%2BXKgbJGMQULDe8DY5d2E3%2BCFm4ErkXYj4JOxMNmepU9zlEVWYDP2K%2BpstsjjXmdQB86%2F9Vc6gAxQ0homoDyh75IziQCXUDMG2nvone1%2FKc9ydq%2FqivbyQ3FqdUMIoVEcbEgOw1x5kgc%2BnbQRWT8dEYfjAcaWvbJ2iZpua%2F5T5lLdf33cpRHcQTrlya2Mt3Ot2cdeFH1TZgI8EiKanwAx3to%2FQznGuH2nskdcaebVt9nz6%2BBnJQsCj4U4jSZgYbxLwIoGkUJEt2QQ6%2Bcv7FS6x7ogXs3z5L0kTwGSqucNO8s3Aa7YVAFL2CtDCnDkgrsH34Nex7XlDfjtx7shscsk9N62BFhJeO8zsC8n7bbiA6d0KYPav5x8Z%2BZu2fQ9Q3K6GjnYdoDgYaz6xQ%2FKp%2FfUTDkg%2FyXbI%2FlRWvHZkYRlGKgvWe3ONBtdqHrXiarfa0VcGX6xBUAtsKC6eNgXdNvNUf6YGN%2Fd3wiPf57BNIMW%2FYFjNPZeW2sCMERlHC7xaptfJkkPIWHq%2Fp0pJw64u72bAggI6tTfqcof0StDK2MnkE5qHLASUfMmluAtdmSxsOvwsA%3D%3D3sSs7fde1908ad7a3ae2c7b8f11332cabd924ab67863::c0e1cb32-0393-4f35-b5d2-9d89fcd19ba5:fbb4d70c83; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2210000001259%22%2C%22%24device_id%22%3A%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%2C%22props%22%3A%7B%7D%2C%22first_id%22%3A%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%7D; sensorsdata2015session=%7B%7D; hawkeye_access_id=c30fc099-a60e-4236-8e21-40e3cb6a469d; fp=bb0bf7a7988da71eafad0545f3b9d7c2; channel_extend_info={"entry":"","channel":"","csc":"","min":"jeremyzha*","mid":"36623","retcode":30181032,"fs_tag":"7FA2565E2CBE36DB2DF0974F273F65AB"}; session=cf6ed42010ca43e5838ebd39678cf63e; mid=36623; Hm_lvt_6617828cdccae4d04f1557b9a67df803=1696731505; Hm_cv_6617828cdccae4d04f1557b9a67df803=1*uid*36623; fit_app_id=1000; _SUTC=s_c7d400da4f226ab6b9cf348c6e12f6e1; _SUTC_AUTH=1; www_token_id=ymao95HnxA6m1%2FFVDcbfui6AXqP%2BxBEh10I96wiMVWe%2FCDVsad2M0AMQFsN2DQ7AW4KFwA90yePfTM6A2sNo8Q%3D%3D; uid=4051565; oa_session=mampk0vehvlp86kb6jtdfh1bq2; Hm_lpvt_6617828cdccae4d04f1557b9a67df803=1698051292; _ffukey=36623; oa_token_id=v26srKD9iDFtObHYNmLOwR3PYUe6Z0APKRzDuNUrKwE85fPom80WQqI7Vkw32KhtoE%2BfD0UaHCIjBP7W%2BHzMRA%3D%3D; rog_session_test=64e7f734d4331f9d333039f0d8d311c1; rog_session=9d7fde493aee97caeb00618399086bf4'
#                         }
#
#     def fsm_mock(self, uid, data: dict):
#         '''
#         fsm字段mock函数，支持单字段和多个字段
#         :param uid: 用户uid
#         :param data: dict格式， 如 {'rr_level_daily_combo_1point5': 'R1', 'rr_fq_lc_daily_combo_1point5': '0.0001'}
#         :return: 返回mock结果， 全部成功返回为 {"retmsg":"success","retcode":"0"}, 如果有失败，返回{"retmsg":"fail","retcode":"错误码"，"result_rows":[字段名]}
#         '''
#
#         url = r'https://hawkeye.oa.fenqile.com/rc_oa_gateway/credit/rc_test/update_user_fsm'
#         requests.packages.urllib3.disable_warnings()
#         resp = {'retmsg': 'success', 'retcode': '0', 'error_fsm': []}  # 设置初始返回值，默认成功
#
#         for key in data.keys():
#             tmp_data = {"uid": uid, "field_name": key, "field_value": data[key]}
#             tmp_resp = requests.post(url, data=tmp_data, headers=self.headers, verify=False)
#             if tmp_resp.json()['retmsg'] != 'success':  # 如果某个字段mock失败，修改返回结果
#                 resp['error_fsm'].append(key)
#                 resp['retcode'] = '5200001'
#                 resp['retmsg'] = 'fail'
#         print("mock结果：", resp)
#         return resp


#     def process_mock(self, uid: int, processId: str, mockType: int, mockRes: dict):
#         '''
#         流程mock，支持指定流程mock指定结果，区分风控1.0和风控2.0
#         :param uid: 用户uid
#         :param processId: 流程id，字符串格式
#         :param mockType: 区分风控1.0和2.0， 1.0传1，2.0传0
#         :param mockRes: dict类型，区分三大类，1.0授信流程，1.0交易流程，2.0流程
#             /*1.0流程：定价取分位，approval_result:1通过，2转人工，3拒绝，额度为整数*/
#             1.0授信流程： {"risk_pricing":2400,"approval_result":1,"credit_cash":15000,"credit_limit":15000}, --- 授信流程，四个参数必填
#             1.0交易流程：{"risk_pricing":3600,"approval_result":1,"cause_codes":[]}，--- 交易流程，仅approval_result必填
#
#             /*2.0流程：定价取整数，approval_result:0通过，1转人工，2拒绝， 99中断，额度为整数*/
#             2.0流程：{"approval_result":0,"cause":[""],"disposal_codes":"","price":20,"credit_limit":15000,"credit_cash":15000} --- 授信流程，额度定价必填， 交易流程可不输出额度和定价
#         :return:
#         '''
#         requests.packages.urllib3.disable_warnings()
#         if mockType == 1:  # 风控1.0
#             # 1, 新增流程，如果流程已经存在，则跳过，执行流程mock
#             url_add = r'https://stable-hawkeye.oa.fenqile.com/rc_oa_gateway/credit/rc_test/add_test_plan'
#             add_req = json.dumps({"uid": uid, "mock_type": mockType, "rc_process_id_list": [processId]})
#             print(type(add_req), add_req)
#             add_resp = eval(requests.post(url_add, data=add_req, headers=self.headers).text)
#             # print(type(add_resp),add_resp)
#             if add_resp['retmsg'] != 'success' and int(
#                     add_resp['retcode']) != 19401014:  # 如果返回值为19401014，则表示流程已添加，可直接执行mock
#                 raise Exception(f'添加异常，结果返回为{add_resp}')  # 添加异常，抛错
#             print(f'1.0流程{processId}添加结果: {add_resp}')
#
#             # 2, 查询流程列表，获取index参数，后续mock需要使用
#             url_query = f'https://hawkeye.oa.fenqile.com/rc_oa_gateway/credit/rc_test/query_test_plan_with_page?uid={uid}&rc_process_id=&app_id=&operator=&page=1&limit=10&valid_status=&process_id=&flow_source=2'  ##source值
#             query_resp = eval(requests.get(url_query, headers=self.headers, verify=False).text)
#             print(type(query_resp), query_resp)
#             index = query_resp['result_rows'][0]['index']
#             print(type(index), index)
#
#             # 3，执行流程mock
#             url_mock = r'https://hawkeye.oa.fenqile.com/rc_oa_gateway/credit/rc_test/update_test_plan_mock_result'
#             mockRes['risk_code'] = mockRes['risk_code'] if 'risk_code' in mockRes else '[]'
#             mock_req = json.dumps({"index": index, "mock_result_bean": {"risk_pricing": mockRes['risk_pricing'],
#                                                                         "approval_result": mockRes['approval_result'],
#                                                                         "flow_mock_type": 0,
#                                                                         "credit_cash": mockRes['credit_cash'],
#                                                                         "credit_limit": mockRes['credit_limit'],
#                                                                         "risk_code": mockRes['risk_code']},
#                                    "mock_type": mockType})
#             mock_resp = eval(requests.post(url_mock, data=mock_req, headers=self.headers, verify=False).text)
#             print(f'1.0流程{processId}mock结果: {mock_resp}')
#
#             return mock_resp['retmsg']
#
#         elif mockType == 0:  # 风控2.0
#             # 1, 新增流程，如果流程已经存在，则跳过，执行流程mock
#             url_add = r'https://hawkeye.oa.fenqile.com/rc_oa_gateway/hawk_decision/process-engine/process/batch_relate_mock.json'
#             add_req = json.dumps({"uid": uid, "mock_type": mockType, "process_id_list": [processId]})
#             # print('data:',type(add_req),add_req)
#             print('2.0--url:', url_add)
#             print('2.0--headers:', type(self.headers), self.headers)
#             add_resp = eval(requests.post(url_add, data=add_req, headers=self.headers, verify=False).text)
#             # print(type(add_resp),add_resp)
#             if add_resp['retmsg'] != 'OK':
#                 raise Exception(f'添加异常，结果返回为{add_resp}')
#             print(f'2.0流程{processId}添加结果: {add_resp}')
#
#             # 2，执行流程mock
#             url_mock = r'https://hawkeye.oa.fenqile.com/rc_oa_gateway/hawk_decision/process-engine/process/save_mock_config.json'
#             output = {
#                 'approval_result': mockRes['approval_result'],
#                 'cause': mockRes['cause'],
#                 'disposal_codes': mockRes['disposal_codes'],
#                 'tag_codes': [],
#                 'untag_codes': [],
#                 'credit_extra_data': {},
#                 'price': mockRes['price'],
#                 'credit_limit': mockRes['credit_limit'],
#                 'credit_cash': mockRes['credit_limit']
#             }
#             # print(output)
#             mock_req = json.dumps({"uid": uid, "process_id": processId, "mock_type": mockType, "valid_status": 0,
#                                    "mock_result": {"approval_result": mockRes['approval_result'], "output": output}})
#             print('2.0--url:', url_mock)
#             print('2.0--headers:', type(self.headers), self.headers)
#             mock_resp = eval(requests.post(url_mock, data=mock_req, headers=self.headers, verify=False).text)
#             print(f'2.0流程{processId}mock结果:  {mock_resp}')
#
#             return mock_resp['retmsg']
#
#         else:
#             raise Exception('mock类型传值错误！')
#
#     def price_mock(self, env='stable'):
#         uid = '4055727'
#         processId = '1585'
#         mockRes = {
#             "risk_pricing": 3600,
#             "approval_result": 1,
#             "credit_cash": 10000,
#             "credit_limit": 10000,
#             "cause_codes": [],
#             "risk_code": "18.88"
#         }
#         self.process_mock(uid=uid, processId=processId, mockType=1, mockRes=mockRes)


if __name__ == '__main__':
    # uid = 3116166
    # process_id = '1255'
    # mock_req = [{
    #     "ruleSetId": 98563,  # 决策节点id
    #     "nodeMockType": 2,  # mock类型（1-修改输入，2-修改输出）
    #     "opMemo": "",  # 备注，非必填
    #     "fieldInfo": [{
    #         "fieldName": "RC_TAG_CODE",  # 字段名
    #         "fieldValue": "ZJFLJ02"  # 字段值
    #     }]
    # }]
    # # RiskMock('stable').process_node_mock(uid=uid, process_id=process_id, mock_req=mock_req)
    # RiskMock('stable').process_mock_valid(status=2, uid=uid, process_id="1255")

    # # 1，FSM字段mock
    uid = 4080302  # 4059476  # 4059397 #

    FSM_list = {
        # 'ascore_mob4_v3_1': '539.0',
        # 'jsjq_sx_fpd7_score_v2': '596.0',
        # 'tx_fraud_model3_score': '0.652518',
        # 'rh_fusion_ascore_v6_2': '499.0',
        # 'rh_fusion_ascore_v7_2': '532.0',
        # 'ant_xj_score': '0.07932814',
        # 'jsjq_sx_fpd7_score_v1': '623.0',
        # 'dxm_lxa_v3_seg123_score': '386.0',
        # 'xin_aliyun_anti_fraud_v4_score': '47.23',
        # 'feducational_level': '03-本科',
        # 'xin_pc_report_model_score1_db': '0.211041064',
        # 'xin_person_credit_szan_available_db': '1',
        # 'xin_person_credit_szan_model1_score_db': "",
        # "fif_new_csx_reoffer_uid": "1",
        # "pboc_model_rd_online_credit_dpd30_lgb_db": "1.0",
        # "xin_pc_report_model_score_available_db": "1",
        # "xin_pc_report_model_score2_db": "",
        # "xin_pc_report_model_score2_db": "",
        "xin_id_name_match": "1",
        "xin_id_credit_status":"1",
    }
    RiskMock(env='pre', group='default').fsm_mock(uid=uid, data=FSM_list)
    # MockOperation().fsm_mock(uid=uid, data=FSM_list)

    # 2, 风控1.0流程mock
    # uid = 3021376  # 3105937#3109107
    # # 授信流程
    # process_id = 'Q604101000152'
    # mock_req = {
    #     "risk_pricing": 2400,
    #     "approval_result": 1,
    #     # "credit_cash": 12000,
    #     "credit_limit": 14000
    # }
    # # 系统流程
    # # process_id = '2484'  # '1029'
    # # mock_req = {
    # #     "approval_result": 1,
    # #     'risk_code': '18.84',
    # #     'cause_codes': ["D0001"]
    # # }
    #
    # RiskMock('stable').process_mock_v1(uid=uid, process_id=process_id, mock_req=mock_req)

    # 3, 风控2.0流程mock
    # uid = 3123234  # 3109107
    # process_id = 'SP00000505'
    # mock_req = {
    #     "approval_result": "0",
    #     "cause": [""],
    #     "disposal_codes": "",
    #     "tag_codes": "",
    #     "untag_codes": [],
    #     "credit_extra_data": {},
    #     "offer_code": 102,
    #     "offer_status": 1,
    #     "price": 0,
    #     "max_period": 1,
    #     "min_period": 3,
    #     "credit_limit": 5000,
    #     "credit_cash": 5000,
    #     "effective_end_time": "20241031"
    # }
    #
    # RiskMock('stable').process_mock_v2(uid=uid, process_id=process_id, mock_req=mock_req)

    # 4, 风控定价mock
    # uid = 3110287  # 3109107
    # price = 18
    # RiskMock('stable').price_mock(uid=uid, price=price, businessType=10, businessScene=230, mockType='2.0')

    # 5, RR风险等级mock
    # uid = 3110287  # 3109107
    # rr_level = "R2"
    # RiskMock().rr_v2_mock(uid=uid, rr_level=rr_level)

    # # 6，额度mock
    # uid = 3021376  # 3109107
    # credit_limit = 12000
    # RiskMock('stable').quota_mock(uid=uid, credit_limit=credit_limit)

    # data = {
    #     'interface': 'com.dshamc.cia.financing.service.web.condition.ChannelBaseInfoWebService',
    #     'method': 'queryByPage',
    #     'params': [{
    #         "systemChannelCode": 2248,
    #     }]
    # }
    # res = BaseRpc.exec_rpc(data)
    # print(type(res), res)
