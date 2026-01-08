# -*- coding: utf-8 -*-
"""
# @File    : baseRpc.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""

import sys

sys.path.append('../utils')  # 添加utils文件夹到模块搜索路径

from utils.handle_log import log
import traceback, json
from common.baseRpc import RPC
from common.httpAction import BianquePlat


class BaseRpc:
    def __init__(self):
        pass

    @classmethod
    def exec_rpc(cls, interface_info: dict, desc='', print_res=True) -> dict:
        """
        执行rpc接口调用，获取接口返回结果
        :param print_res: bool, 是否打印接口出参
        :param desc:  支持传入接口调用描述
        :param interface_info:
        :return:
        """
        # 组装接口入参
        input_data = {
            "service": interface_info.get('interface'),
            # 获取group信息，默认stable
            "group": interface_info.get('group', 'stable'),
            "method": interface_info.get('method'),
            "tracecontext": {},
            "params": interface_info.get('params')

        }
        # print(json.dumps(input_data, sort_keys=True, indent=4, separators=(',', ': ')))
        # 获取环境信息，默认stable
        cur_env = interface_info.get('env', 'stable')

        try:
            # stable/yn_stable 环境
            if 'stable' in cur_env:
                pyrpc = RPC(cur_env)
                log.info(f"{desc}rpc接口入参：{json.dumps(input_data)}")
                result = pyrpc.request(input_data)
                # result = result.replace('null', 'None').replace('true', 'True').replace('false', 'False')  # 将rpc接口返回的特殊字段进行替换

                # 解析接口返回值
                trace_id = result['trace_id']
                try:
                    res_info = result['data']['result']
                except KeyError as e:
                    # 部分接口返回值无 'result'
                    res_info = result['data']

                # 是否打印接口出参
                if print_res:
                    log.info(f"{desc}接口返回traceId: {trace_id}, 结果为:{res_info}")
                else:
                    log.info(f"{desc}接口返回traceId: {trace_id}")

                # 接口返回值类型判断，确保返回的格式为dict
                if isinstance(res_info, list):
                    if res_info:
                        # 判断是否非空，空则不直接取内容
                        return res_info[0]

            # pro、gray、pre环境，区分印尼和科技
            else:
                input_data["env"] = cur_env
                input_data["comment"] = desc
                input_data["print_res"] = print_res
                # 前端传输对单双引号敏感，底层强转为json才能调用http接口
                input_data["params"] = json.dumps(input_data["params"])

                # 使用http接口请求线上扁鹊
                res_info = BianquePlat(env=cur_env).exec_rpc_req(interface_info=input_data)

            return res_info

        except Exception as error:
            # 日志打印
            log.error(traceback.format_exc())
            raise error


if __name__ == '__main__':
    # 调用示例 1 , 类方法调用
    # data = {
    #     'interface': 'com.fenqile.rc.core.process.engine.route.service.ProcessEngineRouteService',
    #     'method': 'route',
    #     'params': [{
    #         "bizDept": 10,
    #         "bizScene": 20,
    #         "process": 1
    #     }]
    # }
    # res = BaseRpc.exec_rpc(data, desc='流程匹配')

    data = {
        'interface': 'com.fenqile.rc_comm.hawk.decision.water.service.OfflineDecisionWaterService',
        'method': 'queryStrategyNodeTestDecision',
        'env': 'stable',
        'group': 'stable',
        'params': [{
            "orderId": "O20240819540716724473",
            "uid": "3064473",
            "seq": "I2024081920444827914428522604473",
            "nodeId": 101057,
            "needInput": True,
            "needOutput": True,
            "createTime": "2024-08-19 00:00:00"
        }]
    }
    res = BaseRpc.exec_rpc(data, desc='【米霍克决策-仿真】流程决策结果查询')
    print(type(res), res)
