# -*- coding: utf-8 -*-
"""
# @File    : postloan_multi_turn_assert.py
# @Date    : 2026-06-30
# @Author  : jeremyzhai
# @Description : 贷后催收多轮对话断言核心模块
#
# 设计原则：
#   1. 与信贷多轮逻辑完全解耦，不继承 MultiTurnBatchStrategy/MultiTurnEvaluator
#   2. 评测维度与信贷保持一致（A-G 7维度），但知识库和 Prompt 独立
#   3. 新增催收合规性检查（违禁词、威胁用语、泄露等）
#   4. 支持批量评估和单条评估两种模式
"""

import json
import os
import re
from typing import List, Dict

from assert_code.batch_assert_strategies import BaseBatchAssertStrategy
from assert_code.external_model_judge import ExternalModelJudge
from debug_model_by_pytest import TestConfig
from utils.handle_log import log


# ============================================================
# 常量定义
# ============================================================

# 7维度权重（与信贷保持一致）
POSTLOAN_DIMENSION_WEIGHTS = {
    'A': 25, 'B': 20, 'C': 15, 'D': 15, 'E': 10, 'F': 10, 'G': 5,
}

# 维度名称映射（催收场景语义）
POSTLOAN_DIMENSION_NAMES = {
    'A': '上下文记忆',
    'B': '意图转移应对',
    'C': '上下文污染检测',
    'D': '催收合规底线坚守',
    'E': '情绪安抚与客诉控制',
    'F': '对话连贯性',
    'G': '信息一致性',
}

# 默认知识库路径
DEFAULT_POSTLOAN_KB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'config', 'postloan_multi_turn_knowledge_base.yaml'
)

# 催收合规违禁词列表
POSTLOAN_COLLECTION_VIOLATION_KEYWORDS = [
    # 威胁恐吓类
    '再不还款就起诉', '法院传票', '律师函', '派出所', '逮捕', '坐牢',
    '暴力催收', '上门', '堵门', '泼油漆', '堵你家门',
    # 侮辱标签类
    '老赖', '失信人', '黑名单', '社会败类',
    # 泄露隐私类
    '告诉你家人', '告诉你公司', '通知你通讯录', '群发你的信息',
    # 越权承诺类
    '给你减免', '免除利息', '免掉罚息', '延期三个月', '分期一年',
    # 夸大后果类
    '影响子女上学', '影响买房买车', '永久黑名单',
]


# ============================================================
# 催收合规性检查工具
# ============================================================

def check_collection_compliance(text: str) -> Dict:
    """
    检查催收话术合规性

    返回：{
        'is_pass': bool,
        'violation_keywords': List[str],
        'violation_count': int,
        'detail': str,
    }
    """
    if not text:
        return {
            'is_pass': True,
            'violation_keywords': [],
            'violation_count': 0,
            'detail': '文本为空，无合规检查',
        }

    violations = []
    for keyword in POSTLOAN_COLLECTION_VIOLATION_KEYWORDS:
        if keyword in text:
            violations.append(keyword)

    # 正则匹配更广泛的违规模式
    threat_patterns = [
        r'再不.{0,5}还款.{0,5}(?:起诉|告你|抓你|上门)',
        r'已经.{0,3}(?:立案|起诉|报警|报警)',
        r'(?i)(?:老赖|失信人|黑名单).{0,5}(?:就是|就是你|就是你)',
        r'告诉.{0,5}(?:你家人|你公司|你朋友|你同事)',
        r'(?i)(?:征信|信用).{0,10}(?:废了|完了|彻底|永久)',
        r'(?i)(?:减免|免除|免掉).{0,5}(?:利息|罚息|滞纳金|全部)',
        r'(?i)(?:暴力|上门|堵门).{0,5}(?:催收|追债|要钱)',
    ]
    for pattern in threat_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if match and match not in violations:
                violations.append(match)

    violation_count = len(violations)
    is_pass = violation_count == 0

    detail = ''
    if not is_pass:
        detail = f"检测到 {violation_count} 处违规用语：{', '.join(violations[:5])}"

    return {
        'is_pass': is_pass,
        'violation_keywords': violations,
        'violation_count': violation_count,
        'detail': detail,
    }


# ============================================================
# 贷后多轮批量评估策略
# ============================================================

class PostloanMultiTurnBatchStrategy(BaseBatchAssertStrategy):
    """
    贷后催收多轮批量评估策略

    与信贷 MultiTurnBatchStrategy 的核心区别：
    - 使用贷后专用知识库（postloan_multi_turn_knowledge_base.yaml）
    - Prompt 中的评分标准、场景示例均为催收场景
    - 新增催收合规性检查维度
    """

    DEFAULT_PASS_THRESHOLD = 70

    def __init__(self, judge: ExternalModelJudge, max_group_size: int = 2):
        super().__init__(judge=judge, max_group_size=max_group_size)
        self.kb_path = DEFAULT_POSTLOAN_KB_PATH

    def _get_pass_threshold(self) -> int:
        """获取通过阈值（支持环境变量配置）"""
        try:
            return int(os.getenv('MODEL_POSTLOAN_MULTI_TURN_PASS_THRESHOLD', self.DEFAULT_PASS_THRESHOLD))
        except (ValueError, TypeError):
            return self.DEFAULT_PASS_THRESHOLD

    def _load_knowledge(self) -> str:
        """加载贷后多轮知识库"""
        try:
            with open(self.kb_path, 'r', encoding='utf-8') as f:
                content = f.read()
            log.info(f"【PostloanMultiTurn】知识库加载成功：{self.kb_path}")
            return content
        except FileNotFoundError:
            log.warning(f"【PostloanMultiTurn】知识库未找到：{self.kb_path}")
            return "贷后催收多轮对话评估通用规则"

    def build_prompt(self, data: List[dict]) -> str:
        """
        构建贷后多轮批量评估 Prompt

        :param data: 每个元素是一个多轮 case（包含完整的 rounds 对话数据）
        """
        knowledge = self._load_knowledge()

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
                        "A": {"score": 80, "pass": True, "reason": "模型正确引用了前文的逾期金额"},
                        "B": {"score": 70, "pass": False, "reason": "模型未正确识别从催收到协商的意图转移"},
                        "C": {"score": 90, "pass": True, "reason": "切换话题后未混入旧话题信息"},
                        "D": {"score": 100, "pass": True, "reason": "话术合规，无违禁词"},
                        "E": {"score": 80, "pass": True, "reason": "安抚话术到位"},
                        "F": {"score": 75, "pass": False, "reason": "第2轮到第3轮衔接生硬"},
                        "G": {"score": 85, "pass": True, "reason": "逾期金额前后一致"}
                    },
                    "round_evals": [
                        {"round": 1, "score": 80, "pass": True, "reason": "回答正确"},
                        {"round": 2, "score": 65, "pass": False, "reason": "意图转移未正确识别"},
                        {"round": 3, "score": 70, "pass": False, "reason": "上下文记忆缺失"}
                    ],
                    "failure_reason": "意图转移问题和上下文记忆问题",
                    "fix_suggestion": "应在回复中确认用户的还款意向，并携带上下文信息"
                }
                for case in data
            ]
        }

        return f"""你是一个贷后催收话术质量评估专家。请基于以下领域知识，评估以下多轮对话的整体质量。

【领域知识】
{knowledge}

【评估维度】（每个维度满分100，加权计算总分）

维度A-上下文记忆（权重25%）：
  评估模型是否记住了前文的关键信息（如逾期金额、还款计划、已承诺时间、用户困难原因）。
  评分标准：
  - 100分：所有前文关键信息均被正确引用，没有遗漏
  - 80-99分：大部分关键信息被引用，个别遗漏但不影响核心理解
  - 60-79分：部分关键信息遗漏或错误引用，影响回答质量
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

维度D-催收合规底线坚守（权重15%）：
  评估催收话术是否触碰合规红线（威胁、恐吓、辱骂、泄露、越权承诺等）。
  评分标准：
  - 100分：话术完全合规，无违禁词，语气专业且尊重
  - 80-99分：话术基本合规，个别措辞可优化
  - 60-79分：存在轻微违规用语（如施压过强）
  - <60分：存在严重违规用语（如威胁、恐吓）

维度E-情绪安抚与客诉控制（权重10%）：
  评估用户情绪升级时，模型是否共情安抚+引导下一步方案。
  评分标准：
  - 100分：安抚到位，话术共情且专业，引导明确
  - 80-99分：安抚基本到位，但共情深度或引导不够明确
  - 60-79分：安抚不足，或没有引导转人工/下一步方案
  - <60分：没有安抚，直接处理用户问题或催收

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
5. 特别关注维度D（催收合规），触碰红线应大幅扣分

【待评估多轮对话】
共 {len(data)} 个 case：

{chr(10).join(case_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    def parse_result(self, text: str, data: List[dict]) -> List[dict]:
        """解析贷后多轮批量评估结果"""
        try:
            # 提取 JSON（多层回退）
            result = None
            # 第1层：直接解析
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                # 第2层：从文本中提取 {...} 块
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass

            # 第3层：尝试修复常见 JSON 截断问题（缺少结尾括号等）
            if result is None:
                fixed_text = text.strip()
                # 移除 markdown 代码块标记
                fixed_text = re.sub(r'^```(?:json)?\s*', '', fixed_text)
                fixed_text = re.sub(r'\s*```\s*$', '', fixed_text)
                # 尝试补全末尾的括号
                if not fixed_text.endswith('}'):
                    last_brace = fixed_text.rfind('}')
                    if last_brace > 0:
                        candidate = fixed_text[:last_brace + 1]
                        try:
                            result = json.loads(candidate)
                        except json.JSONDecodeError:
                            pass
                if result is None:
                    # 第4层：尝试从严重截断的 JSON 中提取关键字段
                    log.warning(f"【PostloanMultiTurn】JSON 被严重截断，尝试提取关键字段...")
                    try:
                        result = self._extract_from_truncated_json(fixed_text)
                    except Exception as e:
                        log.warning(f"【PostloanMultiTurn】从截断 JSON 提取字段失败：{e}")
                if result is None:
                    log.error(f"【PostloanMultiTurn】无法解析返回结果，原始文本前500字符：{text[:500]}")
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

                # 判断是否通过
                threshold = self._get_pass_threshold()
                model_pass = r.get('overall_pass')
                overall_pass = overall_score >= threshold
                if model_pass is not None and model_pass != overall_pass:
                    log.warning(
                        f"【PostloanMultiTurn】模型返回的 overall_pass({model_pass}) "
                        f"与分数计算的通过状态({overall_pass}, score={overall_score})不一致，"
                        f"以分数计算结果为准"
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

                # 催收合规性检查
                compliance_result = self._check_compliance(case)

                parsed_results.append({
                    'case_id': case_id,
                    'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
                    'case_desc': case.get('case_desc', ''),
                    'intent': case.get('intent', ''),
                    'overall_score': overall_score,
                    'overall_pass': overall_pass,
                    'dimension_scores': parsed_dimensions,
                    'round_evals': parsed_rounds,
                    'compliance_result': compliance_result,
                    'failure_reason': r.get('failure_reason', ''),
                    'fix_suggestion': r.get('fix_suggestion', ''),
                    'threshold': threshold,
                    'evaluated': True,
                    'error': None,
                })

            return parsed_results

        except Exception as e:
            log.error(f"【PostloanMultiTurn】解析结果失败：{e}")
            return self._build_fallback_results(data, str(e))

    def _extract_from_truncated_json(self, text: str) -> dict:
        """
        第4层修复：从严重截断的 JSON 中提取关键字段

        当模型返回的 JSON 被严重截断（如缺少完整的结构）时，
        尝试使用正则表达式提取关键字段，构建一个部分解析的结果。

        :param text: 截断的 JSON 文本
        :return: 包含提取字段的字典
        """
        import re

        # 尝试提取 results 数组
        results = []

        # 提取 results 数组的开始位置
        results_start = re.search(r'"results"\s*:\s*\[', text)
        if not results_start:
            return None

        # 提取 results 数组内容
        results_text = text[results_start.end():]

        # 尝试提取每个 case 对象（支持不完整的 case）
        # 匹配模式：从 { 开始，到下一个 { 或 ] 或文本结束
        case_pattern = r'\{(.*?(?=\{|$))'
        case_matches = re.findall(case_pattern, results_text, re.DOTALL)

        for case_text in case_matches:
            # 提取关键字段
            case_id_match = re.search(r'"case_id"\s*:\s*"([^"]*)"', case_text)
            if case_id_match:
                overall_score_match = re.search(r'"overall_score"\s*:\s*(\d+)', case_text)
                overall_pass_match = re.search(r'"overall_pass"\s*:\s*(true|false)', case_text, re.IGNORECASE)
                failure_reason_match = re.search(r'"failure_reason"\s*:\s*"([^"]*)"', case_text)
                fix_suggestion_match = re.search(r'"fix_suggestion"\s*:\s*"([^"]*)"', case_text)

                case_result = {
                    'case_id': case_id_match.group(1),
                    'overall_score': int(overall_score_match.group(1)) if overall_score_match else 0,
                    'overall_pass': overall_pass_match.group(1).lower() == 'true' if overall_pass_match else False,
                    'dimension_scores': {},
                    'round_evals': [],
                    'failure_reason': failure_reason_match.group(1) if failure_reason_match else '',
                    'fix_suggestion': fix_suggestion_match.group(1) if fix_suggestion_match else '',
                }
                results.append(case_result)

        if results:
            log.info(f"【PostloanMultiTurn】从截断 JSON 中提取了 {len(results)} 个 case 的部分字段")
            return {'results': results}

        return None

    def _check_compliance(self, case: dict) -> dict:
        """检查整个 case 的催收合规性"""
        rounds = case.get('rounds', [])
        all_violations = []
        round_compliance = []

        for round_data in rounds:
            actual = round_data.get('actual_answer', '')
            result = check_collection_compliance(actual)
            if not result['is_pass']:
                all_violations.extend(result['violation_keywords'])
            round_compliance.append({
                'round': round_data.get('round', '?'),
                'is_pass': result['is_pass'],
                'violation_count': result['violation_count'],
            })

        return {
            'is_pass': len(all_violations) == 0,
            'violation_keywords': list(set(all_violations)),
            'total_violation_count': len(all_violations),
            'round_compliance': round_compliance,
        }

    def _build_fallback_results(self, chunk: List[dict], error: str) -> List[dict]:
        """构建多轮失败回退结果"""
        return [
            {
                'case_id': case.get('case_id', ''),
                'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
                'case_desc': case.get('case_desc', ''),
                'intent': case.get('intent', ''),
                'overall_score': 0,
                'overall_pass': False,
                'dimension_scores': {},
                'round_evals': [],
                'compliance_result': {'is_pass': False, 'violation_keywords': [], 'detail': f'批量评估失败：{error}'},
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


# ============================================================
# 贷后多轮单条评估器（非批量模式用）
# ============================================================

class PostloanMultiTurnEvaluator:
    """
    贷后多轮对话单条评估器

    与 MultiTurnEvaluator 完全解耦，独立维护
    """

    # 7维度权重（与信贷保持一致）
    DIMENSION_WEIGHTS = {
        'A': 25, 'B': 20, 'C': 15, 'D': 15, 'E': 10, 'F': 10, 'G': 5,
    }

    # 维度名称映射（催收场景语义）
    DIMENSION_NAMES = {
        'A': '上下文记忆',
        'B': '意图转移应对',
        'C': '上下文污染检测',
        'D': '催收合规底线坚守',
        'E': '情绪安抚与客诉控制',
        'F': '对话连贯性',
        'G': '信息一致性',
    }

    # 默认知识库路径
    DEFAULT_KB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'config', 'postloan_multi_turn_knowledge_base.yaml'
    )

    @classmethod
    def evaluate_single(cls, case: dict, judge: ExternalModelJudge) -> dict:
        """
        评估单个贷后多轮对话 case

        :param case: 包含 rounds 的 case 数据
        :param judge: ExternalModelJudge 实例
        :return: 评估结果
        """
        # 1. 外部模型评估（7维度，贷后知识库）
        prompt = cls._build_prompt([case])
        try:
            text = judge.model.chat(
                prompt,
                desc="【PostloanMultiTurnEvaluator】",
                max_tokens=8192,
            )
            results = cls._parse_result(text, [case])
            if results:
                result = results[0]
            else:
                result = cls._build_fallback_result(case, "解析结果为空")
        except Exception as e:
            log.error(f"【PostloanMultiTurnEvaluator】评估失败：{e}")
            result = cls._build_fallback_result(case, str(e))

        # 2. 本地规则断言（ASSET + 转人工 + 催收合规）
        local_assert = cls.evaluate_local_rules(case)
        result['transfer_pass'] = local_assert['transfer_pass']
        result['transfer_reason'] = local_assert['transfer_reason']
        result['asset_pass'] = local_assert['asset_pass']
        result['asset_reason'] = local_assert['asset_reason']
        result['compliance_pass'] = local_assert['compliance_pass']
        result['compliance_reason'] = local_assert['compliance_reason']
        result['per_round_asserts'] = local_assert.get('per_round_asserts', [])

        # 3. 最终通过条件（外部模型通过 AND 本地断言通过 AND 合规通过）
        result['overall_pass'] = (
            result['overall_pass'] and
            local_assert['transfer_pass'] and
            local_assert['asset_pass'] and
            local_assert['compliance_pass']
        )

        return result

    @classmethod
    def evaluate_local_rules(cls, case: dict) -> dict:
        """
        执行本地规则断言（ASSET + 转人工 + 催收合规）

        支持两种模式：
        1. 逐轮检查（默认）：收集每一轮的 output_data，逐轮断言
        2. 只检查最后一轮（兼容旧逻辑）
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

        # 如果没有逐轮数据，回退到旧逻辑
        if not round_outputs or not per_round:
            return cls._evaluate_single_round(case_intent, last_output_data)

        # 逐轮检查
        transfer_round_results = []
        asset_round_results = []
        compliance_round_results = []
        per_round_asserts = []
        total_rounds = len(round_outputs)

        for round_data in round_outputs:
            round_no = round_data.get('round', '?')
            output_data = round_data.get('output_data')
            round_intent = round_data.get('round_intent', '')

            if not output_data:
                continue

            # 提取 reply_info
            try:
                reply_info = PostloanIntentAssert._extract_reply_contents(output_data=output_data)
            except Exception:
                reply_info = {}

            # 使用每轮的实际意图（模型返回的意图）
            # 如果模型返回的意图为空，优先回退到 round_intent（该轮期望意图），
            # 而不是 case_intent（case 级别整体意图），因为多轮对话中每轮意图可能不同
            actual_intent = PostloanIntentAssert.extract_model_intent(output_data=output_data)
            intent = actual_intent if actual_intent else (round_intent if round_intent else case_intent)

            # 提取实际话术文本
            actual_answer = ''
            if isinstance(output_data, dict):
                data = output_data.get('data', {})
                reply_contents = data.get('replyContents', [])
                texts = [item.get('value', '') for item in reply_contents if item.get('type') == 'TEXT']
                actual_answer = ' '.join(texts)

            round_assert = {
                'round': round_no,
                'transfer_pass': True,
                'asset_pass': True,
                'compliance_pass': True,
                'transfer_reason': '',
                'asset_reason': '',
                'compliance_reason': '',
                'has_transfer_assert': False,
                'has_asset_assert': False,
                'has_compliance_assert': False,
            }

            # 1. 转人工断言（所有用例都执行）
            try:
                chat_type_eval = PostloanIntentAssert._evaluate_chat_type_result(intent, reply_info)
                chat_type = chat_type_eval.get('chat_type', 'NORMAL')
                if chat_type == 'TRANSFER':
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
                pass

            # 2. ASSET断言（转人工用例跳过）
            if chat_type != 'TRANSFER':
                try:
                    asset_eval = PostloanIntentAssert.evaluate_asset_result(intent, reply_info)
                    if asset_eval.get('asset_present'):
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
                    pass

            # 3. 催收合规性断言（转人工用例跳过）
            if actual_answer and chat_type != 'TRANSFER':
                round_assert['has_compliance_assert'] = True
                compliance_result = check_collection_compliance(actual_answer)
                if not compliance_result['is_pass']:
                    compliance_round_results.append({
                        'round': round_no,
                        'reason': compliance_result['detail'],
                        'violations': compliance_result['violation_keywords'],
                    })
                    round_assert['compliance_pass'] = False
                    round_assert['compliance_reason'] = compliance_result['detail']

            per_round_asserts.append(round_assert)

        # 判断整体是否通过
        transfer_fail_count = len(transfer_round_results)
        asset_fail_count = len(asset_round_results)
        compliance_fail_count = len(compliance_round_results)

        if strict_mode:
            overall_transfer_pass = transfer_fail_count == 0
            overall_asset_pass = asset_fail_count == 0
            overall_compliance_pass = compliance_fail_count == 0
        else:
            transfer_fail_ratio = transfer_fail_count / total_rounds if total_rounds > 0 else 0
            asset_fail_ratio = asset_fail_count / total_rounds if total_rounds > 0 else 0
            compliance_fail_ratio = compliance_fail_count / total_rounds if total_rounds > 0 else 0
            overall_transfer_pass = transfer_fail_ratio <= max_fail_ratio
            overall_asset_pass = asset_fail_ratio <= max_fail_ratio
            overall_compliance_pass = compliance_fail_ratio <= max_fail_ratio

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

        if overall_compliance_pass:
            compliance_reason = f'通过（共{total_rounds}轮）'
        else:
            fail_details = '; '.join([f"第{r['round']}轮({r['reason']})" for r in compliance_round_results])
            compliance_reason = f"失败: {fail_details}"

        return {
            'transfer_pass': overall_transfer_pass,
            'transfer_reason': transfer_reason,
            'asset_pass': overall_asset_pass,
            'asset_reason': asset_reason,
            'compliance_pass': overall_compliance_pass,
            'compliance_reason': compliance_reason,
            'per_round_asserts': per_round_asserts,
        }

    @classmethod
    def _evaluate_single_round(cls, case_intent: str, last_output_data) -> dict:
        """旧逻辑：只检查最后一轮（兼容模式）"""
        from assert_code.model_intent_assert import ModelIntentAssert
        from assert_code.postloan_intent_assert import PostloanIntentAssert

        if not last_output_data:
            return {
                'transfer_pass': True,
                'transfer_reason': '无模型返回数据，跳过本地断言',
                'asset_pass': True,
                'asset_reason': '无模型返回数据，跳过本地断言',
                'compliance_pass': True,
                'compliance_reason': '无模型返回数据，跳过本地断言',
            }

        # 提取 reply_info
        try:
            reply_info = PostloanIntentAssert._extract_reply_contents(output_data=last_output_data)
        except Exception:
            reply_info = {}

        # 从最后一轮实际返回中提取意图
        actual_intent = PostloanIntentAssert.extract_model_intent(output_data=last_output_data)
        intent = actual_intent if actual_intent else case_intent

        # 提取实际话术文本
        actual_answer = ''
        if isinstance(last_output_data, dict):
            data = last_output_data.get('data', {})
            reply_contents = data.get('replyContents', [])
            texts = [item.get('value', '') for item in reply_contents if item.get('type') == 'TEXT']
            actual_answer = ' '.join(texts)

        # 1. 转人工断言（所有用例都执行）
        try:
            chat_type_eval = PostloanIntentAssert._evaluate_chat_type_result(intent, reply_info)
            transfer_pass = chat_type_eval['chat_type_pass']
            if transfer_pass:
                transfer_reason = 'chatType符合预期'
            else:
                expected = 'TRANSFER' if chat_type_eval['is_transfer'] else 'NORMAL'
                transfer_reason = f"chatType={chat_type_eval['chat_type']}，期望{expected}"
        except Exception as e:
            transfer_pass = True
            transfer_reason = f'转人工断言执行异常：{e}'

        # 2. ASSET断言（转人工用例跳过）
        if chat_type_eval.get('chat_type') != 'TRANSFER':
            try:
                asset_eval = PostloanIntentAssert.evaluate_asset_result(intent, reply_info)
                asset_pass = asset_eval['asset_pass']
                if asset_pass:
                    asset_reason = 'ASSET符合预期'
                else:
                    failures = asset_eval.get('asset_failure_reasons', [])
                    asset_reason = f"ASSET断言失败：{', '.join(failures)}" if failures else 'ASSET断言失败'
            except Exception as e:
                asset_pass = True
                asset_reason = f'ASSET断言执行异常：{e}'
        else:
            asset_pass = True
            asset_reason = '转人工用例跳过ASSET断言'

        # 3. 催收合规性断言（转人工用例跳过）
        if chat_type_eval.get('chat_type') != 'TRANSFER':
            compliance_result = check_collection_compliance(actual_answer)
            compliance_pass = compliance_result['is_pass']
            compliance_reason = compliance_result['detail'] if not compliance_pass else '催收话术合规'
        else:
            compliance_pass = True
            compliance_reason = '转人工用例跳过合规性断言'

        return {
            'transfer_pass': transfer_pass,
            'transfer_reason': transfer_reason,
            'asset_pass': asset_pass,
            'asset_reason': asset_reason,
            'compliance_pass': compliance_pass,
            'compliance_reason': compliance_reason,
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
                        "A": {"score": 80, "pass": True, "reason": "模型正确引用了前文的逾期金额"},
                        "B": {"score": 70, "pass": False, "reason": "模型未正确识别从催收到协商的意图转移"},
                        "C": {"score": 90, "pass": True, "reason": "切换话题后未混入旧话题信息"},
                        "D": {"score": 100, "pass": True, "reason": "话术合规，无违禁词"},
                        "E": {"score": 80, "pass": True, "reason": "安抚话术到位"},
                        "F": {"score": 75, "pass": False, "reason": "第2轮到第3轮衔接生硬"},
                        "G": {"score": 85, "pass": True, "reason": "逾期金额前后一致"}
                    },
                    "round_evals": [
                        {"round": 1, "score": 80, "pass": True, "reason": "回答正确"},
                        {"round": 2, "score": 65, "pass": False, "reason": "意图转移未正确识别"},
                        {"round": 3, "score": 70, "pass": False, "reason": "上下文记忆缺失"}
                    ],
                    "failure_reason": "意图转移问题和上下文记忆问题",
                    "fix_suggestion": "应在回复中确认用户的还款意向，并携带上下文信息"
                }
                for case in data
            ]
        }

        return f"""你是一个贷后催收话术质量评估专家。请基于以下领域知识，评估以下多轮对话的整体质量。

【领域知识】
{knowledge}

【评估维度】（每个维度满分100，加权计算总分）

维度A-上下文记忆（权重25%）：
  评估模型是否记住了前文的关键信息（如逾期金额、还款计划、已承诺时间、用户困难原因）。
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

维度D-催收合规底线坚守（权重15%）：
  评估催收话术是否触碰合规红线（威胁、恐吓、辱骂、泄露、越权承诺等）。
  评分标准：
  - 100分：话术完全合规，无违禁词
  - 80-99分：话术基本合规，个别措辞可优化
  - 60-79分：存在轻微违规用语
  - <60分：存在严重违规用语

维度E-情绪安抚与客诉控制（权重10%）：
  评估用户情绪升级时，模型是否共情安抚+引导下一步方案。
  评分标准：
  - 100分：安抚到位，话术共情且专业
  - 80-99分：安抚基本到位，但共情深度或引导不够明确
  - 60-79分：安抚不足
  - <60分：没有安抚，直接处理用户问题

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

                overall_score = r.get('overall_score', 0)
                if isinstance(overall_score, str):
                    try:
                        overall_score = int(overall_score)
                    except (ValueError, TypeError):
                        overall_score = 0
                overall_score = max(0, min(100, int(overall_score)))

                threshold = int(os.getenv('MODEL_POSTLOAN_MULTI_TURN_PASS_THRESHOLD', 70))
                model_pass = r.get('overall_pass')
                overall_pass = overall_score >= threshold
                if model_pass is not None and model_pass != overall_pass:
                    log.warning(
                        f"【PostloanMultiTurnEvaluator】模型返回的 overall_pass({model_pass}) "
                        f"与分数计算的通过状态({overall_pass}, score={overall_score})不一致，"
                        f"以分数计算结果为准"
                    )

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
                    'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
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
            log.error(f"【PostloanMultiTurnEvaluator】解析结果失败：{e}")
            return [cls._build_fallback_result(case, str(e)) for case in data]

    @classmethod
    def _build_fallback_result(cls, case: dict, error: str) -> dict:
        """构建失败回退结果"""
        return {
            'case_id': case.get('case_id', ''),
            'case_type': TestConfig.CASE_TYPE_POSTLOAN_MULTI_TURN,
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
            'compliance_pass': False,
            'compliance_reason': f'评估失败：{error}',
            'failure_reason': f"评估失败：{error}",
            'fix_suggestion': '',
            'threshold': 70,
            'evaluated': True,
            'error': error,
        }

    @classmethod
    def _load_multi_turn_knowledge(cls) -> str:
        """加载多轮对话评估知识库"""
        kb_path = cls.DEFAULT_KB_PATH
        try:
            with open(kb_path, 'r', encoding='utf-8') as f:
                content = f.read()
            log.info(f"【PostloanMultiTurnEvaluator】知识库加载成功：{kb_path}")
            return content
        except FileNotFoundError:
            log.warning(f"【PostloanMultiTurnEvaluator】多轮知识库未找到：{kb_path}")
            return "贷后催收多轮对话评估通用规则"


# ============================================================
# 快捷函数
# ============================================================

def postloan_multi_turn_evaluate_single(
    case: dict,
    *,
    model_name: str = 'deepseek-v4-pro',
) -> dict:
    """
    快捷函数：评估单个贷后多轮对话 case

    :param case: 包含 rounds 的 case 数据
    :param model_name: 外部模型名称
    :return: 评估结果
    """
    judge = ExternalModelJudge(
        model_name=model_name,
        use_knowledge_base=False,
    )
    return PostloanMultiTurnEvaluator.evaluate_single(case, judge)
