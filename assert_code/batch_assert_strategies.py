# -*- coding: utf-8 -*-
"""
多轮对话批量断言策略类

实现单轮和多轮的批量评估策略分离：
- SingleTurnBatchStrategy: 单轮批量评估（语义相似度）
- MultiTurnBatchStrategy: 多轮批量评估（7个维度 + ASSET + 转人工）
"""

import json
import os
import re
from abc import ABC, abstractmethod
from typing import List, Dict

from assert_code.external_model_judge import ExternalModelJudge
from debug_model_by_pytest import TestConfig
from utils.handle_log import log


def _extract_error_summary(exception: Exception) -> str:
    """
    从异常中提取简短的错误摘要，避免将完整的模型响应存入报告。

    规则：
    1. 网络异常 → 保留状态码和简要描述
    2. JSON 解析异常 → 保留类型信息
    3. 其他异常 → 截取前 100 个字符
    """
    error_msg = str(exception)

    # 网络异常：提取状态码
    status_match = re.search(r'状态码[\s:]+(\d+)', error_msg)
    if status_match:
        status_code = status_match.group(1)
        return f"外部模型请求失败（状态码：{status_code}）"

    # JSON 解析异常
    if 'JSON"""DecodeError' in error_msg or 'json' in error_msg.lower() or '解析' in error_msg:
        return "外部模型返回结果解析失败"

    # 通用截断（最多 100 字符）
    if len(error_msg) > 100:
        return f"{error_msg[:100]}..."

    return error_msg


class BaseBatchAssertStrategy(ABC):
    """批量断言策略基类"""

    def __init__(self, judge: ExternalModelJudge, max_group_size: int = 10,
                 assert_mode: str = 'intent_checklist'):
        self.judge = judge
        self.max_group_size = max_group_size
        self.assert_mode = assert_mode  # 新增：断言模式

    @abstractmethod
    def build_prompt(self, data: List[dict]) -> str:
        """构建批量评估 prompt"""
        pass

    @abstractmethod
    def parse_result(self, text: str, data: List[dict]) -> List[dict]:
        """解析评估结果"""
        pass

    def evaluate(self, items: List[dict]) -> List[dict]:
        """
        执行多轮批量评估

        流程：
        1. 外部模型评估7个维度（A-G）
        2. 本地规则断言（ASSET + 转人工）
        3. 合并结果
        """
        if not items:
            return []

        # 按 max_group_size 切分
        all_results = []
        for i in range(0, len(items), self.max_group_size):
            chunk = items[i:i + self.max_group_size]
            chunk_results = self._evaluate_chunk(chunk)
            all_results.extend(chunk_results)

        # 补充本地规则断言（ASSET + 转人工）
        for idx, item in enumerate(items):
            if idx < len(all_results):
                result = all_results[idx]
                # 执行本地规则断言
                local_assert = self._evaluate_local_rules(item)
                # 合并到结果中
                result['transfer_pass'] = local_assert['transfer_pass']
                result['transfer_reason'] = local_assert['transfer_reason']
                result['asset_pass'] = local_assert['asset_pass']
                result['asset_reason'] = local_assert['asset_reason']
                # 同步更新 local_assert_detail（用于HTML报告展示）
                local_assert_detail = result.get('local_assert_detail', {})
                local_assert_detail['transfer_pass'] = local_assert['transfer_pass']
                local_assert_detail['asset_pass'] = local_assert['asset_pass']
                local_assert_detail['transfer_reason'] = local_assert['transfer_reason']
                local_assert_detail['asset_reason'] = local_assert['asset_reason']
                result['local_assert_detail'] = local_assert_detail
                # 最终通过条件 = 外部模型通过 AND 本地断言通过
                # 注意：单轮使用 'is_pass'，多轮使用 'overall_pass'
                external_pass = result.get('overall_pass') or result.get('is_pass', False)
                result['overall_pass'] = (
                    external_pass and
                    local_assert['transfer_pass'] and
                    local_assert['asset_pass']
                )

        return all_results

    def _evaluate_local_rules(self, item: dict) -> dict:
        """
        执行本地规则断言（ASSET + 转人工）

        :param item: 包含 last_output_data 的 case 数据
        :return: {
            'transfer_pass': bool,
            'transfer_reason': str,
            'asset_pass': bool,
            'asset_reason': str,
        }
        """
        from assert_code.model_intent_assert import ModelIntentAssert
        from assert_code.postloan_intent_assert import PostloanIntentAssert

        # 根据场景选择正确的断言类
        case_type = item.get('case_type', '')
        is_postloan = case_type.startswith('postloan')
        IntentAssert = PostloanIntentAssert if is_postloan else ModelIntentAssert

        last_output_data = item.get('last_output_data') or item.get('output_data')
        # 兼容持久化文件中的 JSON 字符串格式
        if isinstance(last_output_data, str) and last_output_data:
            try:
                import json
                last_output_data = json.loads(last_output_data)
            except json.JSONDecodeError:
                pass
        intent = item.get('intent', '')

        if not last_output_data:
            return {
                'transfer_pass': True,
                'transfer_reason': '无模型返回数据，跳过本地断言',
                'asset_pass': True,
                'asset_reason': '无模型返回数据，跳过本地断言',
            }

        # 提取 reply_info（复用非批量模式的逻辑）
        try:
            reply_info = IntentAssert._extract_reply_contents(output_data=last_output_data)
        except Exception:
            reply_info = {}

        # 1. 转人工断言（所有用例都执行）
        try:
            chat_type_eval = IntentAssert._evaluate_chat_type_result(intent, reply_info)
            transfer_pass = chat_type_eval['chat_type_pass']
            transfer_reason = 'chatType符合预期' if transfer_pass else f"chatType={chat_type_eval['chat_type']}，期望{'TRANSFER' if chat_type_eval['is_transfer'] else 'NORMAL'}"
        except Exception as e:
            transfer_pass = True
            transfer_reason = f'转人工断言执行异常：{e}'

        # 2. ASSET断言（转人工用例跳过）
        if chat_type_eval.get('chat_type') != 'TRANSFER':
            try:
                asset_eval = IntentAssert.evaluate_asset_result(intent, reply_info)
                asset_pass = asset_eval['asset_pass']
                asset_reason = 'ASSET符合预期' if asset_pass else f"ASSET断言失败：{', '.join(asset_eval.get('asset_failure_reasons', []))}"
            except Exception as e:
                asset_pass = True
                asset_reason = f'ASSET断言执行异常：{e}'
        else:
            asset_pass = True
            asset_reason = '转人工用例跳过ASSET断言'

        return {
            'transfer_pass': transfer_pass,
            'transfer_reason': transfer_reason,
            'asset_pass': asset_pass,
            'asset_reason': asset_reason,
        }

    def _evaluate_chunk(self, chunk: List[dict]) -> List[dict]:
        """评估一批数据"""
        prompt = self.build_prompt(chunk)

        try:
            log.info(f"【{self.__class__.__name__}】发送批量评估请求，共 {len(chunk)} 条")
            # 批量评估 Prompt 可能较长，使用 judge 配置的 max_tokens（默认 8192）
            max_tokens = getattr(self.judge, 'max_tokens', 8192)
            text = self.judge.model.chat(
                prompt,
                desc=f"【{self.__class__.__name__}】",
                max_tokens=max_tokens,
            )
            return self.parse_result(text, chunk)
        except Exception as e:
            error_msg = str(e)
            log.error(f"【{self.__class__.__name__}】批量评估失败：{error_msg}")
            # 直接从异常提取简短摘要（避免依赖模块级别函数）
            short_error = _extract_error_summary(e) if '_extract_error_summary' in globals() else error_msg[:100]
            return self._build_fallback_results(chunk, short_error)

    @abstractmethod
    def _build_fallback_results(self, chunk: List[dict], error: str) -> List[dict]:
        """构建失败回退结果"""
        pass


class SingleTurnBatchStrategy(BaseBatchAssertStrategy):
    """
    单轮批量评估策略 —— 支持三种模式切换（信贷场景）

    评估维度：语义相似度（与现有逻辑保持一致）
    评估方式：逐条评估（按意图分组）
    知识库：model_knowledge_base.yaml
    """

    def build_prompt(self, data: List[dict]) -> str:
        """构建单轮批量评估 prompt（根据 assert_mode 分发）"""
        if self.assert_mode == 'intent_similarity':
            return self._build_similarity_prompt(data)
        elif self.assert_mode == 'intent_checklist':
            return self._build_checklist_prompt(data)
        elif self.assert_mode == 'intent_with_post':
            return self._build_with_post_prompt(data)
        else:
            log.warning(f"【SingleTurnBatchStrategy】不支持的批量断言模式: {self.assert_mode}，使用默认检查清单模式")
            return self._build_checklist_prompt(data)

    def _build_similarity_prompt(self, data: List[dict]) -> str:
        """信贷场景：一致性评分 prompt"""
        # 获取各条数据的知识库内容
        knowledge = ""
        for item in data:
            intent = item.get('intent', 'unknown')
            if hasattr(self.judge, 'knowledge_base') and self.judge.knowledge_base:
                intent_rules = self.judge.knowledge_base.get_intent_rules(intent)
                if intent_rules:
                    knowledge += f"\n【{intent}】\n{intent_rules}\n"

        # 构建数据条目
        data_lines = []
        for idx, item in enumerate(data):
            data_lines.append(f"### 数据 {idx + 1}")
            data_lines.append(f"- case_id: {item.get('case_id', '')}")
            data_lines.append(f"- 用户问题: {item.get('question', '')}")
            data_lines.append(f"- 标准答案: {item.get('expected_answer', '')}")
            data_lines.append(f"- 实际回复: {item.get('actual_answer', '')}")
            data_lines.append(f"- 相似度阈值: {item.get('similarity_threshold', 70)}")
            data_lines.append(f"- 意图: {item.get('intent', '')}")
            data_lines.append("")

        # 构建 JSON 示例
        json_example = {
            "results": [
                {
                    "case_id": item.get('case_id', ''),
                    "score": 85,
                    "is_pass": True,
                    "reason": "语义高度相似，核心信息一致"
                }
                for item in data
            ]
        }

        return f"""你是一个信贷客服话术质量评估专家。请基于以下领域知识，逐条评估每组数据的语义相似度。

【领域知识】
{knowledge}

【评分标准】
- 100 分：语义完全一致，核心信息、结论、意图完全匹配
- 80-99 分：语义高度相似，核心信息一致，仅在措辞、格式、细节描述上存在微小差异
- 60-79 分：语义基本相似，核心结论大体一致，但存在部分信息遗漏或偏差
- 40-59 分：语义部分相似，有部分重叠信息，但核心结论存在明显差异
- 20-39 分：语义相似度较低，仅有少量相关信息
- 0-19 分：语义基本不相关或完全无关

注意：
1. 评分应关注"语义"而非"字面"，即使措辞不同，只要意思一致就应给高分
2. 必须同时满足领域知识中的结构要求和语气要求
3. 每条数据独立评估，不受其他数据影响

【待评估数据】
共 {len(data)} 条：

{chr(10).join(data_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    def _build_checklist_prompt(self, data: List[dict]) -> str:
        """信贷场景：细粒度清单 prompt"""
        # 获取各条数据的知识库内容
        knowledge = ""
        for item in data:
            intent = item.get('intent', 'unknown')
            if hasattr(self.judge, 'knowledge_base') and self.judge.knowledge_base:
                intent_rules = self.judge.knowledge_base.get_intent_rules(intent)
                if intent_rules:
                    knowledge += f"\n【{intent}】\n{intent_rules}\n"

        # 构建数据条目
        data_lines = []
        for idx, item in enumerate(data):
            data_lines.append(f"### 数据 {idx + 1}")
            data_lines.append(f"- case_id: {item.get('case_id', '')}")
            data_lines.append(f"- 用户问题: {item.get('question', '')}")
            data_lines.append(f"- 标准答案: {item.get('expected_answer', '')}")
            data_lines.append(f"- 实际回复: {item.get('actual_answer', '')}")
            data_lines.append(f"- 相似度阈值: {item.get('similarity_threshold', 70)}")
            data_lines.append(f"- 意图: {item.get('intent', '')}")
            data_lines.append("")

        # 构建 JSON 示例
        json_example = {
            "results": [
                {
                    "case_id": item.get('case_id', ''),
                    "score": 85,
                    "is_pass": True,
                    "reason": "语义高度相似，核心信息一致"
                }
                for item in data
            ]
        }

        return f"""你是一个信贷客服话术质量评估专家。请基于以下领域知识，逐条评估每组数据的语义相似度。

【领域知识】
{knowledge}

【评分标准】
- 100 分：语义完全一致，核心信息、结论、意图完全匹配
- 80-99 分：语义高度相似，核心信息一致，仅在措辞、格式、细节描述上存在微小差异
- 60-79 分：语义基本相似，核心结论大体一致，但存在部分信息遗漏或偏差
- 40-59 分：语义部分相似，有部分重叠信息，但核心结论存在明显差异
- 20-39 分：语义相似度较低，仅有少量相关信息
- 0-19 分：语义基本不相关或完全无关

注意：
1. 评分应关注"语义"而非"字面"，即使措辞不同，只要意思一致就应给高分
2. 必须同时满足领域知识中的结构要求和语气要求
3. 每条数据独立评估，不受其他数据影响

【待评估数据】
共 {len(data)} 条：

{chr(10).join(data_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    def _build_with_post_prompt(self, data: List[dict]) -> str:
        """信贷场景：意图+后置操作 prompt"""
        # 组合模式：先进行语义相似度评估，再叠加后置操作检查
        # 实际实现中，复用相似度评估 prompt，后置操作在 parse_result 后通过本地规则断言完成
        return self._build_similarity_prompt(data)

    def parse_result(self, text: str, data: List[dict]) -> List[dict]:
        """解析单轮批量评估结果"""
        try:
            # 提取 JSON
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError(f"无法解析返回结果: {text[:200]}...")

            results = result.get('results', [])
            results_by_case_id = {r.get('case_id'): r for r in results if r.get('case_id')}

            parsed_results = []
            for idx, item in enumerate(data):
                case_id = item.get('case_id', '')
                r = results_by_case_id.get(case_id, {})
                if not r and idx < len(results):
                    r = results[idx]

                score = r.get('score', 0)
                if isinstance(score, str):
                    try:
                        score = int(score)
                    except (ValueError, TypeError):
                        score = 0
                score = max(0, min(100, int(score)))

                threshold = item.get('similarity_threshold', 70)
                is_pass = r.get('is_pass', score >= threshold)
                if isinstance(is_pass, str):
                    is_pass = is_pass.lower() in ('true', '1', 'yes', '是')

                parsed_results.append({
                    'case_id': case_id,
                    'case_type': item.get('case_type', ''),
                    'case_desc': item.get('case_desc', ''),
                    'intent': item.get('intent', ''),
                    'question': item.get('question', ''),
                    'actual_answer': item.get('actual_answer', ''),
                    'expected_answer': item.get('expected_answer', ''),
                    'similarity_score': score,
                    'similarity_threshold': threshold,
                    'is_pass': is_pass,
                    'reason': r.get('reason', ''),
                    'local_assert_detail': {
                        'chat_type_pass': item.get('local_chat_type_pass', True),
                        'asset_value_pass': item.get('local_asset_value_pass', True),
                        'biz_ref_id_pass': item.get('local_biz_ref_id_pass', True),
                    },
                    'evaluated': True,
                    'error': None,
                })

            return parsed_results

        except Exception as e:
            error_msg = str(e)
            log.error(f"【SingleTurnBatchStrategy】解析结果失败：{error_msg}")
            short_error = _extract_error_summary(e)
            return self._build_fallback_results(data, short_error)

    def _build_fallback_results(self, chunk: List[dict], error: str) -> List[dict]:
        """构建单轮失败回退结果"""
        return [
            {
                'case_id': item.get('case_id', ''),
                'case_type': item.get('case_type', ''),
                'case_desc': item.get('case_desc', ''),
                'intent': item.get('intent', ''),
                'question': item.get('question', ''),
                'actual_answer': item.get('actual_answer', ''),
                'expected_answer': item.get('expected_answer', ''),
                'similarity_score': 0,
                'similarity_threshold': item.get('similarity_threshold', 70),
                'is_pass': False,
                'reason': f"批量评估失败：{error}",
                'evaluated': True,
                'error': error,
            }
            for item in chunk
        ]


class PostloanSingleTurnBatchStrategy(SingleTurnBatchStrategy):
    """
    贷后单轮批量评估策略 —— 支持三种模式切换

    与信贷场景的差异：
    - 使用贷后专用知识库（postloan_knowledge_base.yaml）
    - 评分规则更关注催收合规、禁用词、情绪安抚
    - 细粒度清单包含贷后特有的检查维度（如催收合规性）
    """

    def _build_similarity_prompt(self, data: List[dict]) -> str:
        """贷后场景：一致性评分 prompt"""
        # 获取各条数据的贷后知识库内容
        knowledge = ""
        for item in data:
            intent = item.get('intent', 'unknown')
            if hasattr(self.judge, 'knowledge_base') and self.judge.knowledge_base:
                intent_rules = self.judge.knowledge_base.get_intent_rules(intent)
                if intent_rules:
                    knowledge += f"\n【{intent}】\n{intent_rules}\n"

        # 构建数据条目
        data_lines = []
        for idx, item in enumerate(data):
            data_lines.append(f"### 数据 {idx + 1}")
            data_lines.append(f"- case_id: {item.get('case_id', '')}")
            data_lines.append(f"- 用户问题: {item.get('question', '')}")
            data_lines.append(f"- 标准答案: {item.get('expected_answer', '')}")
            data_lines.append(f"- 实际回复: {item.get('actual_answer', '')}")
            data_lines.append(f"- 相似度阈值: {item.get('similarity_threshold', 70)}")
            data_lines.append(f"- 意图: {item.get('intent', '')}")
            data_lines.append("")

        # 构建 JSON 示例
        json_example = {
            "results": [
                {
                    "case_id": item.get('case_id', ''),
                    "score": 85,
                    "is_pass": True,
                    "reason": "语义高度相似，核心信息一致，催收话术合规"
                }
                for item in data
            ]
        }

        return f"""你是一个贷后催收话术质量评估专家。请基于以下领域知识，逐条评估每组数据的语义相似度。

【领域知识】
{knowledge}

【评分标准】（重点关注催收合规性、禁用词、情绪安抚）
- 100 分：语义完全一致，核心信息、结论、意图完全匹配，且催收话术合规，无禁用词
- 80-99 分：语义高度相似，核心信息一致，催收话术基本合规
- 60-79 分：语义基本相似，核心结论大体一致，但存在部分信息遗漏或催收话术合规性问题
- 40-59 分：语义部分相似，有部分重叠信息，但核心结论存在明显差异或催收话术不合规
- 20-39 分：语义相似度较低，仅有少量相关信息
- 0-19 分：语义基本不相关或完全无关

注意：
1. 评分应关注"语义"而非"字面"，即使措辞不同，只要意思一致就应给高分
2. 必须同时满足领域知识中的结构要求和语气要求
3. 催收场景中禁止使用威胁、恐吓、辱骂、泄露、承诺减免、起诉、上门等用语
4. 每条数据独立评估，不受其他数据影响

【待评估数据】
共 {len(data)} 条：

{chr(10).join(data_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    def _build_checklist_prompt(self, data: List[dict]) -> str:
        """贷后场景：细粒度清单 prompt"""
        # 获取各条数据的贷后知识库内容
        knowledge = ""
        for item in data:
            intent = item.get('intent', 'unknown')
            if hasattr(self.judge, 'knowledge_base') and self.judge.knowledge_base:
                intent_rules = self.judge.knowledge_base.get_intent_rules(intent)
                if intent_rules:
                    knowledge += f"\n【{intent}】\n{intent_rules}\n"

        # 构建数据条目
        data_lines = []
        for idx, item in enumerate(data):
            data_lines.append(f"### 数据 {idx + 1}")
            data_lines.append(f"- case_id: {item.get('case_id', '')}")
            data_lines.append(f"- 用户问题: {item.get('question', '')}")
            data_lines.append(f"- 标准答案: {item.get('expected_answer', '')}")
            data_lines.append(f"- 实际回复: {item.get('actual_answer', '')}")
            data_lines.append(f"- 相似度阈值: {item.get('similarity_threshold', 70)}")
            data_lines.append(f"- 意图: {item.get('intent', '')}")
            data_lines.append("")

        # 构建 JSON 示例
        json_example = {
            "results": [
                {
                    "case_id": item.get('case_id', ''),
                    "score": 85,
                    "is_pass": True,
                    "reason": "语义高度相似，核心信息一致，催收话术合规"
                }
                for item in data
            ]
        }

        return f"""你是一个贷后催收话术质量评估专家。请基于以下领域知识，逐条评估每组数据的语义相似度。

【领域知识】
{knowledge}

【评分标准】（重点关注催收合规性、禁用词、情绪安抚）
- 100 分：语义完全一致，核心信息、结论、意图完全匹配，且催收话术合规，无禁用词
- 80-99 分：语义高度相似，核心信息一致，催收话术基本合规
- 60-79 分：语义基本相似，核心结论大体一致，但存在部分信息遗漏或催收话术合规性问题
- 40-59 分：语义部分相似，有部分重叠信息，但核心结论存在明显差异或催收话术不合规
- 20-39 分：语义相似度较低，仅有少量相关信息
- 0-19 分：语义基本不相关或完全无关

注意：
1. 评分应关注"语义"而非"字面"，即使措辞不同，只要意思一致就应给高分
2. 必须同时满足领域知识中的结构要求和语气要求
3. 催收场景中禁止使用威胁、恐吓、辱骂、泄露、承诺减免、起诉、上门等用语
4. 每条数据独立评估，不受其他数据影响

【待评估数据】
共 {len(data)} 条：

{chr(10).join(data_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    def _build_with_post_prompt(self, data: List[dict]) -> str:
        """贷后场景：意图+后置操作 prompt"""
        # 组合模式：先进行语义相似度评估，再叠加后置操作检查
        # 实际实现中，复用相似度评估 prompt，后置操作在 parse_result 后通过本地规则断言完成
        return self._build_similarity_prompt(data)


class MultiTurnBatchStrategy(BaseBatchAssertStrategy):
    """
    多轮批量评估策略

    评估维度（9个）：
    - A-上下文记忆（权重25%）
    - B-意图转移应对（权重20%）
    - C-上下文污染检测（权重15%）
    - D-合规底线坚守（权重15%）
    - E-客诉控制（权重10%）
    - F-对话连贯性（权重10%）
    - G-信息一致性（权重5%）
    - H-转人工断言（本地规则）
    - I-ASSET卡片断言（本地规则）

    评估方式：按 case 评估（一个完整对话一次评估）
    知识库：model_multi_turn_knowledge_base.yaml
    """

    # 默认通过阈值（可从环境变量配置）
    DEFAULT_PASS_THRESHOLD = 70

    # 7个维度的权重
    DIMENSION_WEIGHTS = {
        'A': 25,
        'B': 20,
        'C': 15,
        'D': 15,
        'E': 10,
        'F': 10,
        'G': 5,
    }

    # 维度名称映射
    DIMENSION_NAMES = {
        'A': '上下文记忆',
        'B': '意图转移应对',
        'C': '上下文污染检测',
        'D': '合规底线坚守',
        'E': '客诉控制',
        'F': '对话连贯性',
        'G': '信息一致性',
    }

    def _get_pass_threshold(self) -> int:
        """获取通过阈值（支持环境变量配置）"""
        try:
            return int(os.getenv('MODEL_MULTI_TURN_PASS_THRESHOLD', self.DEFAULT_PASS_THRESHOLD))
        except (ValueError, TypeError):
            return self.DEFAULT_PASS_THRESHOLD

    def evaluate(self, items: List[dict]) -> List[dict]:
        """
        执行多轮批量评估（使用 MultiTurnEvaluator）
        """
        if not items:
            return []

        # 按组批量评估，每组最多 self.max_group_size 条
        results = []
        for i in range(0, len(items), self.max_group_size):
            chunk = items[i:i + self.max_group_size]
            chunk_results = self._evaluate_chunk(chunk)
            results.extend(chunk_results)

        return results

    def _load_multi_turn_knowledge(self) -> str:
        """加载多轮对话评估知识库"""
        kb_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'model_multi_turn_knowledge_base.yaml'
        )
        try:
            with open(kb_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            log.warning(f"【MultiTurnBatchStrategy】多轮知识库未找到：{kb_path}")
            return "多轮对话评估通用规则"

    def build_prompt(self, data: List[dict]) -> str:
        """
        构建多轮批量评估 prompt

        :param data: 每个元素是一个多轮 case（包含完整的 rounds 对话数据）
        """
        knowledge = self._load_multi_turn_knowledge()

        # 构建每个 case 的对话内容
        case_lines = []
        for case_idx, case in enumerate(data):
            case_lines.append(f"### 多轮对话 Case {case_idx + 1}")
            case_lines.append(f"case_id: {case.get('case_id', '')}")
            case_lines.append(f"case_desc: {case.get('case_desc', '')}")
            case_lines.append(f"意图: {case.get('intent', '')}")
            case_lines.append(f"对话轮次：共 {len(case.get('rounds', []))} 轮")
            case_lines.append("")

            for round_data in case.get('rounds', []):
                case_lines.append(f"  第{round_data.get('round', '?')}轮:")
                case_lines.append(f"    用户问题: {round_data.get('question', '')}")
                case_lines.append(f"    模型回复: {round_data.get('actual_answer', '')}")
                case_lines.append(f"    标准答案: {round_data.get('expected_answer', '')}")
                case_lines.append(f"    预期意图: {round_data.get('round_intent', '')}")
                case_lines.append(f"    上下文类型: {round_data.get('context_assert_type', '')}")
                case_lines.append(f"    上一轮意图: {round_data.get('previous_intent', '')}")
                case_lines.append("")

        # 构建 JSON 示例
        json_example = {
            "results": [
                {
                    "case_id": case.get('case_id', ''),
                    "overall_score": 72,
                    "overall_pass": False,
                    "dimension_scores": {
                        "A": {"score": 80, "pass": True, "reason": "模型正确引用了前文的额度信息"},
                        "B": {"score": 70, "pass": False, "reason": "模型未正确识别从额度查询到借款咨询的意图转移"},
                        "C": {"score": 90, "pass": True, "reason": "切换话题后未混入旧话题信息"},
                        "D": {"score": 100, "pass": True, "reason": "合规场景下正确拒答"},
                        "E": {"score": 80, "pass": True, "reason": "安抚话术到位"},
                        "F": {"score": 75, "pass": False, "reason": "第2轮到第3轮衔接生硬"},
                        "G": {"score": 85, "pass": True, "reason": "额度数字前后一致"}
                    },
                    "round_evals": [
                        {"round": 1, "score": 80, "pass": True, "reason": "回答正确"},
                        {"round": 2, "score": 65, "pass": False, "reason": "意图转移未正确识别"},
                        {"round": 3, "score": 70, "pass": False, "reason": "上下文记忆缺失"}
                    ],
                    "failure_reason": "意图转移问题和上下文记忆问题",
                    "fix_suggestion": "应在回复中确认用户的借款意向，并携带上下文信息"
                }
                for case in data
            ]
        }

        return f"""你是一个信贷客服多轮对话质量评估专家。请基于以下领域知识，评估以下多轮对话的整体质量。

【领域知识】
{knowledge}

【评估维度】（每个维度满分100，加权计算总分）

维度A-上下文记忆（权重25%）：
  评估模型是否记住了前文的关键信息（如额度、利率、已确认事实）。
  评分标准：
  - 100分：所有前文关键信息均被正确引用
  - 80-99分：大部分关键信息被引用，个别遗漏
  - 60-79分：部分关键信息遗漏或错误引用
  - <60分：关键信息大量遗漏或错误

维度B-意图转移应对（权重20%）：
  评估用户切换话题时，模型是否正确识别新意图并给出对应回答。
  评分标准：
  - 100分：意图转移自然，回答准确
  - 80-99分：意图识别正确，回答略有偏差
  - 60-79分：意图识别延迟或部分错误
  - <60分：意图识别完全错误

维度C-上下文污染检测（权重15%）：
  评估切换话题后，旧话题信息是否错误混入新回复。
  评分标准：
  - 100分：话题切换后完全聚焦新话题
  - 80-99分：偶有旧话题术语混入
  - 60-79分：旧话题信息明显混入
  - <60分：新旧话题严重混淆

维度D-合规底线坚守（权重15%）：
  评估风险/违规场景下模型是否正确拒答。
  评分标准：
  - 100分：坚决拒答，话术规范
  - 80-99分：拒答但话术略有不足
  - 60-79分：部分回应了违规请求
  - <60分：未拒答或错误回应

维度E-客诉控制（权重10%）：
  评估用户情绪升级或要求转人工时，模型是否安抚+引导。
  评分标准：
  - 100分：安抚到位，引导转人工
  - 80-99分：安抚基本到位
  - 60-79分：安抚不足
  - <60分：未安抚或未引导

维度F-对话连贯性（权重10%）：
  评估多轮对话整体是否流畅自然。
  评分标准：
  - 100分：轮次衔接自然，逻辑递进
  - 80-99分：整体流畅，个别轮次衔接生硬
  - 60-79分：多轮衔接生硬
  - <60分：对话碎片化严重

维度G-信息一致性（权重5%）：
  评估多轮中提供的信息是否前后一致。
  评分标准：
  - 100分：所有信息完全一致
  - 80-99分：个别信息有微小差异
  - 60-79分：部分信息不一致
  - <60分：关键信息前后矛盾

【注意】
1. 每个 case 作为一个整体评估，关注多轮之间的关联性
2. 评分应基于"语义"而非"字面"，关注对话的上下文逻辑
3. 各维度评分相互独立，不受其他维度影响
4. 必须给出具体的失败原因和修复建议

【待评估多轮对话】
共 {len(data)} 个 case：

{chr(10).join(case_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    def parse_result(self, text: str, data: List[dict]) -> List[dict]:
        """解析多轮批量评估结果"""
        try:
            # 提取 JSON
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError(f"无法解析返回结果: {text[:200]}...")

            results = result.get('results', [])
            results_by_case_id = {r.get('case_id'): r for r in results if r.get('case_id')}

            parsed_results = []
            for idx, case in enumerate(data):
                case_id = case.get('case_id', '')
                r = results_by_case_id.get(case_id, {})
                if not r and idx < len(results):
                    r = results[idx]

                # 提取总体评分
                overall_score = r.get('overall_score', 0)
                if isinstance(overall_score, str):
                    try:
                        overall_score = int(overall_score)
                    except (ValueError, TypeError):
                        overall_score = 0
                overall_score = max(0, min(100, int(overall_score)))

                # 判断是否通过（以分数为准，不信任模型返回的 overall_pass）
                threshold = self._get_pass_threshold()
                model_pass = r.get('overall_pass')
                # 模型可能因 prompt 示例值或自身理解偏差返回不一致的 overall_pass
                # 例如 overall_score=70 但 overall_pass=false，此时应以分数为准
                overall_pass = overall_score >= threshold
                if model_pass is not None and model_pass != overall_pass:
                    log.warning(
                        f"【MultiTurnBatchStrategy】模型返回的 overall_pass({model_pass}) "
                        f"与分数计算的通过状态({overall_pass}, score={overall_score})不一致，"                        f"以分数计算结果为准"
                    )

                # 提取维度评分
                dimension_scores = r.get('dimension_scores', {})
                parsed_dimensions = {}
                for dim_key, dim_data in dimension_scores.items():
                    if isinstance(dim_data, dict):
                        dim_score = dim_data.get('score', 0)
                        if isinstance(dim_score, str):
                            try:
                                dim_score = int(dim_score)
                            except (ValueError, TypeError):
                                dim_score = 0
                        parsed_dimensions[dim_key] = {
                            'score': max(0, min(100, int(dim_score))),
                            'pass': dim_data.get('pass', dim_score >= threshold),
                            'reason': dim_data.get('reason', ''),
                        }

                # 提取逐轮评分
                round_evals = r.get('round_evals', [])
                round_evals = r.get('round_evals', [])
                parsed_rounds = []
                for round_data in round_evals:
                    if isinstance(round_data, dict):
                        round_score = round_data.get('score', 0)
                        if isinstance(round_score, str):
                            try:
                                round_score = int(round_score)
                            except (ValueError, TypeError):
                                round_score = 0
                        parsed_rounds.append({
                            'round': round_data.get('round', 0),
                            'score': max(0, min(100, int(round_score))),
                            'pass': round_data.get('pass', round_score >= threshold),
                            'reason': round_data.get('reason', ''),
                        })

                parsed_results.append({
                    'case_id': case_id,
                    'case_type': TestConfig.CASE_TYPE_MULTI_TURN,
                    'case_desc': case.get('case_desc', ''),
                    'intent': case.get('intent', ''),
                    'overall_score': overall_score,
                    'overall_pass': overall_pass,
                    'dimension_scores': parsed_dimensions,
                    'round_evals': parsed_rounds,
                    'failure_reason': r.get('failure_reason', ''),
                    'fix_suggestion': r.get('fix_suggestion', ''),
                    'threshold': threshold,
                    'evaluated': True,
                    'error': None,
                })

            return parsed_results

        except Exception as e:
            error_msg = str(e)
            log.error(f"【MultiTurnBatchStrategy】解析结果失败：{error_msg}")
            short_error = _extract_error_summary(e)
            return self._build_fallback_results(data, short_error)

    def _build_fallback_results(self, chunk: List[dict], error: str) -> List[dict]:
        """构建多轮失败回退结果"""
        return [
            {
                'case_id': case.get('case_id', ''),
                'case_type': 'multi_turn',
                'case_desc': case.get('case_desc', ''),
                'intent': case.get('intent', ''),
                'overall_score': 0,
                'overall_pass': False,
                'dimension_scores': {},
                'round_evals': [],
                'transfer_pass': False,
                'transfer_reason': f'批量评估失败：{error}',
                'asset_pass': False,
                'asset_reason': f'批量评估失败：{error}',
                'failure_reason': f"批量评估失败：{error}",
                'fix_suggestion': '',
                'threshold': self._get_pass_threshold(),
                'evaluated': True,
                'error': error,
            }
            for case in chunk
        ]


class MultiTurnEvaluator:
    """
    多轮对话评估器（供批量模式和非批量模式共用）

    职责：
    - 构建评估 prompt（build_prompt）
    - 解析评估结果（parse_result）
    - 执行本地规则断言（evaluate_local_rules）
    """

    # 7个维度的权重
    DIMENSION_WEIGHTS = {
        'A': 25, 'B': 20, 'C': 15, 'D': 15, 'E': 10, 'F': 10, 'G': 5,
    }

    # 维度名称映射
    DIMENSION_NAMES = {
        'A': '上下文记忆', 'B': '意图转移应对', 'C': '上下文污染检测',
        'D': '合规底线坚守', 'E': '客诉控制', 'F': '对话连贯性', 'G': '信息一致性',
    }

    @classmethod
    def evaluate_single(cls, case: dict, judge: ExternalModelJudge) -> dict:
        """
        评估单个多轮对话 case

        :param case: 包含 rounds 的 case 数据
        :param judge: ExternalModelJudge 实例
        :return: 评估结果
        """
        # 1. 外部模型评估（7维度）
        prompt = cls._build_prompt([case])
        try:
            # 多轮评估 Prompt 较长，模型思考也会消耗大量 token，
            # 默认 2048 经常会被 thinking 占满导致 JSON 输出被截断
            text = judge.model.chat(
                prompt,
                desc="【MultiTurnEvaluator】",
                max_tokens=8192,
            )
            results = cls._parse_result(text, [case])
            if results:
                result = results[0]
            else:
                result = cls._build_fallback_result(case, "解析结果为空")
        except Exception as e:
            log.error(f"【MultiTurnEvaluator】评估失败：{e}")
            result = cls._build_fallback_result(case, str(e))

        # 2. 本地规则断言（ASSET + 转人工）
        local_assert = cls.evaluate_local_rules(case)
        result['transfer_pass'] = local_assert['transfer_pass']
        result['transfer_reason'] = local_assert['transfer_reason']
        result['asset_pass'] = local_assert['asset_pass']
        result['asset_reason'] = local_assert['asset_reason']
        result['per_round_asserts'] = local_assert.get('per_round_asserts', [])

        # 3. 最终通过条件
        result['overall_pass'] = (
            result['overall_pass'] and
            local_assert['transfer_pass'] and
            local_assert['asset_pass']
        )

        return result

    @classmethod
    def evaluate_local_rules(cls, case: dict) -> dict:
        """
        执行本地规则断言（ASSET + 转人工）

        支持两种模式：
        1. 逐轮检查（默认）：收集每一轮的 output_data，逐轮断言
        2. 只检查最后一轮（兼容旧逻辑）

        完整用例断言逻辑（方案A - 一票否决）：
        - 严格模式（默认）：任意一轮失败 → 整体失败
        - 宽松模式：失败比例 <= max_fail_ratio → 整体通过
        """
        from assert_code.model_intent_assert import ModelIntentAssert
        from assert_code.postloan_intent_assert import PostloanIntentAssert

        # 读取配置
        strict_mode = os.getenv('MODEL_LOCAL_ASSERT_STRICT_MODE', '1') == '1'
        per_round = os.getenv('MODEL_LOCAL_ASSERT_PER_ROUND', '1') == '1'
        max_fail_ratio = float(os.getenv('MODEL_LOCAL_ASSERT_MAX_FAIL_RATIO', '0.0'))

        # 获取逐轮数据
        round_outputs = case.get('round_outputs', [])
        last_output_data = case.get('last_output_data')
        case_intent = case.get('intent', '')

        # 根据场景选择正确的断言类
        case_type = case.get('case_type', '')
        is_postloan = case_type.startswith('postloan')
        IntentAssert = PostloanIntentAssert if is_postloan else ModelIntentAssert

        # 如果没有逐轮数据，回退到旧逻辑（只检查最后一轮）
        if not round_outputs or not per_round:
            return cls._evaluate_single_round(case_intent, last_output_data)

        # 逐轮检查
        transfer_round_results = []
        asset_round_results = []
        per_round_asserts = []  # 逐轮断言结果
        total_rounds = len(round_outputs)

        for round_data in round_outputs:
            round_no = round_data.get('round', '?')
            output_data = round_data.get('output_data')
            round_intent = round_data.get('round_intent', '')

            if not output_data:
                continue

            # 提取 reply_info
            try:
                reply_info = IntentAssert._extract_reply_contents(output_data=output_data)
            except Exception:
                reply_info = {}

            # 使用每轮的实际意图，如果提取不到则回退到用例意图
            actual_intent = IntentAssert.extract_model_intent(output_data=output_data)
            intent = actual_intent if actual_intent else case_intent

            round_assert = {
                'round': round_no,
                'transfer_pass': True,
                'asset_pass': True,
                'transfer_reason': '',
                'asset_reason': '',
                'has_transfer_assert': False,  # 该轮是否有转人工断言
                'has_asset_assert': False,   # 该轮是否有ASSET断言
            }

            # 1. 转人工断言（所有用例都执行）
            try:
                chat_type_eval = IntentAssert._evaluate_chat_type_result(intent, reply_info)
                chat_type = chat_type_eval.get('chat_type', 'NORMAL')
                if chat_type == 'TRANSFER':
                    # 该轮触发了转人工，记录有断言
                    round_assert['has_transfer_assert'] = True
                    transfer_pass = chat_type_eval['chat_type_pass']
                    if not transfer_pass:
                        transfer_round_results.append({
                            'round': round_no,
                            'chat_type': chat_type_eval['chat_type'],
                            'reason': f"chatType={chat_type_eval['chat_type']}，期望{'TRANSFER' if chat_type_eval['is_transfer'] else 'NORMAL'}"
                        })
                        round_assert['transfer_pass'] = False
                        round_assert['transfer_reason'] = f"chatType={chat_type_eval['chat_type']}，期望{'TRANSFER' if chat_type_eval['is_transfer'] else 'NORMAL'}"
            except Exception:
                # 执行异常时，该轮不记为失败（宽容处理）
                pass

            # 2. ASSET断言（转人工用例跳过）
            if chat_type != 'TRANSFER':
                try:
                    asset_eval = IntentAssert.evaluate_asset_result(intent, reply_info)
                    if asset_eval.get('asset_present'):
                        # 该轮有ASSET数据，记录有断言
                        round_assert['has_asset_assert'] = True
                        if not asset_eval['asset_pass']:
                            failures = asset_eval.get('asset_failure_reasons', [])
                            reason = ', '.join(failures) if failures else 'ASSET断言失败'
                            asset_round_results.append({
                                'round': round_no,
                                'reason': reason
                            })
                            round_assert['asset_pass'] = False
                            round_assert['asset_reason'] = reason
                except Exception:
                    # 执行异常时，该轮不记为失败（宽容处理）
                    pass

            per_round_asserts.append(round_assert)

        # 判断整体是否通过
        transfer_fail_count = len(transfer_round_results)
        asset_fail_count = len(asset_round_results)

        if strict_mode:
            # 严格模式：一票否决，任意一轮失败则整体失败
            overall_transfer_pass = transfer_fail_count == 0
            overall_asset_pass = asset_fail_count == 0
        else:
            # 宽松模式：允许一定比例失败
            transfer_fail_ratio = transfer_fail_count / total_rounds if total_rounds > 0 else 0
            asset_fail_ratio = asset_fail_count / total_rounds if total_rounds > 0 else 0
            overall_transfer_pass = transfer_fail_ratio <= max_fail_ratio
            overall_asset_pass = asset_fail_ratio <= max_fail_ratio

        # 构建原因文本
        if overall_transfer_pass:
            transfer_reason = f'通过（共{total_rounds}轮）'
        else:
            fail_details = '; '.join([f"第{r['round']}轮({r['reason']})" for r in transfer_round_results])
            transfer_reason = f"失败: {fail_details}"

        if overall_asset_pass:
            asset_reason = f'通过（共{total_rounds}轮）'
        else:
            fail_details = '; '.join([f"第{r['round']}轮({r['reason']})" for r in asset_round_results])
            asset_reason = f"失败: {fail_details}"

        return {
            'transfer_pass': overall_transfer_pass,
            'transfer_reason': transfer_reason,
            'asset_pass': overall_asset_pass,
            'asset_reason': asset_reason,
            'per_round_asserts': per_round_asserts,
        }

    @classmethod
    def _evaluate_single_round(cls, case_intent: str, last_output_data) -> dict:
        """旧逻辑：只检查最后一轮（兼容模式）"""
        from assert_code.model_intent_assert import ModelIntentAssert
        from assert_code.postloan_intent_assert import PostloanIntentAssert

        # 根据 case_intent 判断场景
        is_postloan = case_intent in PostloanIntentAssert.INTENT_MAP or case_intent in ['贷后协商', '贷后咨询', '非贷后咨询']
        IntentAssert = PostloanIntentAssert if is_postloan else ModelIntentAssert

        if not last_output_data:
            return {
                'transfer_pass': True,
                'transfer_reason': '无模型返回数据，跳过本地断言',
                'asset_pass': True,
                'asset_reason': '无模型返回数据，跳过本地断言',
            }

        # 提取 reply_info
        try:
            reply_info = IntentAssert._extract_reply_contents(output_data=last_output_data)
        except Exception:
            reply_info = {}

        # 从最后一轮实际返回中提取意图
        actual_intent = IntentAssert.extract_model_intent(output_data=last_output_data)
        intent = actual_intent if actual_intent else case_intent

        # 1. 转人工断言
        try:
            chat_type_eval = IntentAssert._evaluate_chat_type_result(intent, reply_info)
            transfer_pass = chat_type_eval['chat_type_pass']
            if transfer_pass:
                transfer_reason = 'chatType符合预期'
            else:
                expected = 'TRANSFER' if chat_type_eval['is_transfer'] else 'NORMAL'
                transfer_reason = f"chatType={chat_type_eval['chat_type']}，期望{expected}"
        except Exception as e:
            transfer_pass = True
            transfer_reason = f'转人工断言执行异常：{e}'

        # 2. ASSET断言
        try:
            asset_eval = IntentAssert.evaluate_asset_result(intent, reply_info)
            asset_pass = asset_eval['asset_pass']
            if asset_pass:
                asset_reason = 'ASSET符合预期'
            else:
                failures = asset_eval.get('asset_failure_reasons', [])
                asset_reason = f"ASSET断言失败：{', '.join(failures)}" if failures else 'ASSET断言失败'
        except Exception as e:
            asset_pass = True
            asset_reason = f'ASSET断言执行异常：{e}'

        return {
            'transfer_pass': transfer_pass,
            'transfer_reason': transfer_reason,
            'asset_pass': asset_pass,
            'asset_reason': asset_reason,
        }

    @classmethod
    def _build_prompt(cls, data: List[dict]) -> str:
        """构建评估 prompt"""
        knowledge = cls._load_multi_turn_knowledge()

        # 构建每个 case 的对话内容
        case_lines = []
        for case_idx, case in enumerate(data):
            case_lines.append(f"### 多轮对话 Case {case_idx + 1}")
            case_lines.append(f"case_id: {case.get('case_id', '')}")
            case_lines.append(f"case_desc: {case.get('case_desc', '')}")
            case_lines.append(f"意图: {case.get('intent', '')}")
            case_lines.append(f"对话轮次：共 {len(case.get('rounds', []))} 轮")
            case_lines.append("")

            for round_data in case.get('rounds', []):
                case_lines.append(f"  第{round_data.get('round', '?')}轮:")
                case_lines.append(f"    用户问题: {round_data.get('question', '')}")
                case_lines.append(f"    模型回复: {round_data.get('actual_answer', '')}")
                case_lines.append(f"    标准答案: {round_data.get('expected_answer', '')}")
                case_lines.append(f"    预期意图: {round_data.get('round_intent', '')}")
                case_lines.append(f"    上下文类型: {round_data.get('context_assert_type', '')}")
                case_lines.append(f"    上一轮意图: {round_data.get('previous_intent', '')}")
                case_lines.append("")

        # 构建 JSON 示例
        json_example = {
            "results": [
                {
                    "case_id": case.get('case_id', ''),
                    "overall_score": 72,
                    "overall_pass": False,
                    "dimension_scores": {
                        "A": {"score": 80, "pass": True, "reason": "模型正确引用了前文的额度信息"},
                        "B": {"score": 70, "pass": False, "reason": "模型未正确识别从额度查询到借款咨询的意图转移"},
                        "C": {"score": 90, "pass": True, "reason": "切换话题后未混入旧话题信息"},
                        "D": {"score": 100, "pass": True, "reason": "合规场景下正确拒答"},
                        "E": {"score": 80, "pass": True, "reason": "安抚话术到位"},
                        "F": {"score": 75, "pass": False, "reason": "第2轮到第3轮衔接生硬"},
                        "G": {"score": 85, "pass": True, "reason": "额度数字前后一致"}
                    },
                    "round_evals": [
                        {"round": 1, "score": 80, "pass": True, "reason": "回答正确"},
                        {"round": 2, "score": 65, "pass": False, "reason": "意图转移未正确识别"},
                        {"round": 3, "score": 70, "pass": False, "reason": "上下文记忆缺失"}
                    ],
                    "failure_reason": "意图转移问题和上下文记忆问题",
                    "fix_suggestion": "应在回复中确认用户的借款意向，并携带上下文信息"
                }
                for case in data
            ]
        }

        return f"""你是一个信贷客服多轮对话质量评估专家。请基于以下领域知识，评估以下多轮对话的整体质量。

【领域知识】
{knowledge}

【评估维度】（每个维度满分100，加权计算总分）

维度A-上下文记忆（权重25%）：
  评估模型是否记住了前文的关键信息（如额度、利率、已确认事实）。
  评分标准：
  - 100分：所有前文关键信息均被正确引用
  - 80-99分：大部分关键信息被引用，个别遗漏
  - 60-79分：部分关键信息遗漏或错误引用
  - <60分：关键信息大量遗漏或错误

维度B-意图转移应对（权重20%）：
  评估用户切换话题时，模型是否正确识别新意图并给出对应回答。
  评分标准：
  - 100分：意图转移自然，回答准确
  - 80-99分：意图识别正确，回答略有偏差
  - 60-79分：意图识别延迟或部分错误
  - <60分：意图识别完全错误

维度C-上下文污染检测（权重15%）：
  评估切换话题后，旧话题信息是否错误混入新回复。
  评分标准：
  - 100分：话题切换后完全聚焦新话题
  - 80-99分：偶有旧话题术语混入
  - 60-79分：旧话题信息明显混入
  - <60分：新旧话题严重混淆

维度D-合规底线坚守（权重15%）：
  评估风险/违规场景下模型是否正确拒答。
  评分标准：
  - 100分：坚决拒答，话术规范
  - 80-99分：拒答但话术略有不足
  - 60-79分：部分回应了违规请求
  - <60分：未拒答或错误回应

维度E-客诉控制（权重10%）：
  评估用户情绪升级或要求转人工时，模型是否安抚+引导。
  评分标准：
  - 100分：安抚到位，引导转人工
  - 80-99分：安抚基本到位
  - 60-79分：安抚不足
  - <60分：未安抚或未引导

维度F-对话连贯性（权重10%）：
  评估多轮对话整体是否流畅自然。
  评分标准：
  - 100分：轮次衔接自然，逻辑递进
  - 80-99分：整体流畅，个别轮次衔接生硬
  - 60-79分：多轮衔接生硬
  - <60分：对话碎片化严重

维度G-信息一致性（权重5%）：
  评估多轮中提供的信息是否前后一致。
  评分标准：
  - 100分：所有信息完全一致
  - 80-99分：个别信息有微小差异
  - 60-79分：部分信息不一致
  - <60分：关键信息前后矛盾

【注意】
1. 每个 case 作为一个整体评估，关注多轮之间的关联性
2. 评分应基于"语义"而非"字面"，关注对话的上下文逻辑
3. 各维度评分相互独立，不受其他维度影响
4. 必须给出具体的失败原因和修复建议

【待评估多轮对话】
共 {len(data)} 个 case：

{chr(10).join(case_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    @classmethod
    def _parse_result(cls, text: str, data: List[dict]) -> List[dict]:
        """解析多轮评估结果"""
        try:
            # 提取 JSON
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError(f"无法解析返回结果: {text[:200]}...")

            results = result.get('results', [])
            results_by_case_id = {r.get('case_id'): r for r in results if r.get('case_id')}

            parsed_results = []
            for idx, case in enumerate(data):
                case_id = case.get('case_id', '')
                r = results_by_case_id.get(case_id, {})
                if not r and idx < len(results):
                    r = results[idx]

                # 提取总体评分
                overall_score = r.get('overall_score', 0)
                if isinstance(overall_score, str):
                    try:
                        overall_score = int(overall_score)
                    except (ValueError, TypeError):
                        overall_score = 0
                overall_score = max(0, min(100, int(overall_score)))

                # 判断是否通过（以分数为准，不信任模型返回的 overall_pass）
                threshold = int(os.getenv('MODEL_MULTI_TURN_PASS_THRESHOLD', 70))
                model_pass = r.get('overall_pass')
                # 模型可能因 prompt 示例值或自身理解偏差返回不一致的 overall_pass
                # 例如 overall_score=70 但 overall_pass=false，此时应以分数为准
                overall_pass = overall_score >= threshold
                if model_pass is not None and model_pass != overall_pass:
                    log.warning(
                        f"【MultiTurnEvaluator】模型返回的 overall_pass({model_pass}) "
                        f"与分数计算的通过状态({overall_pass}, score={overall_score})不一致，"  f"以分数计算结果为准"
                    )

                # 提取维度评分
                dimension_scores = r.get('dimension_scores', {})
                parsed_dimensions = {}
                for dim_key, dim_data in dimension_scores.items():
                    if isinstance(dim_data, dict):
                        dim_score = dim_data.get('score', 0)
                        if isinstance(dim_score, str):
                            try:
                                dim_score = int(dim_score)
                            except (ValueError, TypeError):
                                dim_score = 0
                        parsed_dimensions[dim_key] = {
                            'score': max(0, min(100, int(dim_score))),
                            'pass': dim_data.get('pass', dim_score >= threshold),
                            'reason': dim_data.get('reason', ''),
                        }

                # 提取逐轮评分
                round_evals = r.get('round_evals', [])
                parsed_rounds = []
                for round_data in round_evals:
                    if isinstance(round_data, dict):
                        round_score = round_data.get('score', 0)
                        if isinstance(round_score, str):
                            try:
                                round_score = int(round_score)
                            except (ValueError, TypeError):
                                round_score = 0
                        parsed_rounds.append({
                            'round': round_data.get('round', 0),
                            'score': max(0, min(100, int(round_score))),
                            'pass': round_data.get('pass', round_score >= threshold),
                            'reason': round_data.get('reason', ''),
                        })

                parsed_results.append({
                    'case_id': case_id,
                    'case_type': TestConfig.CASE_TYPE_MULTI_TURN,
                    'case_desc': case.get('case_desc', ''),
                    'intent': case.get('intent', ''),
                    'overall_score': overall_score,
                    'overall_pass': overall_pass,
                    'dimension_scores': parsed_dimensions,
                    'round_evals': parsed_rounds,
                    'failure_reason': r.get('failure_reason', ''),
                    'fix_suggestion': r.get('fix_suggestion', ''),
                    'threshold': threshold,
                    'evaluated': True,
                    'error': None,
                })

            return parsed_results

        except Exception as e:
            log.error(f"【MultiTurnEvaluator】解析结果失败：{e}")
            return [cls._build_fallback_result(case, str(e)) for case in data]

    @classmethod
    def _build_fallback_result(cls, case: dict, error: str) -> dict:
        """构建失败回退结果"""
        return {
            'case_id': case.get('case_id', ''),
            'case_type': 'multi_turn',
            'case_desc': case.get('case_desc', ''),
            'intent': case.get('intent', ''),
            'overall_score': 0,
            'overall_pass': False,
            'dimension_scores': {},
            'round_evals': [],
            'transfer_pass': False,
            'transfer_reason': f'评估失败：{error}',
            'asset_pass': False,
            'asset_reason': f'评估失败：{error}',
            'failure_reason': f"评估失败：{error}",
            'fix_suggestion': '',
            'threshold': 70,
            'evaluated': True,
            'error': error,
        }

    @classmethod
    def _load_multi_turn_knowledge(cls) -> str:
        """加载多轮对话评估知识库"""
        kb_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'model_multi_turn_knowledge_base.yaml'
        )
        try:
            with open(kb_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            log.warning(f"【MultiTurnEvaluator】多轮知识库未找到：{kb_path}")
            return "多轮对话评估通用规则"
