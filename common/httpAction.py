# -*- coding: utf-8 -*-
"""
# @File    : httpAction.py
# @Date    : 2024-11-04
# @Author  : jeremyzhai
"""

import requests
import json
import traceback
import urllib3
from utils.handle_log import log
from jsonpath import jsonpath

# from assert_code.assert_decorators import retry


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HttpAction:
    def __init__(self, cookie):
        """
        初始化http请求类，更新cookie(不同url对应的cookie不一样)
        :param cookie:
        """
        self.headers = {
            # 'Host': 'stable-bianque.lexinfintech.com',
            'Connection': 'keep-alive',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/x-www-form-urlencoded',
            # 'Referer': 'https://stable-bianque.lexinfintech.com/?ticket=5a53ee1f647078334335b37f76eadf11',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cookie': cookie
        }

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
        # url = 'https://stable-bianque.lexinfintech.com/serviceEmulator/request'
        # 1, 组装http请求的req
        # data = json.dumps(data)
        req = {
            # 'headers': self.headers,
            'req_type': req_type,
            'url': url,
            'data': data
        }
        log.info(f"【{desc}】请求的入参为:{req}")

        # 2, 发送http请求
        try:
            if req_type == 'post':
                response = requests.post(url, headers=self.headers, data=data, verify=True)

            elif req_type == 'get':
                response = requests.get(url, headers=self.headers, params=data, verify=True)

            else:
                raise Exception(f'传入的req_type:{req_type}非法， 非GET或POST！！！')

            if print_res is True:
                log.info(f"【{desc}】响应结果为：{response.status_code}, 出参为: {response.text}")
            else:
                log.info(f"【{desc}】响应结果为：{response.status_code}")

            return json.loads(response.text)
        except Exception as e:
            log.exception(f'发生的错误为：{traceback.format_exc()}')
            raise e


class BianquePlat(HttpAction):
    # 类变量：记录已切换过的环境，避免重复切换
    _switched_envs = set()

    def __init__(self, env='stable'):
        self.env = env
        super().__init__(self._set_cookie())
        # 如果默认环境是预发布及以上，需要切换一次环境
        # 只在该环境第一次初始化时切换，避免重复调用
        if env in ('pre', 'gray', 'pro','prod') and env not in BianquePlat._switched_envs:
            self._switch_env_to(env=env)
            BianquePlat._switched_envs.add(env)

    def _set_cookie(self):
        if self.env == 'stable':
            cookie = 'ltrace_sessionId=BE8E349D3A677BBE43119AD45E2EB885; JSESSIONID=AF578A97F3A93219628E25A795BB1D91'
        elif self.env == 'yn_pro':
            cookie = 'ltrace_sessionId=F87B431FE89B9658D562F87EAE12CA00; JSESSIONID=99F0F48661FF3AB6DEB373E93939646B'
        elif self.env == 'mxg_pro':
            cookie = 'ltrace_sessionId=A2BE9EB5D23BEBFAB8AAC3D20CBBD03A; JSESSIONID=08823612061887E573FE7D1064D74B74'
        else:
            # pre&gray&prod，共用同一个cookie
            cookie = 'ltrace_sessionId=67D7F02039103EC286D997123767EC03; JSESSIONID=EEDB554391358C2017B7F4C113807D18'
        return cookie

    def _switch_env_to(self, env):
        """
        切换扁鹊环境至指定环境
        :return:
        """
        req_type = 'post'
        url = 'https://bianque.lexinfintech.com/governance/environment/sgcSwitch/'
        data = {
            'type': env,
        }
        resp = self.send_req(url=url, data=data, req_type=req_type, desc=f'【切换扁鹊环境至 {env}】', print_res=True)
        if int(resp.get('status'))==0:
            log.info(f"切换环境至{env}成功，出参：{resp}")
        else:
            raise Exception("环境切换失败，请检查当前扁鹊环境配置是否符合预期！！！")

    def get_interface_info(self, interface: str, group: str = 'stable') -> dict:
        """
        获取接口信息，包含ip和端口等
        :param group: str
        :param interface: str, 接口名
        :return:
        """
        req_type = 'get'
        if self.env == 'stable':
            url = 'https://stable-bianque.lexinfintech.com/governance/services/list'
        elif self.env == 'yn_pro':
            url = 'https://bianque.oa.kredito.id/governance/services/list'
            group = 'default'
        elif self.env == 'mxg_pro':
            url = 'https://bianque.oa.wowcredito.com/governance/services/list'
            group = 'default'
        else:
            url = 'https://bianque.lexinfintech.com/governance/services/list'
            group = 'default'

        data = {
            'name': interface,
            'ip': '',
            'port': '',
            'appName': '',
            'version': '',
            'group': '',
            'catogory': 'provider',
            'pageIndex': 1,
            'pageSize': 10
        }
        resp = self.send_req(url=url, data=data, req_type=req_type, desc='接口信息查询', print_res=True)

        res_info_list = resp['data'].get('list', [])
        # 遍历查找指定group对应的ip，区分stable和非stable环境
        res_info = dict()
        for i in range(len(res_info_list)):
            # stable 环境
            if group == 'stable' or group.startswith("project_"):
                if res_info_list[i]['group'] == group and res_info_list[i]['serviceName'] == interface:
                    res_info = res_info_list[i]
                    break
            else:
                # pre,gray,pro环境
                if res_info_list[i]['group'] in ['default', '*'] and res_info_list[i]['serviceName'] == interface:
                    res_info = res_info_list[i]
                    break

        if not res_info:
            log.error(f'查询结果异常，{res_info}')
            raise

        else:
            data = {
                "service": interface,
                "group": res_info['group'],
                "ip": str(res_info['ip']).split(',')[0].split(':')[0],
                "port": str(res_info['ip']).split(',')[0].split(':')[1],
                "version": res_info['version'],
                "application": res_info['application']
            }
            log.info(
                f"【接口详细信息】：环境：{self.env}，group:{data['group']}, 接口名：{data.get('service')}, ip：{data['ip']}, "
                f"端口号：{data['port']}，版本号：{data['version']},工程名:{data['application']}")

            return data

    def exec_rpc_req(self, interface_info: dict) -> dict:
        """
        执行rpc请求
        :param interface_info: dict
        interface_info = {
            "env": '', #环境变量，默认stable
            "service": '接口名',
            "group": '', # 获取group信息，默认stable
            "method": '方法名',
            "params": dict, #'接口入参'
        }
        :return:
        """
        # 1, 接口名和group获取ip和端口信息
        group = 'default'
        if self.env == 'stable':
            group = interface_info.get('group', 'stable')
        res_info = self.get_interface_info(interface=interface_info['service'], group=group)

        # 2, 组装参数
        data = {
            'env': interface_info.get('env', 'stable'),
            'service': interface_info.get('service'),
            'ip': res_info.get('ip'),
            'port': res_info.get('port'),
            'group': res_info.get('group'),
            'version': res_info.get('version'),
            'method': interface_info.get('method'),
            'params': f'{interface_info.get("params")}',
            'comment': interface_info.get('comment', ''),
            'stringFlag': 'false'
        }

        # 3, 执行请求
        req_type = 'post'
        if self.env == 'stable':
            url = 'https://stable-bianque.lexinfintech.com/serviceEmulator/request'
        elif self.env == 'yn_pro':
            url = 'https://bianque.oa.kredito.id/serviceEmulator/request'  # 印尼
        elif self.env == 'mxg_pro':
            url = 'https://bianque.oa.wowcredito.com/serviceEmulator/request'  # 墨西哥
        else:
            url = 'https://bianque.lexinfintech.com/serviceEmulator/request'

        desc = interface_info.get('comment', '接口执行')
        print_res = interface_info.get('print_res', True)
        resp = self.send_req(url=url, data=data, req_type=req_type, desc=desc, print_res=print_res)
        # log.info(resp)

        # 提取请求结果
        trace_id = resp.get('message', '')
        # result = resp['data']['result']
        try:
            result = resp['data']['result']
        except KeyError as e:
            # 部分接口返回值无 'result'
            result = resp['data']

        # 是否打印接口出参
        # print_res = interface_info.get('print_res', True)
        if print_res is True:
            log.info(f"{desc}接口返回traceId: {trace_id}, 结果为:{result}")
        else:
            log.info(f"{desc}接口返回traceId: {trace_id}")

        # 接口返回值类型判断，确保返回的格式为dict
        if isinstance(result, list):
            if result:
                # 判断是否非空，空则不直接取内容
                return result[0]

        return result


class LxcloudPlat(HttpAction):
    def __init__(self, env='pro'):
        self.env = env
        super().__init__(self._set_cookie())

        addition_headers = {
            "Authorization": "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJqZXJlbXl6aGFpIiwic2VjcmV0IjoiIyQ1MSFAJCFAIyExMTIiLCJleHAiOjE3NDg0MzQ2Nzl9.JlZgPL9onKZrhj7DUiysfWnT-_duFcaBZp0AWT-7_8Q",
            "mid": "36623",
            "Host": "lxcloud.oa.fenqile.com",
            "Origin": "https://lxcloud.oa.fenqile.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://lxcloud.oa.fenqile.com/?ticket=6641afe4b253adc2878b80f99fe7aa1e",
            "sec-ch-ua-platform": "Windows",
            "sec-ch-ua": 'Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24',
            "sec-ch-ua-mobile": "?0",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        self.headers.update(addition_headers)

    def _set_cookie(self):
        # pre&gray&prod，共用同一个cookie
        cookie = 'client_type=h5; fs_tag=7FA2565E2CBE36DB2DF0974F273F65AB; isc=LINK_BUYCART.MES202003270237290; _ISC={"key":"_ISC","value":"99VIP_DDXQY_TITLE","time_stamp":1656322248541}; choose_product_id=1; _CSC={"key":"_CSC","value":"CASH.HOME.00000001","expire":300,"priority":0,"time_stamp":1662633884779}; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2210000001259%22%2C%22%24device_id%22%3A%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%2C%22props%22%3A%7B%7D%2C%22first_id%22%3A%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%7D; sensorsdata2015session=%7B%7D; channel_extend_info={"entry":"","channel":"","csc":"","min":"jeremyzha*","mid":"36623","retcode":30181032,"fs_tag":"7FA2565E2CBE36DB2DF0974F273F65AB"}; cash_up_id=COM.guding_XQY_banner.LHJQ.JDDHBXQYXE; Hm_lvt_3592cc1c1f867054320b2773e17711c4=1718336891; Hm_lpvt_3592cc1c1f867054320b2773e17711c4=1718336908; x-s3-sid=TS122bM7n10ubtacro8; mid=36623; session=ca2fd057315b40d59741ddd7976fe8a0; x-s3-sid=TS122bM7n10ubtacro8; oa_session=mnrulla94guhtbdj3fbvc3vet3; uid=36623; min=jeremyzhai; fp=1555694878b65a7fa2bbe8f381a7b9c1; Hm_lvt_6617828cdccae4d04f1557b9a67df803=1743580695; Hm_lpvt_6617828cdccae4d04f1557b9a67df803=1743580695; HMACCOUNT=EFCFCFAB7570F11A; Hm_cv_6617828cdccae4d04f1557b9a67df803=1*uid*36623; www_token_id=w%2FA46IagnWLP%2F%2BgrGYE4f4LjJBHedgUZw5bzSl475qHAAsVZCNkzzuu7vUZjraP5w8qLAtQN1vY7xbKX29Qdeg%3D%3D; _SUTC=2103cbf2a4631eecb475a278bd0dc4eba0636b1c; oa_token_id=yu%2B47oALmT4Y2rxsua0eVoe9IWwy%2FUaxuaHoL8ci3JgTrTVAtSAU30Stqh1hSJ7F5CkCRiaoBYtLsu776uE0Rg%3D%3D; Authorization=Bearer%20eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJqZXJlbXl6aGFpIiwiY3JlYXRlZCI6MTc0ODI0MjA0OTQ2MiwiZXhwIjoxNzc5Nzc4MDQ5fQ.Z3KNsUKtq8eJQ9WT6HeS7y2WlyO4NhM_uOJDlV9hu4ldlfJAEE6YxqcvY98ZaeVyUoCWWIZ9zjAPVdL2Kmj3sA'

        return cookie

    def exec_db_req(self, db_info: dict):
        """
        执行rpc请求
        :param db_info: dict
        db_info = {
            "db_type":"QuotalogDB",
            "sql":"select * from quota_compare_2025_db.t_interface_compare_water_0120 \nwhere 1 and Fcompare_result='0' order by fmodify_time DESC limit 10",
            "desc": "sql描述"，非必传
        }
        :return:
        """
        # 1, 组装参数
        data = {
            'db_type': db_info.get('db_type'),
            'sql': db_info.get('sql'),
            "user_name": "jeremyzhai",
            "query_type": "single",
            "query_role": "masterbackup",
            "start_set": "",
            "end_set": ""
        }

        # 3, 执行请求
        req_type = 'post'
        if self.env == 'stable':
            url = 'https://stable-lxcloud.oa.fenqile.com/#/details_mysql/query_mysql'
        else:
            url = 'https://lxcloud.oa.fenqile.com/v1/mysql/sql-query/exec-query/'

        desc = db_info.get('desc', '')
        print_res = db_info.get('print_res', False)
        resp = self.send_req(url=url, data=data, req_type=req_type, desc=desc, print_res=print_res)
        # log.info(resp)

        # 提取请求结果
        if resp['code'] == 200:  # 请求成功
            # 提取列名
            res_col = resp['data']['columns']
            target_column = []
            for col in res_col:
                target_column.append(col['field'])
            # print(type(target_column),target_column)

            # 提取行数据，转换为tuple
            res_rows = resp['data']['data']
            row_list = []
            for row in res_rows:
                row_val = []
                for col_name in target_column:
                    row_val.append(row[col_name])
                row_list.append(row_val)
            # 将二维数组转换成元组
            row_tuple = tuple(tuple(i) for i in row_list)
            # print(type(row_tuple), len(row_tuple), row_tuple)

            # 美化打印
            # from common.dbAction import DbAction
            # DbAction.print_pretty_table(results=row_tuple, target_column=target_column)

            return row_tuple, target_column

        else:
            log.error("【sql查询】 http请求失败！！！")


if __name__ == '__main__':
    BianquePlat(env='pre').get_interface_info(
        interface='com.fenqile.rc_comm.hawk.decision.dispatcher.service.PackageDecisionService', group='default')


    # db_info = {
    #     "db_type": "CreditlimitDB",
    #     "sql": "select * from user_quota_db.t_credit_limit where fuid = '4085145'",
    #     "desc": "sql查询"
    # }
    # LxcloudPlat(env='pro').exec_db_req(db_info=db_info)
