# -*- coding: utf-8 -*-
"""
# @File    : riskMock.py
# @Date    : 2024-10-29
# @Author  : jeremyzhai
"""

from utils.handle_log import log
from common.rpcAction import BaseRpc
from datetime import datetime

# 风控mock，支持mock FSM字段和风控流程
class RiskMock:
    def __init__(self, env='stable', group='stable'):
        self.cur_env = env
        self.group = group

    # fsm 字段mock
    def fsm_mock(self, uid, data: dict, valid_days=30):
        """
        fsm字段mock函数，支持单字段和多个字段
        :param valid_days: mock生效时间，默认30天
        :param uid: 用户uid,
        :param data: dict格式， 如 {'rr_level_daily_combo_1point5': 'R1', 'rr_fq_lc_daily_combo_1point5': '0.0001'},
        :return: 返回mock结果，
            全部成功返回为 {"ret_msg":"success","ret_code":"0"}, 如果有失败，返回{"ret_msg":"fail","ret_code":"错误码"，"error_fsm":['字段名']}
        """
        if not isinstance(data, dict):
            raise Exception("输入的请求参数非dict类型")

        # 设置初始返回值，默认成功
        resp = {
            'ret_msg': 'success',
            'ret_code': '0',
            'error_fsm': []
        }

        ''' 批量mock接口'''
        # 特征mock上线，更换底层mock接口
        params = {
            "featureMockDetails": [{
                "uid": uid,
                "featureName": str(key),
                "mockValue": str(data[key])
            } for key in data.keys()],
            "validDays": valid_days,
            "invoker": "1218",
            "appSecret": "ZR7wwC0vPgs4Lstn",
            "operator": "ZSPT_system"
        }
        # 1，组装rpc接口参数
        mock_data = {
            'interface': 'com.fenqile.risk.feature.platform.portal.service.featureextension.mock.FeatureMockOperateService',
            'method': 'batchSet',
            'env': self.cur_env,
            'group': self.group,
            'params': [params]
        }

        # 2，执行rpc接口调用
        tmp_resp = BaseRpc.exec_rpc(mock_data, "【FSM字段批量mock】")

        # 如果某个字段mock失败，修改返回结果
        if tmp_resp is not None:
            resp['error_fsm'] = tmp_resp['failedDetails']
            resp['ret_code'] = '5200001' if not tmp_resp['success'] else '0'
            resp['ret_msg'] = tmp_resp

        log.info(f"mock结果: {resp}")
        return resp

    # 特征批量mock，支持多uid多个不同特征
    def fsm_batch_mock(self, mock_details: list, valid_days=30):
        """
        支持批量mock不同uid的不同特征值
        :param mock_details: [{
                                    "feature_name": "age",
                                    "mock_value": "40",
                                    "uid": 4111268
                            },{} ]
        :param valid_days: 默认30天，枚举[30,90,180,360]
        :return:
        """
        if not isinstance(mock_details, list):
            raise Exception("输入的请求参数非list类型")

        # 设置初始返回值，默认成功
        resp = {
            'ret_msg': 'success',
            'ret_code': '0',
            'error_fsm': []
        }
        params = {
            "featureMockDetails": [{
                "uid": p['uid'],
                "featureName": p['feature_name'],
                "mockValue": p['mock_value'],
            } for p in mock_details],
            "validDays": valid_days,
            "invoker": "1218",
            "appSecret": "ZR7wwC0vPgs4Lstn",
            "operator": "ZSPT_system"
        }
        # 1，组装rpc接口参数
        mock_data = {
            'interface': 'com.fenqile.risk.feature.platform.portal.service.featureextension.mock.FeatureMockOperateService',
            'method': 'batchSet',
            'env': self.cur_env,
            'group': self.group,
            'params': [params]
        }

        # 2，执行rpc接口调用
        tmp_resp = BaseRpc.exec_rpc(mock_data, "【FSM字段批量mock】")

        # 如果某个字段mock失败，修改返回结果
        if tmp_resp is not None:
            resp['error_fsm'] = tmp_resp['failedDetails']
            resp['ret_code'] = '5200001' if not tmp_resp['success'] else '0'
            resp['ret_msg'] = tmp_resp

        log.info(f"mock结果: {resp}")
        return resp

    # 失效全量特征mock
    def del_feature_mock(self, uid, feature_name_list=['user_all_credit_tag_code'], expire_type='all') -> None:
        """
        失效指定uid全量m特征ock，暂不开放指定特征失效
        :param feature_name_list: 失效字段列表
        :param expire_type: 失效类型，默认失效全部all，not_all否则失效指定字段列表
        :param uid:
        :return:
        """
        expired_details = []
        if expire_type == 'all':
            expired_details.append({
                "uid": int(uid),
                "expiredAll": True
            })
        else:
            for feature_name in feature_name_list:
                expired_details.append({
                    "uid": int(uid),
                    "featureName": feature_name
                })

        params = {
            "expiredDetails": expired_details,
            "invoker": "1218",
            "appSecret": "ZR7wwC0vPgs4Lstn",
            "operator": "ZSPT_system"
        }
        # 1，组装rpc接口参数
        mock_data = {
            'interface': 'com.fenqile.risk.feature.platform.portal.service.featureextension.mock.FeatureMockOperateService',
            'method': 'batchExpired',
            'env': self.cur_env,
            'group': self.group,
            'params': [params]
        }

        # 2，执行rpc接口调用
        BaseRpc.exec_rpc(mock_data, "【特征mock失效】")

    # CDP标签批量mock，支持多uid多个不同标签
    def label_batch_mock(self, mock_details: list):
        """
        支持批量mock不同uid的不同标签值
        :param mock_details: [{
                                    "fieldName": "age",
                                    "fieldValue": "40",
                                    "uid": 4111268
                            },{} ]
        :return:
        """
        if not isinstance(mock_details, list):
            raise Exception("输入的请求参数非list类型")

        # 设置初始返回值，默认成功
        resp = {
            'ret_msg': 'success',
            'ret_code': '0',
            'error_fsm': []
        }
        params = {
            "fieldMockParamsList": [{
                "uid": p['uid'],
                "fieldName": p['fieldName'],
                "fieldValue": p['fieldValue'],
            } for p in mock_details],
            "invoker": "cdp-master",
            "token": "jfYiaSCGRJo21vtP" if self.cur_env=='stable' else "PflcC0AVVTvnulGV",
        }
        # 1，组装rpc接口参数
        mock_data = {
            'interface': 'com.fenqile.label.portal.service.service.FieldMockAggregatedService',
            'method': 'batchMockFieldValues',
            'env': self.cur_env,
            'group': self.group,
            'params': [params]
        }

        # 2，执行rpc接口调用
        tmp_resp = BaseRpc.exec_rpc(mock_data, "【CDP标签批量mock】")

        # 如果某个字段mock失败，修改返回结果
        if tmp_resp is not None:
            resp['error_fsm'] = tmp_resp['results']
            resp['ret_code'] = '5200001' if not tmp_resp['success'] else '0'
            resp['ret_msg'] = tmp_resp.get('message','')

        log.info(f"mock结果: {resp}")
        return resp

    # 失效指定uid全量标签mock
    def del_label_mock(self, uid) -> None:
        """
        失效指定uid全量标签mock
        :param uid:
        :return:
        """
        # 1，组装rpc接口参数
        mock_data = {
            'interface': 'com.fenqile.label.portal.service.service.FieldMockAggregatedService',
            'method': 'deleteMockedFieldValues',
            'env': self.cur_env,
            'group': self.group,
            'params': [{
            "uid": int(uid),
        }]
        }

        # 2，执行rpc接口调用
        BaseRpc.exec_rpc(mock_data, "【标签mock失效】")

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
            # raise Exception("输入的请求参数不是dict类型！")
            raise Exception("输入的请求参数非dict类型")

        ''' rpc 接口'''
        # 1，判断process_id 是授信流程还是系统流程
        if isinstance(process_id, int) or process_id.isdecimal():
            # 系统流程，纯数字
            flow_source = '2'
        elif isinstance(process_id, str) and process_id[0] == 'Q' and process_id[1:].isdecimal():
            # 授信流程，以Q开头, 其余均为数字
            flow_source = '1'
        else:
            # raise ValueError(f"传入的流程id：{process_id}，不合法！")
            raise Exception(f"传入的流程id：{process_id}，不合法")

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
                # raise Exception(f"流程{process_id}添加异常,错误码：{add_resp['errcode']}，错误信息：{add_resp['errmsg']}")
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
        mock_resp = BaseRpc.exec_rpc(mock_data, desc='【流程mock生效/失效】')
        if isinstance(mock_resp, int):
            # log.info("rpc接口调用成功")
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
                log.info(f"更改流程：{process_id} 状态为失效status={process_status}成功！")
            elif process_status == 1:
                log.info(f"更改流程：{process_id} 状态为生效status={process_status}成功！")
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
            # raise Exception("输入的请求参数不是dict类型！")
            raise Exception("输入的请求参数非dict类型")


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
                            "cause": [""],
                            "disposal_codes": mock_req.get('disposal_codes', ''),
                            "tag_codes": [],
                            "untag_codes": [],
                            "credit_extra_data": {},
                            # "price": mock_req.get('price', 24),
                            "credit_limit": mock_req.get('credit_limit', -2),
                            "credit_cash": mock_req.get('credit_cash', -2)
                        }
                    }
                }
            ]
        }
        # 覆盖更新mock参数
        mock_data['params'][0]['mockResult']['output'] = {**mock_data['params'][0]['mockResult']['output'],
                                                          **mock_req}
        # 2，执行rpc接口调用
        mock_resp = BaseRpc.exec_rpc(mock_data, desc='【流程mock】')

        # 若接口返回值不为0，接口调用失败
        if mock_resp['retcode'] != '0':
            log.error(f"mock失败，接口返回值为：{mock_resp}")
            raise Exception(f"mock失败，接口返回值为：{mock_resp}")

        log.info(
            f"流程：{process_id} mock成功，状态valid_status：{valid_status}, rpc接口返回值为：{mock_resp['retcode']}，返回信息为：{mock_resp['retmsg']}")

        return mock_resp

    # 批量流程mock
    def batch_process_mock(self, uid, process_list: list) -> None:
        """
        授信流程批量mock
        :param uid:
        :param process_list: 流程列表
        :return:
        """
        post_data = {"uid": uid, "processIdList": process_list}
        data = {
            "interface": "com.fenqile.process.engine.console.service.gateway.process.ProcessGatewayService",
            "method": "batchRelateMock",
            "env": self.cur_env,
            "group": self.group,
            "params": [post_data]
        }
        resp = BaseRpc.exec_rpc(data, "【流程列表批量mock】")

        log.info(f"批量mock结果: {resp}")


if __name__ == '__main__':
    # # 1，FSM字段mock
    # uid = 4014615  # 4059476  # 4059397 #
    #
    # FSM_list = {
    #     'is_rc2_credit_flow': 2,
    #     'heitong_bloan_risk_level': 'H',
    #     'days_after_auth': 1,
    #     'age': 26
    # }
    # RiskMock(env='stable', group='stable').fsm_mock(uid=uid, data=FSM_list, valid_days=90)

    mock_details = [      {
                "fieldName": "fjbxx_zhxx_mobile",
                "uid": 3116166,
                "fieldValue": 1
            }]
    RiskMock(env='stable', group='stable').label_batch_mock(mock_details=mock_details)

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
    # uid = 3105937  # 3109107
    # process_id = 'P00000150'
    # mock_req = {
    #     "approval_result": 0,
    #     "price": 20.48,
    #     "credit_limit": 15000
    # }
    #
    # RiskMock('stable').process_mock_v2(uid=uid, process_id=process_id, mock_req=mock_req)
