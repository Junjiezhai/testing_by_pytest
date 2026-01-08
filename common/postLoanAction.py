# -*- coding: utf-8 -*-
"""
# @File    : postLoanAction.py
# @Date    : 2025-07-12
# @Author  : jeremyzhai
"""
import os
import time

import requests
import json
import traceback
import urllib3
from utils.handle_log import log
from assert_code.assert_decorators import post_loan_touch_assert
from common.rpcAction import BaseRpc
from jsonpath import jsonpath


# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def query_user_all_info(uid, env='stable', keys=None):
    """
    查询用户全量信息，包括手机号，出账日等
    :param env: 环境
    :param keys: 查询的结果key，驼峰命名， 支持传入字符串，或字符串列表， 不传返回全部查询结果
    :param uid: int/str
    :return:
    """
    data = {
        'interface': 'com.fenqile.user.user.service.UserQueryService',
        'method': 'queryAll',
        'env': env,
        'group': 'stable' if env == 'stable' else 'default',
        'params': [{"uid": int(uid)}]
    }
    res = BaseRpc.exec_rpc(data, desc='【用户全部信息查询】')

    if keys is None:
        resp = res
    elif isinstance(keys, str):
        resp = jsonpath(res, f'$..{keys}')
    elif isinstance(keys, list):
        resp = dict()
        for key in keys:
            resp[key] = jsonpath(res, f'$..{key}')
    else:
        raise Exception(f'入参类型异常{type(keys)}，非str或list型')

    return resp


# 自动刷新cookie
class HttpAction:
    def __init__(self, cookie, proxy=None):
        """
        初始化http请求类，更新cookie(不同url对应的cookie不一样)
        :param cookie:
        """
        self.headers = {
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cookie': cookie
        }
        self.current_cookie = cookie  # 存储当前cookie
        # self.proxies = proxy  # 设置代理IP
        # 设置 Fiddler 代理
        self.proxies = {
            'http': 'http://127.0.0.1:8888',
            'https': 'http://127.0.0.1:8888'  # Fiddler 会解密 HTTPS 流量（需安装证书）
        }

    def refresh_cookie(self, url: str, login_data: dict, login_type: str = 'post') -> None:
        """
        刷新cookie的方法
        :param url: 登录接口URL
        :param login_data: 登录请求数据
        :param login_type: 登录请求类型，默认post
        """
        try:
            if login_type == 'post':
                response = requests.post(url, headers=self.headers, data=login_data, verify=True)
            elif login_type == 'get':
                response = requests.get(url, headers=self.headers, params=login_data, verify=True)
            else:
                raise Exception(f'传入的login_type:{login_type}非法， 非GET或POST！！！')

            if response.status_code == 200:
                # 从响应中获取最新cookie
                new_cookie = self._extract_cookie_from_response(response)
                if new_cookie:
                    self.current_cookie = new_cookie
                    self.headers['Cookie'] = new_cookie
                    log.info("Cookie刷新成功")
                else:
                    log.warning("从响应中未提取到Cookie")
            else:
                log.error(f"登录失败，状态码: {response.status_code}, 响应: {response.text}")
        except Exception as e:
            log.exception(f'刷新Cookie时发生的错误为：{traceback.format_exc()}')
            raise e

    def _extract_cookie_from_response(self, response: requests.Response) -> str:
        """
        从响应中提取Cookie
        :param response: 请求响应对象
        :return: 提取到的Cookie字符串
        """
        if response.cookies:
            # 将cookies对象转换为字符串
            cookie_str = '; '.join([f"{cookie.name}={cookie.value}" for cookie in response.cookies])
            return cookie_str
        return None

    # @retry(max_attempts=3, delay=1)
    def send_req(self, url: str, data: dict, req_type: str = 'get', desc='', print_res=True) -> dict:
        """
        发送http请求
        :param print_res: 是否打印出参
        :param desc: 描述
        :param req_type: 请求类型，默认get，支持post
        :param url:
        :param data: 请求数据的消息体
        :return:
        """
        # 1, 组装http请求的req
        req = {
            'req_type': req_type,
            'url': url,
            'data': data
        }
        log.info(f"【{desc}】请求的入参为:{req}")

        # 2, 发送http请求
        # ca_cert_path = r'C:\Users\jeremyzhai\Desktop\FiddlerRoot.cer'  # 替换为你的证书路径
        try:
            if req_type == 'post':
                response = requests.post(url, headers=self.headers, json=data, verify=False, proxies=self.proxies)

            elif req_type == 'get':
                response = requests.get(url, headers=self.headers, params=data, verify=False, proxies=self.proxies)

            else:
                raise Exception(f'传入的req_type:{req_type}非法， 非GET或POST！！！')

            # 3, 从响应中更新cookie
            new_cookie = self._extract_cookie_from_response(response)
            if new_cookie:
                self.current_cookie = new_cookie
                self.headers['Cookie'] = new_cookie
                log.debug("请求后自动更新了Cookie")

            if print_res is True:
                log.info(f"【{desc}】响应结果为：{response.status_code}, 出参为: {response.text}")
            else:
                log.info(f"【{desc}】响应结果为：{response.status_code}")

            return json.loads(response.text)
        except Exception as e:
            log.exception(f'发生的错误为：{traceback.format_exc()}')
            raise e


# 催收管理平台
class PostLoanPlat(HttpAction):
    def __init__(self, env='stable', use_proxy=False, proxy=None):
        self.env = env
        self.use_proxy = use_proxy  # 是否使用代理，如果使用，需要传proxy参数，dict格式
        super().__init__(self._set_cookie(), proxy=proxy)
        # 执行登录， 刷新cookie
        self.login()

    def _set_cookie(self):
        if self.env == 'stable':
            cookie = 'client_type=h5; fs_tag=7FA2565E2CBE36DB2DF0974F273F65AB; isc=LINK_BUYCART.MES202003270237290; ' \
                     '_ISC={"key":"_ISC","value":"99VIP_DDXQY_TITLE","time_stamp":1656322248541}; ' \
                     'choose_product_id=1; _CSC={"key":"_CSC","value":"CASH.HOME.00000001","expire":300,"priority":0,' \
                     '"time_stamp":1662633884779}; ' \
                     'sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2210000001259%22%2C%22%24device_id%22%3A' \
                     '%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%2C%22props%22%3A%7B%7D%2C' \
                     '%22first_id%22%3A%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%7D; ' \
                     'sensorsdata2015session=%7B%7D; channel_extend_info={"entry":"","channel":"","csc":"",' \
                     '"min":"jeremyzha*","mid":"36623","retcode":30181032,' \
                     '"fs_tag":"7FA2565E2CBE36DB2DF0974F273F65AB"}; cash_up_id=COM.guding_XQY_banner.LHJQ.JDDHBXQYXE; ' \
                     'Hm_lpvt_3592cc1c1f867054320b2773e17711c4=1718336908; x-s3-sid=TS122bM7n10ubtacro8; ' \
                     'fp=1555694878b65a7fa2bbe8f381a7b9c1; fit_app_id=1000; ' \
                     'www_token_id=Oqwe1NFZsxTvF1VZRxA%2F07b%2FWU%2BVYXmhPe22N1vrIWPtHJZSLlPkU0jbWV4fVPx0AvQawSBBdq' \
                     '%2BOH9%2F3ju13pA%3D%3D; uid=4104598; _SUTC=s_dee1e04cf1b94fb5106717d30b9b2bea; _SUTC_AUTH=1; ' \
                     'session=b1d06921c3eb4c5a986cf51fbf90c695 '
        else:
            # pre&gray&prod，共用同一个cookie
            cookie = ''
        return cookie

    def login(self, user_id='jeremyzhai', password='58d475602f84019b5be3c35430bff632'):
        """
        登录催收系统
        :param user_id: 用户名
        :param password: 密码，密文
        :return: dict, cookie和token等信息
        """
        # 1, 组装参数
        data = {
            "user_id": user_id,
            "password": password,
            "login_phone_system": 0,
            "device_sign": 0,
            "ip": "10.1.25.125"
        }

        # 3, 执行请求
        req_type = 'post'
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/front/login.json'
        else:  # 预发布及灰度，或者项目环境，需指定代理
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/front/login.json'

        resp = self.send_req(url=url, data=data, req_type=req_type, desc='登录', print_res=True)
        # log.info(resp)

        self.token = resp['result_rows']['token']
        self.mid = resp['result_rows']['mid']
        log.info(f"token: {self.token}, mid: {self.mid}")

    @post_loan_touch_assert
    def system_send_sms(self, msg_info: dict):
        """
        系统发送短信
        :param msg_info: 短信入参，需要包含案件id，队列id，短信模板和销售渠道
        :return:
        """
        # 1, 组装参数
        data = {
            "actual_tpl_id": msg_info["actual_tpl_id"],
            "msg_list": msg_info['msg_list'],
            "sell_channel_id": msg_info["sell_channel_id"],
            "token": f"{self.token}"
        }

        # 2, 执行发短
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/batchSend_sms.json'
        else:
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/batchSend_sms.json'

        self.send_req(url=url, data=data, req_type='post', desc='系统发送短信', print_res=True)

        # 3， db参数核对
        query_info = {
            "uid": msg_info['msg_list'][0]["uid"],
            "send_code": msg_info["actual_tpl_id"],
            # "queue_code": msg_info['msg_list'][0]["queue_code"],

        }

        return query_info

    @post_loan_touch_assert
    def system_send_app_sms(self, msg_info: dict):
        """
        系统发送APP短信
        :param msg_info: 短信入参，需要包含案件id，队列id，短信模板和销售渠道
        :return:
        """
        # 1, 组装参数
        data = {
            "actual_tpl_id": msg_info["actual_tpl_id"],
            "msg_list": msg_info['msg_list'],
            "sell_channel_id": msg_info["sell_channel_id"],
            "token": f"{self.token}"
        }

        # 2, 执行发短
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/batch_send_app.json'
        else:
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/batch_send_app.json'

        self.send_req(url=url, data=data, req_type='post', desc='系统发送APP短信', print_res=True)

        # 3， db参数核对
        query_info = {
            "uid": msg_info['msg_list'][0]["uid"],
            "send_code": msg_info["actual_tpl_id"],
            # "queue_code": msg_info['msg_list'][0]["queue_code"],
        }

        return query_info

    @post_loan_touch_assert
    def person_send_sms(self, msg_info: dict):
        """
        个人发送短信
        :param msg_info: 短信入参，需要包含案件id，队列id，短信模板和销售渠道
        :return:
        """
        # 1, 组装参数
        uid = msg_info['uid']
        # 1-1 查询用户信息
        user_info = query_user_all_info(uid=uid, env=self.env, keys=['name', 'mobile'])
        name, mobile = user_info['name'][0], user_info['mobile'][0]

        # 1-2, 获取icd
        data_icd = {
            "source_of_exclude": "3",  # 排除来源标识
            "order_by": "",  # 排序字段（空表示默认排序）
            "uid": f"{uid}",  # 用户ID
            "page": "1",  # 页码
            "limit": "10",  # 每页数据量
            "token": f"{self.token}"  # 认证令牌
        }
        if self.env == 'stable' and self.use_proxy is False:
            url_icd = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/front/contact/tuomin_query_filter_page.json'
        else:
            url_icd = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/front/contact/tuomin_query_filter_page.json'

        res = self.send_req(url=url_icd, data=data_icd, req_type='post', desc='获取icd', print_res=True)
        icd = res['result_rows'][0]['icd']
        relation = res['result_rows'][0]['relation']

        # 1-3 组装发短参数
        data = {
            "uid": f"{uid}",
            "icd": f"{icd}",
            "case_id": f"{uid}",
            "actual_tpl_id": msg_info["actual_tpl_id"],
            "contact_relation": f"{relation}",
            "contact_name": f"{name}",
            "phone": f"{mobile}",
            "appointed_time": "",  # 空值处理
            "sell_channel_id": msg_info["sell_channel_id"],
            "token": f"{self.token}"
        }

        # 2- 执行发短
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/send_sms'
        else:
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/send_sms'

        self.send_req(url=url, data=data, req_type='post', desc='系统发送短信', print_res=True)

        # 3， db参数核对
        query_info = {
            "uid": uid,
            "send_code": msg_info["actual_tpl_id"]
        }

        return query_info

    @post_loan_touch_assert
    def person_send_app_sms(self, msg_info: dict):
        """
        个人发送APP短信
        :param msg_info: 短信入参，需要包含案件id，队列id，短信模板和销售渠道
        :return:
        """
        # 1, 组装参数
        data = {
            "actual_tpl_id": msg_info["actual_tpl_id"],
            "case_id": msg_info['case_id'],
            "sell_channel_id": msg_info["sell_channel_id"],
            "token": f"{self.token}"
        }

        # 2, 执行发短
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/send_app_front.json'
        else:
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/send_app_front.json'

        self.send_req(url=url, data=data, req_type='post', desc='个人发送APP短信', print_res=True)

        # 3， db参数核对
        query_info = {
            "uid": msg_info["case_id"],
            "send_code": msg_info["actual_tpl_id"],
        }

        return query_info

    @post_loan_touch_assert
    def send_complaint_case_sms(self, msg_info: dict):
        """
        投诉处理-短信发送
        :param msg_info: 短信入参，需要包含operation，处理结果，短信模板和uid
        :return:
        """
        # 1, 组装参数
        # 1-1 获取cc_id
        uid = msg_info['uid']
        if self.env == 'stable' and self.use_proxy is False:
            url = f'https://stble-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/complaint_case/query_case_inpage?page=1&limit=10&label=1&operator=520&select_assignee=&collection_case_status=&uid={uid}&sort_asc=&sort_desc=&token={self.token}'
        else:
            url = f'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/complaint_case/query_case_inpage?page=1&limit=10&label=1&operator=520&select_assignee=&collection_case_status=&uid={uid}&sort_asc=&sort_desc=&token={self.token}'
        res = self.send_req(url=url, data={}, req_type='get', desc='获取cc_id', print_res=False)
        cc_id = res['result_rows'][0]['cc_id']

        # 1-2 组装发短参数
        data = {
            "op_memo": "测试",
            "collection_case_achieve_status": "",
            "assignee": "",
            "attach_url_json": [],
            "text_template": f'{msg_info["actual_tpl_id"]}',
            "email_template": "",
            "email_receiver_array": [],
            "handle_result": msg_info['handle_result'],
            "cc_id": cc_id,
            "contact_id": "",
            "contact_status": "",
            "connect_result": "",
            "operation": f'{msg_info["operation"]}',
            "update_index": "",
            "token": f"{self.token}"
        }

        # 2, 执行发短
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/complaint_case/handle_case'
        else:
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/complaint_case/handle_case'

        self.send_req(url=url, data=data, req_type='post', desc='投诉案件处理-发送短信', print_res=True)

        # 3， db参数核对
        query_info = {
            "uid": uid,
            "send_code": msg_info["actual_tpl_id"],
        }

        return query_info

    @post_loan_touch_assert
    def notify_others_app_sms(self, msg_info: dict):
        """
        第三方代还推送APP消息提醒
        :param msg_info: 短信入参，需要包含案件id，队列id，短信模板和销售渠道
        :return:
        """
        # 1, 组装参数
        uid = msg_info["uid"]
        data = f'case_id={uid}&actual_tpl_id={msg_info["actual_tpl_id"]}&token={self.token}'

        # 2, 执行发短
        if self.env == 'stable' and self.use_proxy is False:
            url = 'https://stable-cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/send_app.json' + '?' + data
        else:
            url = 'https://cs.fenqile.com/rc_oa_gateway/cgi-bin/collection/send_app.json' + '?' + data

        self.send_req(url=url, data={}, req_type='post', desc='第三方代还发送APP消息', print_res=True)

        # 3， db参数核对
        query_info = {
            "uid": uid,
            "send_code": msg_info["actual_tpl_id"],
        }

        return query_info

    # # 批量轮循执行发送短信场景
    # def batch_exec_send(self):
    #     log.debug("################## HTTP 接口触发场景 ########################")
    #     # 系统发送短信
    #     self.system_send_sms(msg_info={
    #         "actual_tpl_id": "collection100067",
    #         "msg_list": [{"uid": 3109737, "case_id": 3109737, "queue_code": "NC223"}],
    #         "sell_channel_id": 1
    #     })
    #
    #     # 系统发送APP信息
    #     self.system_send_app_sms(msg_info={
    #         "actual_tpl_id": "APP202405281041414",
    #         "msg_list": [{"uid": 3109737, "case_id": 3109737, "queue_code": "NC223"}],
    #         "sell_channel_id": 1
    #     })
    #
    #     # 个人发送APP信息
    #     self.person_send_app_sms(msg_info={
    #         "actual_tpl_id": "APP202405281041414",
    #         "sell_channel_id": 1,
    #         "case_id": 3109737,
    #     })
    #
    #     # 投诉案件发送短信
    #     self.send_complaint_case_sms(msg_info={
    #         "uid": 3311476,
    #         "actual_tpl_id": "SMS202209290351170",
    #         "handle_result": 0,
    #         "operation": 30,
    #     })
    #
    #     # 个人发送短信信息
    #     self.person_send_sms(msg_info={
    #         "uid": 3311476,
    #         "actual_tpl_id": "SMS202502111167766",
    #         "sell_channel_id": 1
    #     })
    #
    #     # 第三方代还发送APP信息
    #     self.notify_others_app_sms(msg_info={
    #         "uid": 3034508,
    #         "actual_tpl_id": "APP2020010810"
    #     })
    #
    #     # log.debug("################## RPC 接口触发场景 ########################")
    #     # tp = TouchPlatform(env='stable', group='project_1093914')
    #     # # 协商还发送短信 --RPC
    #     # msg_info = {
    #     #     "collectionSendModel": "USER_MANUAL",
    #     #     "scene": "还款工具",
    #     #     "uid": 3311476,
    #     #     "mobile": "13433638155",
    #     #     "tplId": "SMS202408021313380",
    #     #     "contentData": {
    #     #         "name": "张三",
    #     #         "url": "http://short.url/123",
    #     #         "customer_hotline": "400-800-9000"
    #     #     }
    #     # }
    #     # tp.negotiate_repay_send_sms(msg_info=msg_info)
    #     #
    #     # # 律师函发送短信 --RPC
    #     # msg_info = {
    #     #     "uid": "3034508",
    #     #     "contractUrl": "http://img1.fenqile.com/eleccontract3/M00/02/52/oZ8BAF6EC4-AaMGiAARxLTk8vXM557.pdf",
    #     #     "msgTemplate": "SMS202003102",
    #     #     "contractId": "S20200401128114950A0910DC4737508",
    #     #     "token": f"{self.token}"
    #     # }
    #     # tp.lawyer_letter_send_sms(msg_info=msg_info)
    #     #
    #     # # 系统发送短信 --RPC
    #     # msg_info = [
    #     #     3109737,
    #     #     {
    #     #         "fmode": 2,
    #     #         "sendOne": True,
    #     #         "fmsgTplId": 110,
    #     #         "ftplName": "heos自动短信",
    #     #         "fchannelType": 0,
    #     #         "fsendType": 20,
    #     #         "fsendObject": "[]",
    #     #         "fchannelId": 40,
    #     #         "fuserTagTypes": "[\"s3\",\"w1\",\"s2\",\"w2\",\"s1\"]",
    #     #         "fsellChannelIds": "[1]",
    #     #         "fsellChannelId": 1,
    #     #         "foverdueDays": "[\"100\"]",
    #     #         "fsendTime": "18:22",
    #     #         "factualTplId": "SMS202212201540962",
    #     #         "fopMemo": "",
    #     #         "foperator": "heoszhou",
    #     #         "fuseFlag": 1,
    #     #         "fcreateTime": "2025-07-11 16:39:11",
    #     #         "fmodifyTime": "2025-07-11 18:21:26",
    #     #         "fversion": 0,
    #     #         "fjgAutoTestId": "",
    #     #         "fuidSuffixs": "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]",
    #     #         "fqueueCodes": "[\"NC223\"]",
    #     #         "fdeliveryChannel": 0,
    #     #         "fappointedTime": "17",
    #     #         "fappointedOverdueDay": 0,
    #     #         "fqueueType": 10,
    #     #         "fdeliveryChannels": "",
    #     #         "factualTaskId": "",
    #     #         "ftemplateType": 0,
    #     #         "ftemplateContent": "",
    #     #         "ftemplatePic": "",
    #     #         "fworkplaces": "[]",
    #     #         "frandomRange": "",
    #     #         "fcompanyIdS": "[]",
    #     #         "fplatformType": 0,
    #     #         "fdetailChannelId": "",
    #     #         "fextendFields": "{}",
    #     #         "fallQueues": 0
    #     #     }
    #     # ]
    #     # tp.system_send_sms(msg_info=msg_info)
    #     #
    #     # # 系统发送APP消息 --RPC
    #     # msg_info = [
    #     #     3109737,
    #     #     {
    #     #         "fmode": 2,
    #     #         "sendOne": True,
    #     #         "fmsgTplId": 114,
    #     #         "ftplName": "heos-app自动",
    #     #         "fchannelType": 0,
    #     #         "fsendType": 20,
    #     #         "fsendObject": "[]",
    #     #         "fchannelId": 39,
    #     #         "fuserTagTypes": "[\"s3\",\"w1\",\"s2\",\"w2\",\"s1\"]",
    #     #         "fsellChannelIds": "[1]",
    #     #         "fsellChannelId": 1,
    #     #         "foverdueDays": "[\"100\"]",
    #     #         "fsendTime": "16:15",
    #     #         "factualTplId": "APP202304281355146",
    #     #         "fopMemo": "",
    #     #         "foperator": "heoszhou",
    #     #         "fuseFlag": 1,
    #     #         "fcreateTime": "2025-07-11 16:39:11",
    #     #         "fmodifyTime": "2025-07-11 18:21:26",
    #     #         "fversion": 0,
    #     #         "fjgAutoTestId": "",
    #     #         "fuidSuffixs": "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]",
    #     #         "fqueueCodes": "[\"NC223\"]",
    #     #         "fdeliveryChannel": 0,
    #     #         "fappointedTime": "17",
    #     #         "fappointedOverdueDay": 0,
    #     #         "fqueueType": 10,
    #     #         "fdeliveryChannels": "",
    #     #         "factualTaskId": "",
    #     #         "ftemplateType": 0,
    #     #         "ftemplateContent": "",
    #     #         "ftemplatePic": "",
    #     #         "fworkplaces": "[]",
    #     #         "frandomRange": "",
    #     #         "fcompanyIdS": "[]",
    #     #         "fplatformType": 0,
    #     #         "fdetailChannelId": "",
    #     #         "fextendFields": "{}",
    #     #         "fallQueues": 0
    #     #     }
    #     # ]
    #     # tp.system_send_app_sms(msg_info=msg_info)


if __name__ == '__main__':
    # 系统发送短信
    # data = {
    #     "actual_tpl_id": "collection100067",
    #     "msg_list": [{"uid": 3109737, "case_id": 3109737, "queue_code": "NC223"}],
    #     "sell_channel_id": 1
    # }
    # PostLoanPlat(env='stable', use_proxy=True).system_send_sms(msg_info=data)

    # 系统发送APP信息
    # data = {
    #     "actual_tpl_id": "APP202405281041414",
    #     "msg_list": [{"uid": 3109737, "case_id": 3109737, "queue_code": "NC223"}],
    #     "sell_channel_id": 1
    # }
    # PostLoanPlat(env='stable', use_proxy=True).system_send_app_sms(msg_info=data)

    # 系统发送APP信息
    # data = {
    #     "actual_tpl_id": "APP202405281041414",
    #     "sell_channel_id": 1,
    #     "case_id": 3109737,
    # }
    # PostLoanPlat(env='stable', use_proxy=True).person_send_app_sms(msg_info=data)

    # 系统发送APP信息
    # data = {
    #     "uid": 3311476,
    #     "actual_tpl_id": "SMS202209290351170",
    #     "handle_result": 0,
    #     "operation": 30,
    # }
    # PostLoanPlat(env='stable', use_proxy=True).send_complaint_case_sms(msg_info=data)

    # 个人发送短信信息
    # data = {
    #     "uid": 3311476,
    #     "actual_tpl_id": "SMS202502111167766",
    #     "sell_channel_id": 1
    # }
    # PostLoanPlat(env='stable', use_proxy=True).person_send_sms(msg_info=data)

    # 个人发送短信信息
    # data = {
    #     "uid": 3034508,
    #     "actual_tpl_id": "APP2020010810"
    # }
    # PostLoanPlat(env='stable', use_proxy=True).notify_others_app_sms(msg_info=data)

    # plp = PostLoanPlat(env='stable', use_proxy=True)
    # plp.batch_exec_send()
    pass
