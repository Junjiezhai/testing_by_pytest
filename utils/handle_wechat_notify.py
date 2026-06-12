# -*- coding: utf-8 -*-
"""
# @File    : handle_wechat_notify.py
# @Date    : 2026-06-02
# @Author  : jeremyzhai
# @Description  : 企业微信机器人通知工具，支持文本、图片、markdown、图文等多种消息格式
"""

import base64
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import requests

from utils.handle_log import log


# ============================================================
# 默认配置
# ============================================================
DEFAULT_WEBHOOK_URL = 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=4f5df1d2-d679-4782-b25f-63e534b4a376'

# 限制：图片大小不超过 2MB
MAX_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB


# ============================================================
# 核心发送函数
# ============================================================

def _send(webhook_url: str, payload: dict) -> bool:
    """发送消息到企微 webhook（内部通用函数）."""
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        if result.get('errcode') != 0:
            log.error(f"企微通知发送失败: {result}")
            return False
        log.info("企微通知发送成功")
        return True
    except requests.RequestException as e:
        log.error(f"企微通知发送异常: {e}")
        return False


# ============================================================
# 1. 文本消息
# ============================================================

def send_text(
    content: str,
    webhook_url: str = DEFAULT_WEBHOOK_URL,
    mentioned_list: Optional[List[str]] = None,
    mentioned_mobile_list: Optional[List[str]] = None,
) -> bool:
    """
    发送文本消息

    Args:
        content: 文本内容（最长2048字节）
        webhook_url: 企微 webhook 地址
        mentioned_list: @userid列表，如 ["userid1", "userid2"]，@all 表示所有人
        mentioned_mobile_list: @手机号列表

    Returns:
        发送是否成功

    Example:
        >>> send_text("测试执行完成，通过率100%")
        >>> send_text("测试完成", mentioned_list=["@all"])
    """
    payload = {
        "msgtype": "text",
        "text": {"content": content}
    }
    if mentioned_list:
        payload["text"]["mentioned_list"] = mentioned_list
    if mentioned_mobile_list:
        payload["text"]["mentioned_mobile_list"] = mentioned_mobile_list
    return _send(webhook_url, payload)


# ============================================================
# 2. Markdown 消息（支持图片链接，图片需公网可访问）
# ============================================================

def send_markdown(
    content: str,
    webhook_url: str = DEFAULT_WEBHOOK_URL,
) -> bool:
    """
    发送 Markdown 格式消息

    Args:
        content: Markdown 内容（最长4096字节）
        webhook_url: 企微 webhook 地址

    Returns:
        发送是否成功

    Example:
        >>> send_markdown("## 测试报告\\n- 通过率：100%\\n- 耗时：5分钟")
        >>> send_markdown("![雷达图](https://example.com/radar.png)")
    """
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content}
    }
    return _send(webhook_url, payload)


# ============================================================
# 3. 图片消息（本地图片转为 base64 发送）
# ============================================================

def send_image(
    image_path: Union[str, Path],
    webhook_url: str = DEFAULT_WEBHOOK_URL,
) -> bool:
    """
    发送图片消息（本地图片文件）

    注意：图片大小不能超过 2MB

    Args:
        image_path: 本地图片路径（如 radar.png）
        webhook_url: 企微 webhook 地址

    Returns:
        发送是否成功

    Example:
        >>> send_image("report/radar.png")
        >>> send_image("report/confusion_matrix.png")
    """
    image_path = Path(image_path)

    if not image_path.exists():
        log.error(f"图片文件不存在: {image_path}")
        return False

    if image_path.stat().st_size > MAX_IMAGE_SIZE:
        log.error(f"图片大小超过限制（最大2MB）: {image_path}")
        return False

    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # 计算 base64 和 md5
        base64_data = base64.b64encode(image_data).decode('utf-8')
        md5_value = hashlib.md5(image_data).hexdigest()

        payload = {
            "msgtype": "image",
            "image": {
                "base64": base64_data,
                "md5": md5_value,
            }
        }
        return _send(webhook_url, payload)
    except Exception as e:
        log.error(f"图片发送失败: {e}")
        return False


# ============================================================
# 4. 图文消息（news，支持图片链接）
# ============================================================

def send_news(
    articles: List[Dict],
    webhook_url: str = DEFAULT_WEBHOOK_URL,
) -> bool:
    """
    发送图文消息

    Args:
        articles: 图文列表，每项包含 title/description/url/picurl
        webhook_url: 企微 webhook 地址

    Returns:
        发送是否成功

    Example:
        >>> send_news([{
        ...     "title": "测试报告",
        ...     "description": "通过率 100%",
        ...     "url": "http://allure-report.com",
        ...     "picurl": "http://example.com/cover.png",
        ... }])
    """
    payload = {
        "msgtype": "news",
        "news": {
            "articles": articles[:8]  # 最多8条
        }
    }
    return _send(webhook_url, payload)


# ============================================================
# 5. 文件消息（需要先上传获取 media_id）
# ============================================================

def upload_file(file_path: Union[str, Path], webhook_url: str = DEFAULT_WEBHOOK_URL) -> Optional[str]:
    """
    上传文件到企微获取 media_id（用于发送文件消息）

    Args:
        file_path: 本地文件路径
        webhook_url: 企微 webhook 地址

    Returns:
        media_id 字符串，失败返回 None

    Example:
        >>> media_id = upload_file("report/test_result.xlsx")
        >>> if media_id:
        ...     send_file(media_id)
    """
    file_path = Path(file_path)
    if not file_path.exists():
        log.error(f"文件不存在: {file_path}")
        return None

    try:
        with open(file_path, 'rb') as f:
            files = {'media': (file_path.name, f, 'application/octet-stream')}
            # 提取 key 参数
            key = webhook_url.split('key=')[-1].split('&')[0] if 'key=' in webhook_url else ''
            upload_url = f'https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={key}&type=file'
            response = requests.post(upload_url, files=files, timeout=30)
            response.raise_for_status()
            result = response.json()
            if result.get('errcode') == 0:
                media_id = result.get('media_id')
                log.info(f"文件上传成功，media_id: {media_id}")
                return media_id
            else:
                log.error(f"文件上传失败: {result}")
                return None
    except requests.RequestException as e:
        log.error(f"文件上传异常: {e}")
        return None


def send_file(
    media_id: str,
    webhook_url: str = DEFAULT_WEBHOOK_URL,
) -> bool:
    """
    发送文件消息（需要先上传获取 media_id）

    Args:
        media_id: 上传文件后获取的 media_id
        webhook_url: 企微 webhook 地址

    Returns:
        发送是否成功

    Example:
        >>> media_id = upload_file("report/test_result.xlsx")
        >>> send_file(media_id)
    """
    payload = {
        "msgtype": "file",
        "file": {"media_id": media_id}
    }
    return _send(webhook_url, payload)


# ============================================================
# 6. 组合消息：文本 + 图片（推荐用于测试报告）
# ============================================================

def send_report_with_image(
    title: str,
    content: str,
    image_path: Union[str, Path],
    webhook_url: str = DEFAULT_WEBHOOK_URL,
    mentioned_list: Optional[List[str]] = None,
) -> bool:
    """
    发送测试报告：先发送文本摘要，再发送图片

    Args:
        title: 报告标题
        content: 报告内容文本
        image_path: 图片路径（雷达图、混淆矩阵等）
        webhook_url: 企微 webhook 地址
        mentioned_list: @用户列表

    Returns:
        发送是否成功

    Example:
        >>> send_report_with_image(
        ...     "模型意图识别测试报告",
        ...     "通过率：95%\\n执行耗时：10分钟",
        ...     "report/radar.png",
        ... )
    """
    # 先发送文本
    full_content = f"{title}\n{'=' * 40}\n{content}"
    success = send_text(full_content, webhook_url, mentioned_list)
    if not success:
        return False

    # 再发送图片
    if image_path and Path(image_path).exists():
        image_success = send_image(image_path, webhook_url)
        return image_success

    return success


# ============================================================
# 7. 封装：Allure 报告 + 图片通知（替换原有 report_summary）
# ============================================================

def report_summary(
    num_successd: int,
    num_failed: int,
    allure_report_url: str,
    env: Optional[str] = None,
    group: Optional[str] = None,
    webhook_url: str = DEFAULT_WEBHOOK_URL,
    extra_content: str = '',
    elapsed_minutes: Optional[float] = None,
    image_path: Optional[Union[str, Path]] = None,
) -> bool:
    """
    发送 Allure 测试报告摘要（支持附带图片）

    Args:
        num_successd: 通过用例数
        num_failed: 失败用例数
        allure_report_url: Allure 报告 URL
        env: 环境名称
        group: 分组名称
        webhook_url: 企微 webhook 地址
        extra_content: 额外内容
        elapsed_minutes: 执行耗时（分钟）
        image_path: 可选，要附带的图片路径（如雷达图、混淆矩阵）

    Returns:
        发送是否成功

    Example:
        >>> report_summary(100, 5, "http://allure-report.com", env="dev", group="model")
        >>> report_summary(100, 5, "http://allure-report.com", image_path="report/radar.png")
    """
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

    # 发送文本
    success = send_text(content_text, webhook_url)
    if not success:
        return False

    # 发送图片（如果有）
    if image_path and Path(image_path).exists():
        image_success = send_image(image_path, webhook_url)
        return success and image_success

    return success


# ============================================================
# 8. 模型意图测试专用通知封装
# ============================================================

def send_start_notice(webhook_url: str = DEFAULT_WEBHOOK_URL) -> bool:
    """
    测试执行前发送企微通知（开始通知）

    Args:
        webhook_url: 企微 webhook 地址

    Returns:
        发送是否成功
    """
    from datetime import datetime
    content_text = (
        "执行自动化测试中，请勿发版，如果必须发版，请通知jeremyzhai !!!@joelwu(吴荣洲) @haganzhou(周汉耿)\n"
        f"操作人：jeremyzhai\n"
        f"操作时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return send_text(content_text, webhook_url)


def send_end_notice(
    env: str,
    group: str,
    assert_mode: str,
    case_type: str,
    num_successd: int,
    num_failed: int,
    allure_report_url: str,
    elapsed_minutes: float = 0.0,
    webhook_url: str = DEFAULT_WEBHOOK_URL,
    type_stats: dict = None,
    response_stats: dict = None,
) -> bool:
    """
    测试执行后发送企微通知（非批量模式，保持原模板）

    Args:
        env: 测试环境
        group: 测试分组
        assert_mode: 断言模式
        case_type: 用例类型
        num_successd: 通过用例数
        num_failed: 失败用例数
        allure_report_url: Allure 报告 URL
        elapsed_minutes: 执行耗时（分钟）
        webhook_url: 企微 webhook 地址
        type_stats: 按类型统计 {'single': {...}, 'multi': {...}}
        response_stats: 响应耗时统计 {'avg': str, 'p90': str, 'p95': str, 'max': str}

    Returns:
        发送是否成功
    """
    execute_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_count = num_successd + num_failed
    pass_rate = f'{num_successd / total_count * 100:.2f}%' if total_count else '0.00%'
    elapsed_text = f'执行耗时：{elapsed_minutes:.2f}分钟\n' if elapsed_minutes is not None else ''

    # 构建按类型统计表格
    type_stats_text = ''
    if type_stats:
        single = type_stats.get('single', {})
        multi = type_stats.get('multi', {})
        type_stats_text = (
            f"\n"
            f"类型 | 通过用例数 | 失败用例数 | 总用例数 | 通过率\n"
            f"单轮 | {single.get('pass', 0)} | {single.get('fail', 0)} | {single.get('total', 0)} | {single.get('rate', '0.00%')}\n"
            f"多轮 | {multi.get('pass', 0)} | {multi.get('fail', 0)} | {multi.get('total', 0)} | {multi.get('rate', '0.00%')}\n"
        )

    # 构建响应耗时统计表格
    response_stats_text = ''
    if response_stats:
        response_stats_text = (
            f"\n"
            f"耗时 | 平均 | P90 | P95 | 最大\n"
            f"响应 | {response_stats.get('avg', 'N/A')} | {response_stats.get('p90', 'N/A')} | {response_stats.get('p95', 'N/A')} | {response_stats.get('max', 'N/A')}\n"
        )

    content_text = (
        f"自动化测试执行完成\n"
        f"时间：{execute_date}\n"
        f"{elapsed_text}"
        f"环境：{env} / {group}\n"
        f"模式：非批量断言\n"
        f"总览：通过 {num_successd}，失败 {num_failed}，通过率 {pass_rate}\n"
        f"{type_stats_text}"
        f"{response_stats_text}"
        f"\n"
        f"断言模式：{assert_mode}\n"
        f"用例类型：{case_type}\n"
        f"Allure：{allure_report_url}"
    )

    payload = {
        "msgtype": "text",
        "text": {
            "content": content_text,
        }
    }
    return _send(webhook_url, payload)


def send_end_notice_batch(
    env: str,
    group: str,
    assert_mode: str,
    case_type: str,
    num_successd: int,
    num_failed: int,
    allure_report_url: str,
    elapsed_minutes: float = 0.0,
    webhook_url: str = DEFAULT_WEBHOOK_URL,
    batch_summary: dict = None,
    response_stats: dict = None,
) -> bool:
    """
    测试执行后发送企微通知（批量断言模式专用模板）

    Args:
        env: 测试环境
        group: 测试分组
        assert_mode: 断言模式
        case_type: 用例类型
        num_successd: pytest 通过用例数
        num_failed: pytest 失败用例数
        allure_report_url: Allure 报告 URL
        elapsed_minutes: 执行耗时（分钟）
        webhook_url: 企微 webhook 地址
        batch_summary: 批量断言结果摘要
            {'total': int, 'pass_count': int, 'failed_count': int, 'pass_rate': str}
        response_stats: 响应耗时统计
            {'avg': str, 'p90': str, 'p95': str, 'max': str}

    Returns:
        发送是否成功
    """
    execute_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    elapsed_text = f'执行耗时：{elapsed_minutes:.2f}分钟\n' if elapsed_minutes is not None else ''

    # 构建批量断言统计文本
    batch_text = ''
    if batch_summary:
        batch_total = batch_summary.get('total', 0)
        batch_pass = batch_summary.get('pass_count', 0)
        batch_fail = batch_summary.get('failed_count', 0)
        batch_rate = batch_summary.get('pass_rate', '0.00%')
        batch_text = (
            f"\n"
            f"【批量断言统计】\n"
            f"总条数：{batch_total}，通过：{batch_pass}，失败：{batch_fail}，通过率：{batch_rate}\n"
        )

    # 构建响应耗时统计文本
    response_stats_text = ''
    if response_stats:
        response_stats_text = (
            f"\n"
            f"耗时 | 平均 | P90 | P95 | 最大\n"
            f"响应 | {response_stats.get('avg', 'N/A')} | {response_stats.get('p90', 'N/A')} | {response_stats.get('p95', 'N/A')} | {response_stats.get('max', 'N/A')}\n"
        )

    content_text = (
        f"自动化测试执行完成\n"
        f"时间：{execute_date}\n"
        f"{elapsed_text}"
        f"环境：{env} / {group}\n"
        f"模式：批量断言\n"
        f"{batch_text}"
        f"{response_stats_text}"
        f"\n"
        f"断言模式：{assert_mode}\n"
        f"用例类型：{case_type}\n"
        f"Allure：{allure_report_url}"
    )

    payload = {
        "msgtype": "text",
        "text": {
            "content": content_text,
        }
    }
    return _send(webhook_url, payload)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例1：发送文本消息
    # send_text("测试执行完成，通过率100%")

    # 示例2：发送 Markdown 消息
    # send_markdown("## 模型测试报告\n- **通过率**：95%\n- **耗时**：10分钟")

    # 示例3：发送本地图片（雷达图、混淆矩阵等）
    # send_image("report/model_radar.png")

    # 示例4：发送图文消息
    # send_news([{
    #     "title": "模型测试报告",
    #     "description": "通过率95%，点击查看详情",
    #     "url": "http://allure-report.com",
    #     "picurl": "http://example.com/cover.png",
    # }])

    # 示例5：文本 + 图片组合
    # send_report_with_image(
    #     "模型意图识别测试报告",
    #     "通过率：95%\n执行耗时：10分钟",
    #     "report/radar.png",
    # )

    # 示例6：带图片的 Allure 报告通知
    # report_summary(
    #     num_successd=95,
    #     num_failed=5,
    #     allure_report_url="http://allure-report.com",
    #     env="dev",
    #     group="model_intent",
    #     image_path="report/radar.png",
    # )
    pass
