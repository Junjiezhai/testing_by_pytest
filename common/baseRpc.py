# -*- coding: utf-8 -*-
"""
# @File    : baseRpc.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""

import json
import time
import socket
import traceback
import typing
import random
import os
from kazoo.client import KazooClient
from urllib.parse import unquote
import re

import sys

sys.path.append('../utils')  # 添加utils文件夹到模块搜索路径

from utils.handle_log import log


def gen_trace_id() -> str:
    """
    生成用户trace_id
    """
    timestamp = int(time.time() * 1000)
    random_int = random.randrange(1000, 10000)
    return '{}{}{}{}'.format(get_ip_hex(), timestamp, random_int, get_pid_hex()).upper()


def get_ip_hex():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        ip_addr = ip.split('.')

        if len(ip_addr) == 4:
            ip_hex = ''
            for addr in ip_addr:
                addr_hex = hex(int(addr)).replace('0x', '')
                if len(addr_hex) == 1:
                    addr_hex = '0' + addr_hex
                ip_hex += addr_hex
        else:
            ip_hex = '00000000'
        return ip_hex
    except Exception:
        return '00000000'
    finally:
        s.close()


def get_pid_hex():
    pid = os.getpid()
    pid_str = str(pid)
    pid_hex = ''
    if len(pid_str) < 4:
        cover = 4 - len(pid_str)
        for i in range(0, cover):
            pid_hex += '0'
    pid_hex += hex(int(pid)).replace('0x', '')
    return pid_hex


class RPC(object):
    """
    RPC请求类
    """

    def __init__(
            self,
            env: str = 'stable',
            timeout: int = 20
    ) -> typing.NoReturn:
        """
          建立TCP连接
           :param env: 环境标识，默认stable，str型入参
        """
        self.timeout = timeout
        self.zk_host = {
            "yn_stable": "10.9.108.197:2183",
            "mxg_stable": "10.9.107.194:2183",
            "stable": "10.9.22.26:2182,10.9.22.30:2182",
            "pre": "10.10.16.122:2185, 10.11.16.87:2184",
            "gray": "10.10.16.122:2184, 10.11.16.87:2185",
            "pro": "10.10.16.125:2186, 10.11.16.87:2181",
            "yn_pro": "10.249.2.12:2183, 10.249.2.47:2183",
            "mxg_pro": "10.248.2.93:2183, 10.248.2.3:2183"
        }
        # self.zk_host = {"stable": "10.9.108.197:2183"}
        self.env = env
        self.sock = socket.socket()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _get_addr_by_interface(self, service_name, group='stable'):
        zk_host = self.zk_host.get(self.env)
        host_list = zk_host.split(',')
        flag, interface_ver, port_info = False, 'default', 'default'

        # 兼容非stable环境group默认为default
        # group = 'stable' if self.env == 'stable' else 'default'

        for host in host_list:
            try:
                zk = KazooClient(hosts=host)
                zk.start()
                interface_list = zk.get_children("/fsof/%s/providers" % service_name)
                port_list = []
                item_list = [unquote(item) for item in interface_list if
                             f"group={group}" in unquote(item) or f"group=*" in unquote(item)]
                # print(len(item_list), item_list)
                # log.info(item_list)
                interface_ver = '2.0.0'
                for interface in item_list:
                    self.server_name = re.search(r'application=([^&]+)', interface).group(1)
                    pattern = r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+"
                    match = re.search(pattern, interface)
                    if match:
                        ip_port = match.group()
                        port_list.append(ip_port)
                        for s in interface.split('&')[::-1]:
                            if 'version=' in s:
                                interface_ver = s.split('=')[-1]  # 接口版本号
                                break
                zk.stop()
                zk.close()
                if len(port_list) > 0:
                    return True, port_list[0], interface_ver
            except Exception as e:
                log.warning(
                    f"获取服务【{service_name}】信息异常，当前环境env:{self.env}, group:{group}, zk_host:{host}, host_list:{host_list}!")
                log.error(traceback.format_exc())
                continue

        return flag, port_info, interface_ver

        # raise Exception(f"{self.env}环境解析{service_name}接口地址失败")

    def _prepare_request(self, interface: str, group: str = 'stable'):
        """
        初始化参数校验
        :param interface: 接口名，str型入参
        """
        if not isinstance(interface, str):
            raise Exception(f"传入的接口名{interface}非字符串类型")

        res, ip_port, self.interface_version = self._get_addr_by_interface(service_name=interface, group=group)

        # 日志提示取到项目环境机器ip
        if group is not 'stable':
            log.info(f"====== 当前group为：{group}，接口名：{interface}，ip和端口为：{ip_port} =====")

        # 当指定服务在当前group不存在机器时，取stable的机器ip
        if (res is False) and (group is not 'stable'):
            res, ip_port, self.interface_version = self._get_addr_by_interface(service_name=interface, group='stable')
            log.warning(f"====== 未获取到指定group：{group}的接口信息，取stable接口信息，接口名：{interface}，ip和端口为：{ip_port} =====")

        if res is False:
            raise Exception(f'获取group({group}), 接口名({interface})失败')

        self.ip = str(ip_port.split(':')[0])
        self.port = int(ip_port.split(':')[1])

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.ip, self.port))

    def close(self):
        """
        关闭socket连接
        """
        self.sock.close()

    def request(
            self,
            data: dict,
            pretty: str = 'dict',
            indent: int = 2
    ) -> typing.Union[dict, str]:
        """
        发送TCP请求
        If ``pretty`` is dict, then return response message as a python dict
        If ``pretty`` is json, then return response message as a json string which indent=indent,default is 2
        :return response msg
        """
        assert isinstance(data, dict), 'request data must be dict type'
        # gen trace_id
        trace_id = gen_trace_id()
        data['tracecontext'] = {'trace_id': trace_id}

        # 建立TCP 连接 , 传入接口名，获取ip和port
        self._prepare_request(data.get("service"), data.get('group', 'stable'))

        # group处理
        data['environment'] = data.get("group")
        # 设置接口版本号，未传则以查询到的为准
        data['version'] = data.get('version', self.interface_version)
        log.info(
            f"接口名：{data.get('service')}, 方法名：{data.get('method')}，ip： {self.ip}, 端口号：{self.port}，版本号：{data['version']}, group:{data.get('group', 'stable')}")

        data = json.dumps(data)

        header = bytes()
        # magic
        header += bytes([0xda, 0xbb])
        # cmd
        header += bytes([0x01, 0x00])
        # data length
        header += len(data).to_bytes(4, byteorder='big')
        # crc
        header += bytes([0x00 for _ in range(0, 4)])
        # frame
        header += bytes([0x01, 0x01, 0x00, 0x00])
        # sn
        header += int(time.time()).to_bytes(4, byteorder='big')
        # serializer
        header += bytes([0x00])
        # reserve
        header += bytes([0x00 for _ in range(0, 11)])
        # msg
        msg = header + data.encode('utf-8')

        self.sock.sendall(msg)

        return self._response(pretty=pretty, indent=indent, trace_id=trace_id)

    def _response(self, pretty: str, indent: int, trace_id: str) -> typing.Union[dict, str]:
        """
        读取响应报文
        """
        assert pretty in ('dict', 'json'), 'pretty args must be (dict,json)'
        assert isinstance(indent, int), 'indent args must be int type'
        # 读取协议头
        header: bytes = self.sock.recv(32)
        len_bytes = header[4:8]
        data_len = int.from_bytes(len_bytes, byteorder="big")

        # 读取协议体
        data = bytes()
        read_len = 0

        while read_len < data_len:
            one_read_data = self.sock.recv(1024)
            data += one_read_data
            read_len += len(one_read_data)

        assert data_len == read_len, 'CRC Check failed'

        try:
            service_resp = json.loads(data.decode())
        except:
            service_resp = eval(data.decode().replace('null', 'None').replace('true', 'True').replace('false', 'False'))

        resp = {
            "status": 0,
            "trace_id": trace_id,
            "data": service_resp
        }

        if pretty == 'json':
            resp = json.dumps(resp, ensure_ascii=False, indent=indent)

        return resp

    def __str__(self):
        return '<RPC: IP:%s,PORT:%s, VERSION:%s>' % (self.ip, self.port, self.interface_version)

    __repr__ = __str__


if __name__ == '__main__':
    # rpc = RPC("stable")
    # data = {
    #     "service": "com.fenqile.rc.core.process.engine.route.service.ProcessEngineRouteService",
    #     "method": "route",
    #     "group": "default",
    #     # "version": "2.0.0",#service_meta["version"],
    #     "params": [{
    #         "bizDept": 10,
    #         "bizScene": 20,
    #         "process": 1
    #     }]
    # }
    # res = rpc.request(data)
    # print(type(res), res)

    rpc = RPC("mxg_stable")
    # data = {
    #     "service": "com.fenqile.process.engine.console.service.process.ProcessQueryService",
    #     "method": "queryOnlineEdition",
    #     "group": "project_109110229",
    #     # "version": "2.0.0",#service_meta["version"],
    #     "params": ["SP00000309"]
    # }
    data = {
        "service": "com.fenqile.anti_fraud.field_computing.service.FieldBatchComputeService",
        "method": "compute",
        "group": "project_10963208",
        "params": [
            {
                "invoker": "5",
                "uid": 3201279,
                "orderId": "O20250512029866600472",
                "macCode": "R2",
                "creditId": "161C419883E2F4F473D3305C98E14474",
                "fieldNameList": [
                    "mex_junhong_script_feature_test_integer"
                ]
            }
        ]
    }
    res = rpc.request(data)
    print(type(res), res)
