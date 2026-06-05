# -*- coding: utf-8 -*-
"""
# @File    : handle_allure_report.py
# @Date    : 2026-04-13
# @Author  : jeremyzhai
# @Description  : 处理执行完毕的allure报告，将报告链接通过wehook发送到企微群聊
"""

import json
import os
import shutil
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

from utils.handle_log import log


# ============================================================
# Allure 报告内容挂载封装（与断言模式联动）
# ============================================================

def _get_assert_mode_label(assert_mode: str) -> str:
    """根据断言模式返回中文标签"""
    label_map = {
        'intent_similarity': '一致性评分',
        'intent_checklist': '细粒度清单',
        'intent_with_post': '意图+后置操作',
    }
    return label_map.get(assert_mode, assert_mode)


def attach_single_turn_report(report_row: dict, case_info: dict, assert_mode: str = 'intent_similarity') -> None:
    """
    挂载单轮测试 allure 报告内容（根据断言模式联动展示）

    Args:
        report_row: 评估结果行
        case_info: 用例信息
        assert_mode: 当前断言模式
    """
    import allure

    mode_label = _get_assert_mode_label(assert_mode)
    allure.attach(f"断言模式：{mode_label}", '断言模式', allure.attachment_type.TEXT)

    # 根据断言模式挂载不同的断言明细
    if assert_mode == 'intent_checklist' and 'checklist_result' in report_row:
        checklist = report_row.get('checklist_result', {})
        allure.attach(json.dumps(checklist, ensure_ascii=False, indent=2), '检查清单评估结果', allure.attachment_type.JSON)
    elif assert_mode == 'intent_with_post' and 'post_assert' in report_row:
        post = report_row.get('post_assert', {})
        allure.attach(json.dumps(post, ensure_ascii=False, indent=2), '后置操作断言结果', allure.attachment_type.JSON)


def attach_multi_turn_report(round_rows: list, report_row: dict, case_info: dict, assert_mode: str = 'intent_similarity') -> None:
    """
    挂载多轮测试 allure 报告内容（根据断言模式联动展示）

    Args:
        round_rows: 逐轮评估结果
        report_row: 汇总结果行
        case_info: 用例信息
        assert_mode: 当前断言模式
    """
    import allure

    mode_label = _get_assert_mode_label(assert_mode)
    allure.attach(f"断言模式：{mode_label}", '断言模式', allure.attachment_type.TEXT)

    # 挂载逐轮断言明细
    for i, row in enumerate(round_rows):
        if assert_mode == 'intent_checklist' and 'checklist_result' in row:
            checklist = row.get('checklist_result', {})
            allure.attach(json.dumps(checklist, ensure_ascii=False, indent=2), f'第{i+1}轮检查清单结果', allure.attachment_type.JSON)


def attach_model_assert_detail(report_row: dict, assert_mode: str = 'intent_similarity') -> None:
    """
    根据断言模式挂载对应的断言明细

    Args:
        report_row: 评估结果行
        assert_mode: 当前断言模式
    """
    import allure
    # 模式特定的断言明细
    if assert_mode == 'intent_checklist':
        checklist = report_row.get('checklist_result', {})
        items = checklist.get('items', [])

        # 1. 展示所有检查项明细
        detail_lines = [f"{'✅' if item.get('status') == '是' else '❌'} [{item.get('dimension', '')}] {item.get('name', '')}" for item in items]
        allure.attach('\n'.join(detail_lines) if detail_lines else '无检查项', '检查清单明细', allure.attachment_type.TEXT)

        # 2. 单独展示失败的检查项（只展示失败的，方便查看）
        failed_items = [item for item in items if item.get('status') != '是']
        if failed_items:
            failed_lines = []
            for item in failed_items:
                failed_lines.append(f"❌ [{item.get('dimension', '')}] {item.get('name', '')}")
                reason = item.get('reason', '')
                if reason:
                    failed_lines.append(f"   原因：{reason}")
            allure.attach('\n'.join(failed_lines), '检查清单失败项', allure.attachment_type.TEXT)
        else:
            allure.attach('所有检查项均通过 ✅', '检查清单失败项', allure.attachment_type.TEXT)

    elif assert_mode == 'intent_with_post':
        post = report_row.get('post_assert', {})
        detail_lines = [
            f"后置操作通过：{post.get('post_pass', 'N/A')}",
            f"会话类型通过：{post.get('chat_type_pass', 'N/A')}",
            f"ASSET通过：{post.get('asset_pass', 'N/A')}",
        ]
        allure.attach('\n'.join(detail_lines), '后置操作断言明细', allure.attachment_type.TEXT)
    else:
        # 默认模式：一致性评分，展示评分 + 理由
        score = report_row.get('similarity_score', 'N/A')
        reason = report_row.get('similarity_reason', 'N/A')
        threshold = report_row.get('similarity_threshold', 'N/A')
        detail_lines = [
            f"相似度评分：{score}",
            f"评分阈值：{threshold}",
            f"评分理由：{reason}",
        ]
        allure.attach('\n'.join(detail_lines), '相似度评分明细', allure.attachment_type.TEXT)


# ============================================================
# 企微通知相关（原有逻辑保留）
# ============================================================

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
    host = get_local_ip()
    allure_report_url = f'http://{host}:{port}/'
    allure_command = get_allure_command()
    subprocess.Popen(
        ['cmd', '/c', allure_command, 'open', report_dir, '--host', host, '--port', str(port)],
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    )
    return allure_report_url


def build_allure_run_dirs(base_dir='./report'):
    run_id = datetime.now().strftime('%Y%m%d%H%M%S')
    result_dir = os.path.join(base_dir, 'tmp', run_id)
    report_dir = os.path.join(base_dir, 'report', run_id)
    latest_report_dir = get_latest_allure_report_dir(os.path.join(base_dir, 'report'))
    os.makedirs(result_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)
    copy_allure_history(latest_report_dir, result_dir)
    return result_dir, report_dir


def get_latest_allure_report_dir(report_root='./report/report'):
    report_root_path = Path(report_root)
    if not report_root_path.exists():
        return None
    report_dirs = [path for path in report_root_path.iterdir() if path.is_dir() and (path / 'history').exists()]
    if not report_dirs:
        return None
    return str(max(report_dirs, key=lambda path: path.stat().st_mtime))


def copy_allure_history(previous_report_dir, result_dir):
    if not previous_report_dir:
        return
    history_dir = os.path.join(previous_report_dir, 'history')
    if not os.path.exists(history_dir):
        return
    target_history_dir = os.path.join(result_dir, 'history')
    if os.path.exists(target_history_dir):
        shutil.rmtree(target_history_dir)
    shutil.copytree(history_dir, target_history_dir)


def generate_allure_report(result_dir, report_dir):
    allure_command = get_allure_command()
    subprocess.run([allure_command, 'generate', result_dir, '-o', report_dir], check=True)


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
