# -*- coding: utf-8 -*-
"""
pytest 全局配置
"""
import sys

# Windows 下强制 stdout/stderr 使用 UTF-8，防止中文乱码
# 使用 reconfigure() 避免直接替换 sys.stdout 导致 pytest 内部错误
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, OSError, ValueError):
        pass


def pytest_configure(config):
    pass


# ============================================================
# 批量断言 session fixture（autouse，在 session 结束时执行批量断言）
# ============================================================
import pytest


@pytest.fixture(scope='session', autouse=True)
def batch_assert_session(request):
    """
    Session 级别 autouse fixture，在 session 结束时执行批量断言。

    作为 fallback 机制：
    - 正常流程下，批量断言在 test_model_summary_report 中执行
    - 如果 test_model_summary_report 被跳过（如 -k 过滤），则在此 fixture 的 teardown 中执行
    """
    # yield 之前是 setup（session 开始时），这里不需要做什么
    yield

    # yield 之后是 teardown（session 结束时），执行批量断言
    import os
    from utils.batch_assert_collector import batch_collector
    from utils.handle_log import log

    # 检测批量断言模式
    if os.getenv('MODEL_BATCH_ASSERT', '0') != '1':
        return

    # 获取收集的数据
    items = batch_collector.get_all()

    if not items:
        return

    # 检查是否已经执行过（test_model_summary_report 中已经执行过会清空收集器）
    if not items:
        return

    log.info(f"【批量断言】session teardown（fallback），共收集 {len(items)} 条数据，开始批量评估...")

    try:
        from assert_code.batch_model_assert import BatchModelAssert

        # 初始化批量断言器（一次性注入知识库）
        batch = BatchModelAssert(
            model_name=os.getenv('MODEL_BATCH_JUDGE_MODEL', 'deepseek-v4-pro'),
            max_group_size=int(os.getenv('MODEL_BATCH_MAX_GROUP_SIZE', '10')),
            max_group_size_multi=int(os.getenv('MODEL_BATCH_MAX_GROUP_SIZE_MULTI', '2')),
        )

        # 执行批量评估
        results = batch.batch_evaluate(items)

        # 生成报告
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'report', 'model_intent_recognition', 'batch_assert')
        summary = batch.generate_report(items, results, output_dir=output_dir)

        # 保存批量断言结果到 JSON（供外部读取）
        try:
            import json
            import multiprocessing
            worker_id = multiprocessing.current_process().name.replace('-', '_')
            batch_result_file = os.path.join(output_dir, f'batch_assert_result_{worker_id}.json')
            with open(batch_result_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'total': summary['total'],
                    'pass_count': summary['pass_count'],
                    'failed_count': summary['failed_count'],
                    'pass_rate': summary['pass_rate'],
                    'failed_case_ids': summary.get('failed_case_ids', []),
                    'html_path': summary.get('html_path', ''),
                    'detail_path': summary.get('detail_path', ''),
                }, f, ensure_ascii=False, indent=2)
            log.info(f"【批量断言】结果已保存到：{batch_result_file}")
        except Exception as e:
            log.warning(f"【批量断言】保存结果到 JSON 失败：{e}")

        # 输出汇总日志
        log.info("=" * 80)
        log.info("【批量断言评估汇总（session fallback）】")
        log.info(f"  总计：{summary['total']} 条")
        log.info(f"  通过：{summary['pass_count']} 条")
        log.info(f"  失败：{summary['failed_count']} 条")
        log.info(f"  通过率：{summary['pass_rate']}")
        log.info("=" * 80)

    except Exception as e:
        log.error(f"【批量断言】批量评估执行失败：{e}")
        import traceback
        log.error(traceback.format_exc())
    finally:
        # 清空收集器
        batch_collector.clear()
