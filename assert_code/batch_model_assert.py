# -*- coding: utf-8 -*-
"""
批量模型断言器

作用：
    一次性注入知识库，批量评估多条测试数据。

设计：
    - 初始化时注入知识库（只注入一次）
    - 按意图分组，每组构建一个大的批量评估 prompt
    - 一次 API 调用评估多条数据
    - 解析返回结果，生成报告行

使用方式：
    from assert_code.batch_model_assert import BatchModelAssert

    batch = BatchModelAssert()
    results = batch.batch_evaluate(items)

    # items 格式（由 BatchAssertCollector 收集）：
    # [
    #     {
    #         'case_id': 'MIR_0001',
    #         'case_type': 'single_turn',
    #         'intent': '提额降息咨询类',
    #         'question': '我想申请提额',
    #         'actual_answer': '...',
    #         'expected_answer': '...',
    #         'similarity_threshold': 70,
    #         'response_time': 1.23,
    #     },
    #     ...
    # ]
"""

import json
import os
from typing import List, Dict, Optional
from collections import defaultdict

from assert_code.external_model_judge import ExternalModelJudge
from assert_code.model_intent_assert import ModelIntentAssert
from assert_code.batch_assert_strategies import SingleTurnBatchStrategy, MultiTurnBatchStrategy
from utils.handle_log import log


class BatchModelAssert:
    """
    批量模型断言器
    """

    def __init__(self, model_name: str = 'deepseek-v4-pro', max_group_size: int = 10,
                 max_group_size_multi: int = 2):
        """
        初始化批量断言器（一次性注入知识库）

        :param model_name: 外部模型名称
        :param max_group_size: 单轮每组最大用例数（控制 prompt 长度）
        :param max_group_size_multi: 多轮每组最大用例数（多轮 prompt 较长，建议设小）
        """
        self.max_group_size = max_group_size
        self.max_group_size_multi = max_group_size_multi
        # 初始化 ExternalModelJudge（注入知识库，只注入一次）
        self.judge = ExternalModelJudge(
            model_name=model_name,
            use_knowledge_base=True,
            inject_knowledge_as_system=True,
        )
        log.info("【批量断言】BatchModelAssert 初始化完成，知识库已注入")

    def batch_evaluate(self, items: List[dict]) -> List[dict]:
        """
        批量评估入口

        按 case_type 分发到不同的策略：
        - single_turn: 单轮批量评估（语义相似度）
        - multi_turn: 多轮批量评估（7个维度）

        :param items: 待评估数据列表
        :return: 评估结果列表
        """
        if not items:
            log.info("【批量断言】无待评估数据")
            return []

        log.info(f"【批量断言】开始批量评估，共 {len(items)} 条数据")

        # 按 case_type 分组
        single_turn_items = [item for item in items if item.get('case_type') == 'single_turn']
        multi_turn_items = [item for item in items if item.get('case_type') == 'multi_turn']

        results = []

        # 单轮：使用 SingleTurnBatchStrategy
        if single_turn_items:
            log.info(f"【批量断言】单轮数据 {len(single_turn_items)} 条，使用 SingleTurnBatchStrategy")
            single_strategy = SingleTurnBatchStrategy(self.judge, self.max_group_size)
            # 按意图分组（单轮策略内部处理）
            single_results = single_strategy.evaluate(single_turn_items)
            results.extend(single_results)
            log.info(f"【批量断言】单轮评估完成：{len(single_results)} 条结果")

        # 多轮：使用 MultiTurnBatchStrategy（使用单独的多轮组大小）
        if multi_turn_items:
            log.info(f"【批量断言】多轮数据 {len(multi_turn_items)} 条，使用 MultiTurnBatchStrategy，每组大小 {self.max_group_size_multi}")
            multi_strategy = MultiTurnBatchStrategy(self.judge, self.max_group_size_multi)
            multi_results = multi_strategy.evaluate(multi_turn_items)
            results.extend(multi_results)
            log.info(f"【批量断言】多轮评估完成：{len(multi_results)} 条结果")

        log.info(f"【批量断言】批量评估完成，共 {len(results)} 条结果")
        return results

    @staticmethod
    def _group_by_intent(items: List[dict]) -> Dict[str, List[dict]]:
        """按意图分组"""
        grouped = defaultdict(list)
        for item in items:
            intent = item.get('intent', 'unknown')
            grouped[intent].append(item)
        return grouped

    def _evaluate_chunk(self, intent: str, chunk_items: List[dict]) -> List[dict]:
        """
        评估一批数据（同一意图）

        :param intent: 意图分类
        :param chunk_items: 一批数据
        :return: 评估结果列表
        """
        # 构建批量评估 prompt
        prompt = self._build_batch_prompt(intent, chunk_items)

        try:
            # 调用外部模型（一次性评估多条）
            log.info(f"【批量断言】发送批量评估请求，意图[{intent}]，{len(chunk_items)} 条")
            max_tokens = getattr(self.judge, 'max_tokens', 8192)
            text = self.judge.model.chat(
                prompt,
                desc=f"【批量断言】意图[{intent}]",
                max_tokens=max_tokens,
            )

            # 解析返回结果
            results = self._parse_batch_result(text, chunk_items)
            return results
        except Exception as e:
            log.error(f"【批量断言】批量评估失败（意图[{intent}]）：{e}")
            # 返回失败结果
            return [
                {
                    'case_id': item.get('case_id', ''),
                    'intent': intent,
                    'similarity_score': 0,
                    'is_pass': False,
                    'reason': f"批量评估失败：{e}",
                    'evaluated': True,
                    'error': str(e),
                }
                for item in chunk_items
            ]

    def _build_batch_prompt(self, intent: str, items: List[dict]) -> str:
        """
        构建批量评估 prompt

        :param intent: 意图分类
        :param items: 待评估数据列表
        :return: 批量评估 prompt
        """
        # 获取该意图的知识库内容
        knowledge = ""
        kb_loaded = False
        if self.judge.knowledge_base:
            knowledge = self.judge.knowledge_base.get_intent_rules(intent)
            kb_loaded = True

        # 打印知识库携带状态（显性日志，只展示是否加载，不展示内容）
        if kb_loaded and knowledge:
            log.info(f"【批量断言】意图[{intent}] - 已加载知识库 ✓")
        elif kb_loaded:
            log.warning(f"【批量断言】意图[{intent}] - 知识库已加载但无内容（该意图未配置规则）")
        else:
            log.warning(f"【批量断言】意图[{intent}] - 未加载知识库（knowledge_base=None）")

        # 构建数据条目
        data_lines = []
        for idx, item in enumerate(items):
            data_lines.append(f"### 数据 {idx + 1}")
            data_lines.append(f"- case_id: {item.get('case_id', '')}")
            data_lines.append(f"- 用户问题: {item.get('question', '')}")
            data_lines.append(f"- 标准答案: {item.get('expected_answer', '')}")
            data_lines.append(f"- 实际回复: {item.get('actual_answer', '')}")
            data_lines.append(f"- 相似度阈值: {item.get('similarity_threshold', 70)}")
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
                for item in items
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
共 {len(items)} 条：

{chr(10).join(data_lines)}

【返回要求】
只返回 JSON，不要返回 markdown，不要返回额外解释。
JSON 格式如下：
{json.dumps(json_example, ensure_ascii=False, indent=2)}
"""

    @staticmethod
    def _parse_batch_result(text: str, items: List[dict]) -> List[dict]:
        """
        解析批量评估返回结果

        :param text: 外部模型返回的文本
        :param items: 原始数据（用于映射 case_id）
        :return: 评估结果列表
        """
        try:
            # 提取 JSON
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                import re
                json_match = re.search(r'\{.*\}', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    raise ValueError(f"无法解析返回结果: {text[:200]}...")

            # 提取 results
            results = result.get('results', [])
            if not results:
                raise ValueError("返回结果中缺少 'results' 字段")

            # 按 case_id 映射，同时保留原始顺序
            results_by_case_id = {r.get('case_id'): r for r in results if r.get('case_id')}

            parsed_results = []
            for idx, item in enumerate(items):
                case_id = item.get('case_id', '')
                # 优先按 case_id 映射，如果找不到则按索引回退
                r = results_by_case_id.get(case_id, {})
                if not r and idx < len(results):
                    # 按索引回退
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
                    # 保留本地断言字段（用于HTML报告展示和合并）
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
            log.error(f"【批量断言】解析批量评估结果失败：{e}，原始文本：{text[:500]}")
            # 返回失败结果
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
                    'reason': f"解析结果失败：{e}",
                    'evaluated': True,
                    'error': str(e),
                }
                for item in items
            ]

    def generate_report(
        self,
        original_items: List[dict],
        results: List[dict],
        output_dir: str = None,
    ) -> dict:
        """
        生成批量断言报告（CSV + HTML）

        :param original_items: 原始数据
        :param results: 评估结果
        :param output_dir: 报告输出目录
        :return: 报告摘要字典
        """
        total = len(results)
        pass_count = sum(1 for r in results if r.get('is_pass'))
        fail_count = total - pass_count
        pass_rate = round(pass_count / total * 100, 2) if total else 0

        # 失败用例
        failed_items = [r for r in results if not r.get('is_pass')]

        summary = {
            'total': total,
            'pass_count': pass_count,
            'failed_count': fail_count,
            'pass_rate': f'{pass_rate}%',
            'failed_case_ids': [r.get('case_id') for r in failed_items],
            'failed_items': failed_items,
        }

        # 生成报告（CSV + HTML）
        if output_dir:
            import csv
            import datetime
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')

            # 详细结果 CSV
            detail_path = os.path.join(output_dir, f'batch_assert_detail_{timestamp}.csv')
            with open(detail_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'case_id', 'case_type', 'case_desc', 'intent', 'question',
                    'expected_answer', 'actual_answer', 'similarity_score',
                    'similarity_threshold', 'is_pass', 'reason'
                ])
                writer.writeheader()
                for r in results:
                    writer.writerow({
                        'case_id': r.get('case_id', ''),
                        'case_type': r.get('case_type', ''),
                        'case_desc': r.get('case_desc', ''),
                        'intent': r.get('intent', ''),
                        'question': r.get('question', ''),
                        'expected_answer': r.get('expected_answer', ''),
                        'actual_answer': r.get('actual_answer', ''),
                        'similarity_score': r.get('similarity_score', 0),
                        'similarity_threshold': r.get('similarity_threshold', 70),
                        'is_pass': '通过' if r.get('is_pass') else '失败',
                        'reason': r.get('reason', ''),
                    })

            # 失败用例 CSV
            if failed_items:
                failed_path = os.path.join(output_dir, f'batch_assert_failed_{timestamp}.csv')
                with open(failed_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'case_id', 'case_type', 'intent', 'question',
                        'expected_answer', 'actual_answer', 'similarity_score', 'reason'
                    ])
                    writer.writeheader()
                    for r in failed_items:
                        writer.writerow({
                            'case_id': r.get('case_id', ''),
                            'case_type': r.get('case_type', ''),
                            'intent': r.get('intent', ''),
                            'question': r.get('question', ''),
                            'expected_answer': r.get('expected_answer', ''),
                            'actual_answer': r.get('actual_answer', ''),
                            'similarity_score': r.get('similarity_score', 0),
                            'reason': r.get('reason', ''),
                        })

            # 生成 HTML 报告（Allure 自定义报告页）
            html_path = self._generate_html_report(results, summary, output_dir, timestamp)
            summary['html_path'] = html_path
            summary['detail_path'] = detail_path

        log.info(f"【批量断言】报告生成完成：通过 {pass_count} / 失败 {fail_count} / 总计 {total}，通过率 {pass_rate}%")
        return summary

    def _generate_html_report(self, results: List[dict], summary: dict, output_dir: str, timestamp: str) -> str:
        """
        生成批量断言 HTML 报告

        :param results: 评估结果列表
        :param summary: 报告摘要
        :param output_dir: 输出目录
        :param timestamp: 时间戳
        :return: HTML 文件路径
        """
        import datetime

        total = summary['total']
        pass_count = summary['pass_count']
        fail_count = summary['failed_count']
        pass_rate = summary['pass_rate']
        failed_items = summary.get('failed_items', [])

        # 评分分布（按分数段统计）
        score_ranges = {
            '100': 0,
            '80-99': 0,
            '60-79': 0,
            '40-59': 0,
            '20-39': 0,
            '0-19': 0,
        }
        for r in results:
            score = r.get('similarity_score', 0)
            if score == 100:
                score_ranges['100'] += 1
            elif score >= 80:
                score_ranges['80-99'] += 1
            elif score >= 60:
                score_ranges['60-79'] += 1
            elif score >= 40:
                score_ranges['40-59'] += 1
            elif score >= 20:
                score_ranges['20-39'] += 1
            else:
                score_ranges['0-19'] += 1

        # 生成评分分布条形图（HTML）
        score_bars = []
        for range_label, count in score_ranges.items():
            if count > 0:
                width = (count / total * 100) if total else 0
                score_bars.append(
                    f'<div class="score-bar">'
                    f'  <div class="score-bar-label">{range_label}分</div>'
                    f'  <div class="score-bar-track">'
                    f'    <div class="score-bar-fill" style="width: {width:.1f}%">{count}</div>'
                    f'  </div>'
                    f'</div>'
                )

        # 失败用例表格行
        failed_rows = []
        for r in failed_items:
            actual_answer = r.get("actual_answer", "")
            expected_answer = r.get("expected_answer", "")
            local_assert_text = self._build_local_assert_text(r.get('local_assert_detail', {}))
            failed_rows.append(
                f'<tr>'
                f'  <td>{r.get("case_id", "")}</td>'
                f'  <td>{r.get("intent", "")}</td>'
                f'  <td>{r.get("question", "")}</td>'
                f'  <td class="score-fail">{r.get("similarity_score", 0)}</td>'
                f'  <td>{local_assert_text}</td>'
                f'  <td title="{self._escape_html(actual_answer)}">{self._truncate_text(actual_answer, 50)}</td>'
                f'  <td title="{self._escape_html(expected_answer)}">{self._truncate_text(expected_answer, 50)}</td>'
                f'  <td>{r.get("reason", "")}</td>'
                f'</tr>'
            )

        # 所有用例表格行
        all_rows = []
        for r in results:
            status_class = 'pass' if r.get('is_pass') else 'fail'
            actual_answer = r.get("actual_answer", "")
            expected_answer = r.get("expected_answer", "")
            local_assert_text = self._build_local_assert_text(r.get('local_assert_detail', {}))
            all_rows.append(
                f'<tr>'
                f'  <td>{r.get("case_id", "")}</td>'
                f'  <td>{r.get("intent", "")}</td>'
                f'  <td>{r.get("question", "")}</td>'
                f'  <td class="score-{status_class}">{r.get("similarity_score", 0)}</td>'
                f'  <td><span class="badge-{status_class}">{"通过" if r.get("is_pass") else "失败"}</span></td>'
                f'  <td>{local_assert_text}</td>'
                f'  <td title="{self._escape_html(actual_answer)}">{self._truncate_text(actual_answer, 50)}</td>'
                f'  <td title="{self._escape_html(expected_answer)}">{self._truncate_text(expected_answer, 50)}</td>'
                f'  <td>{r.get("reason", "")[:100]}{"..." if len(r.get("reason", "")) > 100 else ""}</td>'
                f'</tr>'
            )

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>批量断言报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f5f7fa; color: #333; line-height: 1.6; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header .subtitle {{ opacity: 0.9; font-size: 14px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
        .stat-card .stat-value {{ font-size: 32px; font-weight: bold; margin: 10px 0; }}
        .stat-card .stat-label {{ font-size: 14px; color: #666; }}
        .stat-card.total .stat-value {{ color: #667eea; }}
        .stat-card.pass .stat-value {{ color: #52c41a; }}
        .stat-card.fail .stat-value {{ color: #f5222d; }}
        .stat-card.rate .stat-value {{ color: #faad14; }}
        .section {{ background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; }}
        .section h2 {{ font-size: 18px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #eee; }}
        .score-distribution {{ display: flex; flex-direction: column; gap: 8px; }}
        .score-bar {{ display: flex; align-items: center; gap: 10px; }}
        .score-bar-label {{ width: 60px; text-align: right; font-size: 13px; color: #666; }}
        .score-bar-track {{ flex: 1; height: 24px; background: #f0f0f0; border-radius: 12px; overflow: hidden; }}
        .score-bar-fill {{ height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); color: white; display: flex; align-items: center; justify-content: center; font-size: 12px; border-radius: 12px; min-width: 30px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; word-wrap: break-word; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #666; }}
        tr:hover {{ background: #f8f9fa; }}
        .score-pass {{ color: #52c41a; font-weight: bold; }}
        .score-fail {{ color: #f5222d; font-weight: bold; }}
        .badge-pass {{ background: #f6ffed; color: #52c41a; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .badge-fail {{ background: #fff1f0; color: #f5222d; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .failed-section {{ border-left: 4px solid #f5222d; }}
        .empty-msg {{ color: #999; text-align: center; padding: 40px; }}
        /* 列宽控制 */
        .col-case-id {{ width: 7%; }}
        .col-intent {{ width: 9%; }}
        .col-question {{ width: 13%; }}
        .col-score {{ width: 5%; }}
        .col-result {{ width: 5%; }}
        .col-local-assert {{ width: 8%; }}
        .col-actual {{ width: 15%; }}
        .col-expected {{ width: 15%; }}
        .col-reason {{ width: 16%; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>批量断言报告</h1>
            <p class="subtitle">生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card total">
                <div class="stat-label">总条数</div>
                <div class="stat-value">{total}</div>
            </div>
            <div class="stat-card pass">
                <div class="stat-label">通过</div>
                <div class="stat-value">{pass_count}</div>
            </div>
            <div class="stat-card fail">
                <div class="stat-label">失败</div>
                <div class="stat-value">{fail_count}</div>
            </div>
            <div class="stat-card rate">
                <div class="stat-label">通过率</div>
                <div class="stat-value">{pass_rate}</div>
            </div>
        </div>

        <div class="section">
            <h2>评分分布</h2>
            <div class="score-distribution">
                {chr(10).join(score_bars) if score_bars else '<div class="empty-msg">暂无数据</div>'}
            </div>
        </div>

        <div class="section failed-section">
            <h2>失败用例（{len(failed_items)} 条）</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th class="col-case-id">用例ID</th>
                            <th class="col-intent">意图</th>
                            <th class="col-question">问题</th>
                            <th class="col-score">评分</th>
                            <th class="col-local-assert">本地断言</th>
                            <th class="col-actual">实际回复</th>
                            <th class="col-expected">标准答案</th>
                            <th class="col-reason">失败原因</th>
                        </tr>
                    </thead>
                    <tbody>
                        {chr(10).join(failed_rows) if failed_rows else '<tr><td colspan="8" class="empty-msg">无失败用例</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>全部用例</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th class="col-case-id">用例ID</th>
                            <th class="col-intent">意图</th>
                            <th class="col-question">问题</th>
                            <th class="col-score">评分</th>
                            <th class="col-result">结果</th>
                            <th class="col-local-assert">本地断言</th>
                            <th class="col-actual">实际回复</th>
                            <th class="col-expected">标准答案</th>
                            <th class="col-reason">原因</th>
                        </tr>
                    </thead>
                    <tbody>
                        {chr(10).join(all_rows)}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>"""

        html_path = os.path.join(output_dir, f'batch_assert_report_{timestamp}.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        log.info(f"【批量断言】HTML 报告已生成：{html_path}")
        return html_path

    def generate_multi_turn_report(
        self,
        original_items: List[dict],
        results: List[dict],
        output_dir: str = None,
    ) -> dict:
        """
        生成多轮对话批量断言报告（CSV + HTML）

        与单轮报告的区别：
        - 展示7个维度的评分
        - 展示逐轮评分
        - 展示完整的真实对话和标准话术
        - 单独的多轮评估报告页

        :param original_items: 原始数据（包含 rounds 完整对话）
        :param results: 评估结果（多轮）
        :param output_dir: 报告输出目录
        :return: 报告摘要字典
        """
        total = len(results)
        pass_count = sum(1 for r in results if r.get('overall_pass'))
        fail_count = total - pass_count
        pass_rate = round(pass_count / total * 100, 2) if total else 0

        # 失败用例
        failed_items = [r for r in results if not r.get('overall_pass')]

        # 构建 case_id -> rounds 的映射（用于展示完整对话）
        case_id_to_rounds = {}
        for item in original_items:
            case_id = item.get('case_id')
            if case_id:
                case_id_to_rounds[case_id] = item.get('rounds', [])

        # 为每个 result 补充本地断言（转人工 + ASSET）
        from assert_code.batch_assert_strategies import MultiTurnEvaluator
        case_id_to_item = {item.get('case_id'): item for item in original_items if item.get('case_id')}
        for r in results:
            case_id = r.get('case_id')
            if case_id and case_id in case_id_to_item:
                item = case_id_to_item[case_id]
                local_assert = MultiTurnEvaluator.evaluate_local_rules(item)
                r['transfer_pass'] = local_assert['transfer_pass']
                r['transfer_reason'] = local_assert['transfer_reason']
                r['asset_pass'] = local_assert['asset_pass']
                r['asset_reason'] = local_assert['asset_reason']
                r['per_round_asserts'] = local_assert.get('per_round_asserts', [])
                # 重新计算 overall_pass（外部模型评估 + 本地断言）
                r['overall_pass'] = (
                    r.get('overall_pass', False) and
                    local_assert['transfer_pass'] and
                    local_assert['asset_pass']
                )

        # 重新计算失败用例（因为可能有新的失败项）
        failed_items = [r for r in results if not r.get('overall_pass')]

        summary = {
            'total': total,
            'pass_count': pass_count,
            'failed_count': fail_count,
            'pass_rate': f'{pass_rate}%',
            'failed_case_ids': [r.get('case_id') for r in failed_items],
            'failed_items': failed_items,
        }

        # 生成报告（CSV + HTML）
        if output_dir:
            import csv
            import datetime
            os.makedirs(output_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')

            # 详细结果 CSV
            detail_path = os.path.join(output_dir, f'batch_assert_multi_turn_detail_{timestamp}.csv')
            with open(detail_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'case_id', 'case_desc', 'intent', 'overall_score', 'overall_pass',
                    'A_score', 'A_pass', 'B_score', 'B_pass', 'C_score', 'C_pass',
                    'D_score', 'D_pass', 'E_score', 'E_pass', 'F_score', 'F_pass',
                    'G_score', 'G_pass', 'transfer_pass', 'asset_pass',
                    'transfer_reason', 'asset_reason',
                    'user_questions', 'actual_answers', 'expected_answers',
                    'failure_reason', 'fix_suggestion'
                ])
                writer.writeheader()
                for r in results:
                    ds = r.get('dimension_scores', {})
                    case_id = r.get('case_id', '')
                    rounds = case_id_to_rounds.get(case_id, [])
                    # 分别构建用户问题、真实应答、标准应答
                    user_questions = self._build_user_questions(rounds)
                    actual_answers = self._build_dialog_text(rounds, 'actual_answer')
                    expected_answers = self._build_dialog_text(rounds, 'expected_answer')
                    writer.writerow({
                        'case_id': case_id,
                        'case_desc': r.get('case_desc', ''),
                        'intent': r.get('intent', ''),
                        'overall_score': r.get('overall_score', 0),
                        'overall_pass': '通过' if r.get('overall_pass') else '失败',
                        'A_score': ds.get('A', {}).get('score', 0),
                        'A_pass': '通过' if ds.get('A', {}).get('pass', False) else '失败',
                        'B_score': ds.get('B', {}).get('score', 0),
                        'B_pass': '通过' if ds.get('B', {}).get('pass', False) else '失败',
                        'C_score': ds.get('C', {}).get('score', 0),
                        'C_pass': '通过' if ds.get('C', {}).get('pass', False) else '失败',
                        'D_score': ds.get('D', {}).get('score', 0),
                        'D_pass': '通过' if ds.get('D', {}).get('pass', False) else '失败',
                        'E_score': ds.get('E', {}).get('score', 0),
                        'E_pass': '通过' if ds.get('E', {}).get('pass', False) else '失败',
                        'F_score': ds.get('F', {}).get('score', 0),
                        'F_pass': '通过' if ds.get('F', {}).get('pass', False) else '失败',
                        'G_score': ds.get('G', {}).get('score', 0),
                        'G_pass': '通过' if ds.get('G', {}).get('pass', False) else '失败',
                        'transfer_pass': '通过' if r.get('transfer_pass') else '失败',
                        'asset_pass': '通过' if r.get('asset_pass') else '失败',
                        'transfer_reason': r.get('transfer_reason', ''),
                        'asset_reason': r.get('asset_reason', ''),
                        'user_questions': user_questions,
                        'actual_answers': actual_answers,
                        'expected_answers': expected_answers,
                        'failure_reason': r.get('failure_reason', ''),
                        'fix_suggestion': r.get('fix_suggestion', ''),
                    })

            # 失败用例 CSV
            if failed_items:
                failed_path = os.path.join(output_dir, f'batch_assert_multi_turn_failed_{timestamp}.csv')
                with open(failed_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        'case_id', 'case_desc', 'intent', 'overall_score',
                        'transfer_pass', 'asset_pass',
                        'transfer_reason', 'asset_reason',
                        'user_questions', 'actual_answers', 'expected_answers',
                        'failure_reason', 'fix_suggestion'
                    ])
                    writer.writeheader()
                    for r in failed_items:
                        case_id = r.get('case_id', '')
                        rounds = case_id_to_rounds.get(case_id, [])
                        user_questions = self._build_user_questions(rounds)
                        actual_answers = self._build_dialog_text(rounds, 'actual_answer')
                        expected_answers = self._build_dialog_text(rounds, 'expected_answer')
                        writer.writerow({
                            'case_id': case_id,
                            'case_desc': r.get('case_desc', ''),
                            'intent': r.get('intent', ''),
                            'overall_score': r.get('overall_score', 0),
                            'transfer_pass': '通过' if r.get('transfer_pass') else '失败',
                            'asset_pass': '通过' if r.get('asset_pass') else '失败',
                            'transfer_reason': r.get('transfer_reason', ''),
                            'asset_reason': r.get('asset_reason', ''),
                            'user_questions': user_questions,
                            'actual_answers': actual_answers,
                            'expected_answers': expected_answers,
                            'failure_reason': r.get('failure_reason', ''),
                            'fix_suggestion': r.get('fix_suggestion', ''),
                        })

            # 生成 HTML 报告（多轮专用）
            html_path = self._generate_multi_turn_html_report(results, summary, original_items, output_dir, timestamp)
            summary['html_path'] = html_path
            summary['detail_path'] = detail_path

        log.info(f"【批量断言】多轮报告生成完成：通过 {pass_count} / 失败 {fail_count} / 总计 {total}，通过率 {pass_rate}%")
        return summary

    @staticmethod
    def _build_user_questions(rounds: list) -> str:
        """合并多轮用户问题"""
        if not rounds:
            return ''
        lines = []
        for round_data in rounds:
            round_no = round_data.get('round', '?')
            question = round_data.get('question', '')
            if question:
                lines.append(f"[第{round_no}轮] {question}")
        return '\n'.join(lines)

    @staticmethod
    def _build_dialog_text(rounds: list, answer_key: str) -> str:
        """合并多轮对话中指定类型的应答内容（如 actual_answer 或 expected_answer）"""
        if not rounds:
            return ''
        lines = []
        for round_data in rounds:
            round_no = round_data.get('round', '?')
            answer = round_data.get(answer_key, '')
            if answer:
                lines.append(f"[第{round_no}轮] {answer}")
        return '\n'.join(lines)

    @staticmethod
    def _build_rounds_html(rounds: list, text_key: str, max_chars: int = 120) -> str:
        """
        将多轮数据格式化为 HTML 展示（用于报告表格中）

        :param rounds: 轮次数据列表
        :param text_key: 要提取的字段名 ('question', 'actual_answer', 'expected_answer')
        :param max_chars: 每轮文本最大显示字符数
        :return: HTML 字符串
        """
        if not rounds:
            return '<span class="empty-msg">—</span>'
        lines = []
        for round_data in rounds:
            round_no = round_data.get('round', '?')
            text = str(round_data.get(text_key, '') or '')
            if not text:
                continue
            # 截断处理，hover 显示完整内容
            display_text = text
            if len(text) > max_chars:
                display_text = text[:max_chars] + '...'
            escaped_text = (display_text
                            .replace('&', '&amp;')
                            .replace('<', '&lt;')
                            .replace('>', '&gt;')
                            .replace('"', '&quot;'))
            full_text = (text
                         .replace('&', '&amp;')
                         .replace('<', '&lt;')
                         .replace('>', '&gt;')
                         .replace('"', '&quot;')
                         .replace('\n', '<br>'))
            lines.append(
                f'<div class="dialog-round">'
                f'<span class="round-label">第{round_no}轮</span>'
                f'<span class="round-text" title="{full_text}">{escaped_text}</span>'
                f'</div>'
            )
        return '\n'.join(lines) if lines else '<span class="empty-msg">—</span>'

    def _generate_multi_turn_html_report(self, results: List[dict], summary: dict, original_items: List[dict], output_dir: str, timestamp: str) -> str:
        """
        生成多轮对话批量断言 HTML 报告

        :param results: 评估结果列表
        :param summary: 报告摘要
        :param original_items: 原始数据（包含完整对话）
        :param output_dir: 输出目录
        :param timestamp: 时间戳
        :return: HTML 文件路径
        """
        import datetime

        total = summary['total']
        pass_count = summary['pass_count']
        fail_count = summary['failed_count']
        pass_rate = summary['pass_rate']
        failed_items = summary.get('failed_items', [])

        # 构建 case_id -> rounds 映射
        case_id_to_rounds = {}
        for item in original_items:
            case_id = item.get('case_id')
            if case_id:
                case_id_to_rounds[case_id] = item.get('rounds', [])

        # 维度名称和权重
        dimensions = {
            'A': ('上下文记忆', 25),
            'B': ('意图转移应对', 20),
            'C': ('上下文污染检测', 15),
            'D': ('合规底线坚守', 15),
            'E': ('客诉控制', 10),
            'F': ('对话连贯性', 10),
            'G': ('信息一致性', 5),
        }

        # ============================================================
        # 生成雷达图
        # ============================================================
        radar_chart_html = ''
        try:
            from utils.handle_plot import draw_radar_chart

            # 计算各维度平均分
            dim_avg_scores = {}
            for key, (name, weight) in dimensions.items():
                scores = []
                for r in results:
                    ds = r.get('dimension_scores', {})
                    dim_data = ds.get(key, {})
                    score = dim_data.get('score', 0)
                    if score:
                        scores.append(score)
                if scores:
                    dim_avg_scores[key] = round(sum(scores) / len(scores), 1)
                else:
                    dim_avg_scores[key] = 0

            # 构建雷达图数据
            radar_data = {
                '当前测试': [dim_avg_scores.get(key, 0) for key in dimensions.keys()]
            }
            radar_categories = [name for name, weight in dimensions.values()]

            # 保存雷达图
            radar_path = os.path.join(output_dir, f'batch_assert_multi_turn_radar_{timestamp}.png')
            draw_radar_chart(
                radar_data,
                radar_categories,
                title="多轮对话各维度评分雷达图",
                save_path=radar_path,
                show=False,
                close_after_save=True,
            )

            # 将图片转为 base64 嵌入 HTML
            import base64
            with open(radar_path, 'rb') as img_file:
                radar_base64 = base64.b64encode(img_file.read()).decode('utf-8')

            radar_chart_html = f'''<div class="section">
    <h2>各维度评分雷达图</h2>
    <div style="text-align: center;">
        <img src="data:image/png;base64,{radar_base64}" style="max-width: 48%; height: auto;" alt="各维度评分雷达图"/>
    </div>
</div>'''
            log.info(f"【批量断言】多轮雷达图已生成：{radar_path}")
        except Exception as e:
            log.warning(f"【批量断言】多轮雷达图生成失败：{e}")
            radar_chart_html = ''

        # ============================================================
        # 构建合并后的各维度评分明细（含逐轮评分 + 原因列）
        # ============================================================
        detail_rows = []
        for r in results:
            case_id = r.get('case_id', '')
            rounds = case_id_to_rounds.get(case_id, [])

            # 各维度评分（合并为文本）
            ds = r.get('dimension_scores', {})
            dim_scores = []
            for key, (name, weight) in dimensions.items():
                dim_data = ds.get(key, {})
                score = dim_data.get('score', 0)
                is_pass = dim_data.get('pass', False)
                status = '✅' if is_pass else f'❌{score}'
                dim_scores.append(f'{name}: {status}')

            # 逐轮评分
            round_evals = r.get('round_evals', [])
            round_details = []
            for round_data in round_evals:
                is_pass = round_data.get('pass', False)
                status_class = 'score-pass' if is_pass else 'score-fail'
                round_details.append(
                    f"第{round_data.get('round', '?')}轮: "
                    f"<span class='{status_class}'>{round_data.get('score', 0)}分</span> "
                    f"({round_data.get('reason', '')[:50]}{'...' if len(round_data.get('reason', '')) > 50 else ''})"
                )

            # 本地断言
            local_assert_text = self._build_local_assert_text(r)

            # 原因列
            reasons = []
            if not r.get('overall_pass'):
                reasons.append(f"外部模型评估未通过：{r.get('failure_reason', '')}")
            if not r.get('transfer_pass', True):
                reasons.append(f"转人工断言失败：{r.get('transfer_reason', '')}")
            if not r.get('asset_pass', True):
                reasons.append(f"ASSET断言失败：{r.get('asset_reason', '')}")
            if not reasons:
                reasons.append('通过')
            reason_text = '<br>'.join(reasons) if reasons else ''

            # 多轮对话 HTML 格式化
            user_q_html = self._build_rounds_html(rounds, 'question', max_chars=80)
            model_r_html = self._build_rounds_html(rounds, 'actual_answer', max_chars=80)
            expected_html = self._build_rounds_html(rounds, 'expected_answer', max_chars=80)

            overall_pass_class = 'score-pass' if r.get('overall_pass') else 'score-fail'

            detail_rows.append(
                f'<tr>'
                f'  <td>{r.get("case_id", "")}</td>'
                f'  <td>{r.get("case_desc", "")}</td>'
                f'  <td class="col-user-q">{user_q_html}</td>'
                f'  <td class="col-model-r">{model_r_html}</td>'
                f'  <td class="col-expected">{expected_html}</td>'
                f'  <td>{"<br>".join(dim_scores)}</td>'
                f'  <td>{"<br>".join(round_details)}</td>'
                f'  <td class="{overall_pass_class}">{r.get("overall_score", 0)}</td>'
                f'  <td>{local_assert_text}</td>'
                f'  <td>{reason_text}</td>'
                f'</tr>'
            )

        # ============================================================
        # 构建失败用例详情表（含各维度评分 + 原因）
        # ============================================================
        failed_detail_rows = []
        for r in failed_items:
            case_id = r.get('case_id', '')
            rounds = case_id_to_rounds.get(case_id, [])

            # 各维度评分
            ds = r.get('dimension_scores', {})
            dim_scores = []
            for key, (name, weight) in dimensions.items():
                dim_data = ds.get(key, {})
                score = dim_data.get('score', 0)
                is_pass = dim_data.get('pass', False)
                status = '✅' if is_pass else f'❌{score}'
                dim_scores.append(f'{name}: {status}')

            # 逐轮评分
            round_evals = r.get('round_evals', [])
            round_details = []
            for round_data in round_evals:
                is_pass = round_data.get('pass', False)
                status_class = 'score-pass' if is_pass else 'score-fail'
                round_details.append(
                    f"第{round_data.get('round', '?')}轮: "
                    f"<span class='{status_class}'>{round_data.get('score', 0)}分</span> "
                    f"({round_data.get('reason', '')[:50]}{'...' if len(round_data.get('reason', '')) > 50 else ''})"
                )

            # 本地断言
            local_assert_text = self._build_local_assert_text(r)

            # 原因列
            reasons = []
            if not r.get('overall_pass'):
                reasons.append(f"外部模型评估未通过：{r.get('failure_reason', '')}")
            if not r.get('transfer_pass', True):
                reasons.append(f"转人工断言失败：{r.get('transfer_reason', '')}")
            if not r.get('asset_pass', True):
                reasons.append(f"ASSET断言失败：{r.get('asset_reason', '')}")
            reason_text = '<br>'.join(reasons) if reasons else ''

            # 多轮对话 HTML 格式化
            user_q_html = self._build_rounds_html(rounds, 'question', max_chars=80)
            model_r_html = self._build_rounds_html(rounds, 'actual_answer', max_chars=80)
            expected_html = self._build_rounds_html(rounds, 'expected_answer', max_chars=80)

            failed_detail_rows.append(
                f'<tr>'
                f'  <td>{r.get("case_id", "")}</td>'
                f'  <td>{r.get("case_desc", "")}</td>'
                f'  <td class="col-user-q">{user_q_html}</td>'
                f'  <td class="col-model-r">{model_r_html}</td>'
                f'  <td class="col-expected">{expected_html}</td>'
                f'  <td>{"<br>".join(dim_scores)}</td>'
                f'  <td>{"<br>".join(round_details)}</td>'
                f'  <td class="score-fail">{r.get("overall_score", 0)}</td>'
                f'  <td>{local_assert_text}</td>'
                f'  <td>{reason_text}</td>'
                f'</tr>'
            )

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>多轮对话批量断言报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f5f7fa; color: #333; line-height: 1.6; padding: 20px; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header .subtitle {{ opacity: 0.9; font-size: 14px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center; }}
        .stat-card .stat-value {{ font-size: 32px; font-weight: bold; margin: 10px 0; }}
        .stat-card .stat-label {{ font-size: 14px; color: #666; }}
        .stat-card.total .stat-value {{ color: #667eea; }}
        .stat-card.pass .stat-value {{ color: #52c41a; }}
        .stat-card.fail .stat-value {{ color: #f5222d; }}
        .stat-card.rate .stat-value {{ color: #faad14; }}
        .section {{ background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 20px; }}
        .section h2 {{ font-size: 18px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #eee; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; word-wrap: break-word; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #666; }}
        tr:hover {{ background: #f8f9fa; }}
        .score-pass {{ color: #52c41a; font-weight: bold; }}
        .score-fail {{ color: #f5222d; font-weight: bold; }}
        .badge-pass {{ background: #f6ffed; color: #52c41a; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .badge-fail {{ background: #fff1f0; color: #f5222d; padding: 2px 8px; border-radius: 4px; font-size: 12px; }}
        .failed-section {{ border-left: 4px solid #f5222d; }}
        .empty-msg {{ color: #999; text-align: center; padding: 40px; }}
        .col-case-id {{ width: 5%; }}
        .col-case-desc {{ width: 8%; }}
        .col-user-q {{ width: 14%; }}
        .col-model-r {{ width: 14%; }}
        .col-expected {{ width: 14%; }}
        .col-dim {{ width: 14%; }}
        .col-round {{ width: 14%; }}
        .col-score {{ width: 5%; }}
        .col-local {{ width: 12%; min-width: 120px; }}
        .col-reason {{ width: 14%; }}
        .col-fix {{ width: 8%; }}
        .dialog-round {{ margin-bottom: 4px; padding: 2px 0; border-bottom: 1px dashed #e8e8e8; }}
        .dialog-round:last-child {{ border-bottom: none; margin-bottom: 0; }}
        .round-label {{ display: inline-block; background: #e6f7ff; color: #1890ff; font-size: 11px; padding: 1px 5px; border-radius: 3px; margin-right: 4px; white-space: nowrap; }}
        .round-text {{ color: #333; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>多轮对话批量断言报告</h1>
            <p class="subtitle">生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card total">
                <div class="stat-label">总用例数</div>
                <div class="stat-value">{total}</div>
            </div>
            <div class="stat-card pass">
                <div class="stat-label">通过</div>
                <div class="stat-value">{pass_count}</div>
            </div>
            <div class="stat-card fail">
                <div class="stat-label">失败</div>
                <div class="stat-value">{fail_count}</div>
            </div>
            <div class="stat-card rate">
                <div class="stat-label">通过率</div>
                <div class="stat-value">{pass_rate}</div>
            </div>
        </div>

        {radar_chart_html}

        <div class="section failed-section">
            <h2>失败用例详情（{len(failed_items)} 条）</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr>
                            <th class="col-case-id">用例ID</th>
                            <th class="col-case-desc">场景描述</th>
                            <th class="col-user-q">用户问题</th>
                            <th class="col-model-r">模型回复</th>
                            <th class="col-expected">标准话术</th>
                            <th class="col-dim">各维度评分</th>
                            <th class="col-round">逐轮评分</th>
                            <th class="col-score">总分</th>
                            <th class="col-local">本地断言</th>
                            <th class="col-reason">原因</th>
                        </tr>
                    </thead>
                    <tbody>
                        {chr(10).join(failed_detail_rows) if failed_detail_rows else '<tr><td colspan="10" class="empty-msg">无失败用例</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="section">
            <h2>各维度评分明细</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr class="dimension-header">
                            <th class="col-case-id">用例ID</th>
                            <th class="col-case-desc">场景描述</th>
                            <th class="col-user-q">用户问题</th>
                            <th class="col-model-r">模型回复</th>
                            <th class="col-expected">标准话术</th>
                            <th class="col-dim">各维度评分</th>
                            <th class="col-round">逐轮评分</th>
                            <th class="col-score">总分</th>
                            <th class="col-local">本地断言</th>
                            <th class="col-reason">原因</th>
                        </tr>
                    </thead>
                    <tbody>
                        {chr(10).join(detail_rows) if detail_rows else '<tr><td colspan="10" class="empty-msg">暂无数据</td></tr>'}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>"""

        html_path = os.path.join(output_dir, f'batch_assert_multi_turn_report_{timestamp}.html')
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        log.info(f"【批量断言】多轮 HTML 报告已生成：{html_path}")
        return html_path

    @staticmethod
    def _build_local_assert_text(result: dict) -> str:
        """
        构建本地断言展示文本

        格式：
        - 有断言时：
            结论：success/fail
            第X轮：转人工✅、ASSET❌
        - 无断言时：
            结论：success（无断言）
        """
        per_round_asserts = result.get('per_round_asserts', [])

        # 检查是否有逐轮信息
        if not per_round_asserts:
            # 兼容旧逻辑：没有逐轮信息时
            transfer_pass = result.get('transfer_pass', True)
            asset_pass = result.get('asset_pass', True)
            if transfer_pass and asset_pass:
                return '<span style="color:#999;">结论：success（无断言）</span>'
            conclusion = 'fail' if not (transfer_pass and asset_pass) else 'success'
            conclusion_color = '#f5222d' if conclusion == 'fail' else '#52c41a'
            lines = [f'<div style="font-weight:bold; color:{conclusion_color};">结论：{conclusion}</div>']
            if not transfer_pass:
                lines.append(f'<div>转人工：❌</div>')
            if not asset_pass:
                lines.append(f'<div>ASSET：❌</div>')
            return '\n'.join(lines)

        # 检查是否有任何一轮有断言（转人工或ASSET）
        has_any_assert = any(
            r.get('has_transfer_assert') or r.get('has_asset_assert')
            for r in per_round_asserts
        )

        if not has_any_assert:
            return '<span style="color:#999;">结论：success（无断言）</span>'

        # 有断言，计算整体结论
        overall_pass = result.get('transfer_pass', True) and result.get('asset_pass', True)
        conclusion = 'success' if overall_pass else 'fail'
        conclusion_color = '#52c41a' if overall_pass else '#f5222d'

        # 构建展示内容
        lines = [f'<div style="font-weight:bold; color:{conclusion_color};">结论：{conclusion}</div>']

        # 按轮展示有断言的轮次
        hover_lines = []
        for r in per_round_asserts:
            if r.get('has_transfer_assert') or r.get('has_asset_assert'):
                round_no = r.get('round', '?')
                parts = []
                if r.get('has_transfer_assert'):
                    t_icon = '✅' if r.get('transfer_pass') else '❌'
                    parts.append(f"转人工{t_icon}")
                if r.get('has_asset_assert'):
                    a_icon = '✅' if r.get('asset_pass') else '❌'
                    parts.append(f"ASSET{a_icon}")
                lines.append(f'<div>第{round_no}轮：{"、".join(parts)}</div>')

                # hover 详情
                hover_lines.append(f"第{round_no}轮:")
                if r.get('has_transfer_assert'):
                    t_status = '通过' if r.get('transfer_pass') else '失败'
                    t_reason = r.get('transfer_reason', '')
                    hover_lines.append(f"  转人工({t_status}): {t_reason or '通过'}")
                if r.get('has_asset_assert'):
                    a_status = '通过' if r.get('asset_pass') else '失败'
                    a_reason = r.get('asset_reason', '')
                    hover_lines.append(f"  ASSET({a_status}): {a_reason or '通过'}")

        text = '\n'.join(lines)
        if hover_lines:
            # 使用 &#10; 实现 hover 换行
            detail_text = '&#10;'.join(hover_lines)
            text += f' <span title="{detail_text}" style="cursor:help">📋</span>'
        return text

    @staticmethod
    def _escape_html(text: str) -> str:
        """转义 HTML 特殊字符，用于 title 属性"""
        if not text:
            return ''
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    @staticmethod
    def _truncate_text(text: str, max_length: int = 50) -> str:
        """截断文本，超出部分显示省略号"""
        if not text:
            return ''
        if len(text) <= max_length:
            return text
        return text[:max_length] + '...'
