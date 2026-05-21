# -*- coding: utf-8 -*-
"""
# @File    : handle_allure_report.py
# @Date    : 2026-04-13
# @Author  : jeremyzhai
# @Description  : 处理执行完毕的allure报告，将报告链接通过wehook发送到企微群聊
"""

import json
import shutil
import socket
import subprocess
from datetime import datetime

import requests

from utils.handle_log import log


WEHOOK_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=4f5df1d2-d679-4782-b25f-63e534b4a376'


def get_case_count(summary_path='./report/report/widgets/summary.json'):
    with open(summary_path, encoding='utf-8') as file:
        summary = json.load(file)

    statistic = summary.get('statistic', {})
    num_successd = statistic.get('passed', 0)
    num_failed = statistic.get('failed', 0) + statistic.get('broken', 0)
    return num_successd, num_failed


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        return '127.0.0.1'


def get_available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('', 0))
        return sock.getsockname()[1]


def get_allure_command():
    for command in ('allure', 'allure.bat', 'allure.cmd'):
        command_path = shutil.which(command)
        if command_path:
            return command_path
    raise FileNotFoundError('未找到 allure 可执行文件，请先确认 Allure 已安装并已加入 PATH')


def open_allure_report(report_dir='./report/report'):
    port = get_available_port()
    allure_report_url = f'http://{get_local_ip()}:{port}/'
    allure_command = get_allure_command()
    subprocess.Popen(
        ['cmd', '/c', allure_command, 'open', report_dir, '--host', '0.0.0.0', '--port', str(port)],
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    )
    return allure_report_url


def report_summary(num_successd, num_failed, allure_report_url, env=None, group=None, wehook_url=WEHOOK_URL, extra_content='', elapsed_minutes=None):
    execute_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_count = num_successd + num_failed
    pass_rate = f'{num_successd / total_count * 100:.2f}%' if total_count else '0.00%'
    extra_text = f'\n{extra_content}' if extra_content else ''
    elapsed_text = f'执行耗时：{elapsed_minutes:.2f}分钟\n' if elapsed_minutes is not None else ''
    content_text = (
        f"自动化测试执行完成\n"
        f"时间：{execute_date}\n"
        f"{elapsed_text}"
        f"环境：{env} / {group}\n"
        f"总览：通过 {num_successd}，失败 {num_failed}，通过率 {pass_rate}"
        f"{extra_text}\n"
        f"Allure：{allure_report_url}"
    )
    content = {
        "msgtype": "text",
        "text": {
            "content": content_text,
        }
    }
    response = requests.post(wehook_url, json=content, timeout=10)
    response.raise_for_status()
    result = response.json()
    if result.get('errcode') != 0:
        log.error(f"企微通知发送失败：{result}")
        return False
    log.info("企微通知发送成功")
    return True
