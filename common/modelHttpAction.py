# -*- coding: utf-8 -*-
"""
# @File    : modelHttpAction.py
# @Date    : 2026-06-02
# @Author  : jeremyzhai
# @Description  : 纯外部模型调用工具（HTTP Client）
#
# 职责：提供统一的模型 HTTP 调用能力，不涉及任何业务逻辑。
# 使用方式：
#   from common.modelHttpAction import ModelHttpAction
#   client = ModelHttpAction(model_name='deepseek-v4-pro')
#   response = client.chat(prompt="...", max_tokens=2048)
"""

import json
import os
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Union

import requests

Base_Path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(Base_Path)

from utils.handle_log import log


# ============================================================
# 默认配置（可通过环境变量或初始化参数覆盖）
# ============================================================
DEFAULT_AUTH_TOKEN = 'sk-PI-hmdzRFDgccN2sdAhVmQ'
DEFAULT_BASE_URL = 'https://ai-gateway-oa.lexincloud.com/litellm'
DEFAULT_TIMEOUT = 240

# 支持的模型名称映射（可扩展）
SUPPORTED_MODELS = {
    'deepseek-v4-pro': 'deepseek-v4-pro',
    'kimi-k2.6': 'kimi-k2.6',
    # 'claude-opus-4-7': 'claude-opus-4-7',
    # 'claude-opus-4-8': 'claude-opus-4-8',
}


class ModelHttpAction:
    """
    外部模型 HTTP 调用客户端

    提供统一的模型调用接口，支持：
    - 指定不同模型名称（通过 model_name 参数）
    - 自定义请求参数（temperature、max_tokens 等）
    - 结构化 JSON 输出（通过 json_schema）
    """

    def __init__(
        self,
        model_name: str = 'deepseek-v4-pro',
        auth_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """
        初始化模型 HTTP 客户端

        Args:
            model_name: 模型名称，如 'deepseek-v4-pro'、'kimi-k2.6'、'claude-opus-4-7'
            auth_token: 认证 Token，默认从环境变量或默认值读取
            base_url: 模型接口域名
            timeout: 请求超时时间（秒）
        """
        self.model_name = model_name
        self.auth_token = auth_token or os.getenv('MODEL_AUTH_TOKEN', DEFAULT_AUTH_TOKEN)
        self.base_url = (base_url or os.getenv('MODEL_BASE_URL', DEFAULT_BASE_URL)).rstrip('/')
        self.timeout = timeout
        self.url = f'{self.base_url}/v1/messages'
        self.headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json',
        }

    def _check_auth(self) -> None:
        """校验认证信息."""
        if not self.auth_token:
            raise ValueError(
                '请在初始化时传入 auth_token 或设置环境变量 MODEL_AUTH_TOKEN'
            )

    def chat(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        thinking_type: str = 'adaptive',
        json_schema: Optional[Dict] = None,
        desc: str = '【模型调用】',
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ) -> str:
        """
        发送单条用户消息并获取模型回复

        Args:
            prompt: 用户输入的提示词
            system_prompt: 系统提示词（可选）
            max_tokens: 最大生成 token 数
            temperature: 温度参数（0-1）
            thinking_type: 思考模式，默认 'adaptive'
            json_schema: 结构化输出 JSON Schema（可选）
            desc: 日志描述前缀
            max_retries: 最大重试次数（默认3次）
            retry_backoff: 重试退避基数（默认2.0秒）

        Returns:
            模型返回的文本内容

        Example:
            >>> client = ModelHttpAction(model_name='deepseek-v4-pro')
            >>> response = client.chat("请总结这段文本：...")
            >>> print(response)
        """
        self._check_auth()

        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        return self.chat_messages(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_type=thinking_type,
            json_schema=json_schema,
            desc=desc,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
        )

    def chat_messages(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        thinking_type: str = 'adaptive',
        json_schema: Optional[Dict] = None,
        desc: str = '【模型调用】',
        max_retries: int = 3,
        retry_backoff: float = 2.0,
    ) -> str:
        """
        发送多轮对话消息并获取模型回复

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}, ...]
            max_tokens: 最大生成 token 数
            temperature: 温度参数
            thinking_type: 思考模式
            json_schema: 结构化输出 JSON Schema
            desc: 日志描述前缀
            max_retries: 最大重试次数（默认3次）
            retry_backoff: 重试退避基数（默认2.0秒）

        Returns:
            模型返回的文本内容

        Example:
            >>> client = ModelHttpAction(model_name='deepseek-v4-pro')
            >>> messages = [
            ...     {"role": "system", "content": "你是助手"},
            ...     {"role": "user", "content": "你好"},
            ... ]
            >>> response = client.chat_messages(messages)
        """
        self._check_auth()

        data: Dict[str, Any] = {
            'model': self.model_name,
            'max_tokens': max_tokens,
            'thinking': {'type': thinking_type},
            'cache_control': {'type': 'ephemeral'},
            'messages': messages,
        }

        if temperature is not None:
            data['temperature'] = temperature

        if json_schema:
            data['output_config'] = {
                'effort': 'low',
                'format': {
                    'type': 'json_schema',
                    'schema': json_schema,
                }
            }

        log.info(f"{desc}请求入参: model={self.model_name}, messages_count={len(messages)}")

        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    self.url,
                    headers=self.headers,
                    data=json.dumps(data),
                    timeout=self.timeout,
                    verify=True,
                )
                log.info(f"{desc}响应状态: {response.status_code}")

                if response.status_code == 200:
                    resp = json.loads(response.text)
                    text = ''
                    for block in resp.get('content', []):
                        if block.get('type') == 'text':
                            text = block.get('text', '')
                            break

                    if not text:
                        raise RuntimeError(f'{desc}模型返回内容为空，响应: {resp}')

                    return text

                # 非200状态码处理
                if response.status_code in (429, 502, 503, 504):
                    # 需要重试的状态码
                    if attempt < max_retries:
                        wait_time = retry_backoff ** attempt
                        log.warning(
                            f"{desc}请求失败，状态码: {response.status_code}，"
                            f"{wait_time}秒后重试（第{attempt + 1}/{max_retries}次）"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(
                            f'{desc}请求失败，状态码: {response.status_code}，响应: {response.text}')
                else:
                    raise RuntimeError(
                        f'{desc}请求失败，状态码: {response.status_code}，响应: {response.text}')

            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < max_retries:
                    wait_time = retry_backoff ** attempt
                    log.warning(
                        f"{desc}请求异常，{wait_time}秒后重试（第{attempt + 1}/{max_retries}次）: {e}"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    log.error(f'{desc}请求异常: {traceback.format_exc()}')
                    raise RuntimeError(f'{desc}请求异常（已重试{max_retries}次）: {e}') from e

        # 理论上不会到达这里，但保险起见
        if last_exception:
            raise RuntimeError(f'{desc}请求最终失败: {last_exception}')
        raise RuntimeError(f'{desc}请求未知错误')

    def chat_with_json_output(
        self,
        prompt: str,
        *,
        json_schema: Dict,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: Optional[float] = None,
        desc: str = '【模型结构化调用】',
    ) -> Dict:
        """
        调用模型并强制返回结构化 JSON

        Args:
            prompt: 用户提示词
            json_schema: JSON Schema 定义输出结构
            system_prompt: 系统提示词
            max_tokens: 最大 token 数
            temperature: 温度参数
            desc: 日志描述

        Returns:
            解析后的 JSON 字典

        Example:
            >>> schema = {
            ...     "type": "object",
            ...     "properties": {"score": {"type": "number"}},
            ...     "required": ["score"]
            ... }
            >>> result = client.chat_with_json_output("评分", json_schema=schema)
        """
        text = self.chat(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            json_schema=json_schema,
            desc=desc,
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON
            import re
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError(f'无法解析为 JSON: {text}')

    def __repr__(self) -> str:
        return f"ModelHttpAction(model_name='{self.model_name}', base_url='{self.base_url}')"


# ==================== 使用示例 ====================

if __name__ == '__main__':
    # 示例1：基础调用
    client = ModelHttpAction(model_name='deepseek-v4-pro')
    response = client.chat("你好，请介绍一下自己")
    print(response)

    # 示例2：切换不同模型
    # client2 = ModelHttpAction(model_name='kimi-k2.6')
    # response2 = client2.chat("你好")
    # print(response2)

    # 示例3：结构化输出
    # schema = {
    #     "type": "object",
    #     "properties": {"score": {"type": "number"}, "reason": {"type": "string"}},
    #     "required": ["score", "reason"]
    # }
    # result = client.chat_with_json_output("评分", json_schema=schema)
    # print(result)
    pass
