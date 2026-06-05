# -*- coding: utf-8 -*-
"""
# @File    : intent_confusion_matrix.py
# @Date    : 2026-06-02
# @Author  : jeremyzhai
# @Description  : 模型意图识别混淆矩阵生成工具，支持多意图分类评估（纯numpy实现，无需sklearn）
"""

import os
from collections import Counter
from typing import Dict, List, Optional, Tuple, Union

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np


# ============================================================
# 配置中文字体（Windows 环境）
# ============================================================
plt.rcParams['font.sans-serif'] = [
    'Microsoft YaHei',
    'SimHei',
    'SimSun',
    'WenQuanYi Micro Hei',
    'sans-serif',
]
plt.rcParams['axes.unicode_minus'] = False


def _get_font_prop():
    """动态查找并返回可用的中文字体 FontProperties."""
    font_candidates = [
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\simsun.ttc',
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            return fm.FontProperties(fname=font_path)
    return None


def compute_metrics(y_true: List, y_pred: List, labels: Optional[List[str]] = None) -> Dict[str, float]:
    """
    计算分类评估指标（准确率、精确率、召回率、F1分数）

    Args:
        y_true: 标准答案列表
        y_pred: 模型预测结果列表
        labels: 所有意图标签列表

    Returns:
        包含各项评估指标的字典
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"y_true ({len(y_true)}) 和 y_pred ({len(y_pred)}) 长度不一致")

    if labels is None:
        labels = sorted(set(y_true) | set(y_pred))

    # 计算混淆矩阵
    label_to_idx = {label: i for i, label in enumerate(labels)}
    n = len(labels)
    cm = np.zeros((n, n), dtype=int)
    for true, pred in zip(y_true, y_pred):
        if true in label_to_idx and pred in label_to_idx:
            cm[label_to_idx[true], label_to_idx[pred]] += 1

    # 计算各项指标
    tp = np.diag(cm)  # 真正例（对角线）
    fp = cm.sum(axis=0) - tp  # 假正例
    fn = cm.sum(axis=1) - tp  # 假反例
    tn = cm.sum() - tp - fp - fn  # 真反例

    # 每个类别的精确率、召回率、F1
    precision_per_class = np.divide(tp, tp + fp, out=np.zeros_like(tp, dtype=float), where=(tp + fp) > 0)
    recall_per_class = np.divide(tp, tp + fn, out=np.zeros_like(tp, dtype=float), where=(tp + fn) > 0)
    f1_per_class = np.divide(2 * precision_per_class * recall_per_class,
                             precision_per_class + recall_per_class,
                             out=np.zeros_like(tp, dtype=float),
                             where=(precision_per_class + recall_per_class) > 0)

    # 各类别的样本数
    support = cm.sum(axis=1)
    total = support.sum()

    metrics = {
        'accuracy': tp.sum() / total if total > 0 else 0.0,
        'precision_macro': precision_per_class.mean(),
        'recall_macro': recall_per_class.mean(),
        'f1_macro': f1_per_class.mean(),
        'precision_weighted': np.average(precision_per_class, weights=support) if total > 0 else 0.0,
        'recall_weighted': np.average(recall_per_class, weights=support) if total > 0 else 0.0,
        'f1_weighted': np.average(f1_per_class, weights=support) if total > 0 else 0.0,
        'precision_per_class': {labels[i]: precision_per_class[i] for i in range(n) if support[i] > 0},
        'recall_per_class': {labels[i]: recall_per_class[i] for i in range(n) if support[i] > 0},
        'f1_per_class': {labels[i]: f1_per_class[i] for i in range(n) if support[i] > 0},
        'support': {labels[i]: int(support[i]) for i in range(n) if support[i] > 0},
    }
    return metrics


def draw_confusion_matrix(
    y_true: List,
    y_pred: List,
    labels: Optional[List[str]] = None,
    *,
    title: str = "意图识别混淆矩阵",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (10, 8),
    cmap: str = 'Blues',
    normalize: Optional[str] = None,
    show_values: bool = True,
    show_percent: bool = True,
    font_size: int = 12,
    title_font_size: int = 16,
    label_font_size: int = 12,
    show: bool = True,
    dpi: int = 150,
    close_after_save: bool = True,
) -> Dict:
    """
    绘制混淆矩阵热力图

    Args:
        y_true: 标准答案列表
        y_pred: 模型预测结果列表
        labels: 意图标签名称列表（排序后作为坐标轴标签）
        title: 图表标题
        save_path: 保存路径（如 'output/confusion_matrix.png'），None 则不保存
        figsize: 图表大小，默认 (10, 8)
        cmap: 颜色映射方案，默认 'Blues'
        normalize: 归一化方向，可选 'true'（按行归一化）/ 'pred'（按列归一化）/ 'all'（全局归一化）/ None（不归一化）
        show_values: 是否显示数值
        show_percent: 是否在数值后显示百分比（仅在归一化时生效）
        font_size: 基础字体大小
        title_font_size: 标题字体大小
        label_font_size: 标签字体大小
        show: 是否显示图表（调试用）
        dpi: 保存图片的DPI
        close_after_save: 保存后是否关闭图表（防止内存泄漏）

    Returns:
        包含 'matrix', 'labels', 'metrics' 的字典

    Example:
        # 标准答案和预测结果
        y_true = ['查询余额', '转账', '查询余额', '查询余额']
        y_pred = ['查询余额', '查询余额', '查询余额', '转账']

        draw_confusion_matrix(
            y_true, y_pred,
            labels=['查询余额', '转账', '信用卡还款'],
            normalize='true',
            save_path='output/confusion_matrix.png',
        )
    """
    if len(y_true) != len(y_pred):
        raise ValueError(f"y_true ({len(y_true)}) 和 y_pred ({len(y_pred)}) 长度不一致")

    if not y_true:
        raise ValueError("输入数据为空")

    # 自动提取所有标签
    all_labels = sorted(set(y_true) | set(y_pred))
    if labels is not None:
        labels = list(labels)
        for label in all_labels:
            if label not in labels:
                labels.append(label)
    else:
        labels = all_labels

    # 计算混淆矩阵
    label_to_idx = {label: i for i, label in enumerate(labels)}
    n = len(labels)
    cm = np.zeros((n, n), dtype=int)
    for true, pred in zip(y_true, y_pred):
        if true in label_to_idx and pred in label_to_idx:
            cm[label_to_idx[true], label_to_idx[pred]] += 1

    # 计算指标
    metrics = compute_metrics(y_true, y_pred, labels)

    # 归一化矩阵（用于显示百分比）
    if normalize == 'true':
        row_sums = cm.sum(axis=1, keepdims=True)
        cm_display = np.divide(cm.astype('float'), row_sums,
                               out=np.zeros_like(cm, dtype=float), where=row_sums > 0)
        title = f"{title} (按行归一化 - Recall)"
    elif normalize == 'pred':
        col_sums = cm.sum(axis=0, keepdims=True)
        cm_display = np.divide(cm.astype('float'), col_sums,
                               out=np.zeros_like(cm, dtype=float), where=col_sums > 0)
        title = f"{title} (按列归一化 - Precision)"
    elif normalize == 'all':
        total = cm.sum()
        cm_display = cm.astype('float') / total if total > 0 else cm.astype('float')
        title = f"{title} (全局归一化)"
    else:
        cm_display = cm.astype('float')

    # 设置全局字体
    plt.rcParams['font.size'] = font_size

    # 创建图形
    fig, ax = plt.subplots(figsize=figsize)

    # 绘制热力图
    im = ax.imshow(cm_display, interpolation='nearest', cmap=cmap)
    ax.figure.colorbar(im, ax=ax)

    # 设置坐标轴
    ax.set(xticks=np.arange(n),
           yticks=np.arange(n),
           xticklabels=labels,
           yticklabels=labels,
           xlabel='预测意图',
           ylabel='标准意图')

    # 旋转 x 轴标签
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # 在每个单元格中显示数值
    if show_values:
        thresh = cm_display.max() / 2. if cm_display.max() > 0 else 1
        for i in range(n):
            for j in range(n):
                if normalize:
                    text = f'{cm[i, j]}\n({cm_display[i, j]:.1%})' if show_percent else f'{cm[i, j]}'
                else:
                    text = f'{cm[i, j]}'
                ax.text(j, i, text,
                        ha="center", va="center",
                        color="white" if cm_display[i, j] > thresh else "black",
                        fontsize=font_size - 1)

    # 设置标题和标签字体
    font_prop = _get_font_prop()
    if font_prop:
        ax.set_title(title, fontsize=title_font_size, fontproperties=font_prop)
        ax.set_xlabel('预测意图', fontsize=label_font_size, fontproperties=font_prop)
        ax.set_ylabel('标准意图', fontsize=label_font_size, fontproperties=font_prop)
    else:
        ax.set_title(title, fontsize=title_font_size)
        ax.set_xlabel('预测意图', fontsize=label_font_size)
        ax.set_ylabel('标准意图', fontsize=label_font_size)

    # 调整标签字体
    if font_prop:
        for label in ax.get_xticklabels():
            label.set_fontproperties(font_prop)
        for label in ax.get_yticklabels():
            label.set_fontproperties(font_prop)

    fig.tight_layout()

    # 保存图片
    result_path = ""
    if save_path:
        dir_path = os.path.dirname(save_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        plt.savefig(save_path, dpi=dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        result_path = save_path
        print(f"[OK] 混淆矩阵已保存: {save_path}")

    # 显示图表
    if show:
        plt.show()

    # 关闭图表释放内存
    if close_after_save:
        plt.close(fig)

    return {
        'matrix': cm.tolist(),
        'labels': labels,
        'metrics': metrics,
        'save_path': result_path,
    }


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # ============================================================
    # 示例：多种意图的模型预测结果 vs 标准答案
    # 假设有6种意图类别
    # ============================================================

    # 定义所有意图标签
    intent_labels = [
        '查询余额',
        '转账',
        '信用卡还款',
        '挂失',
        '修改密码',
        '客服投诉',
    ]

    # 标准答案（实际意图）
    y_true = [
        '查询余额', '查询余额', '转账', '转账', '信用卡还款',
        '查询余额', '转账', '信用卡还款', '查询余额', '转账',
        '信用卡还款', '转账', '查询余额', '转账', '信用卡还款',
        '挂失', '挂失', '修改密码', '修改密码', '客服投诉',
        '客服投诉', '查询余额', '转账', '信用卡还款', '查询余额',
        '转账', '转账', '查询余额', '信用卡还款', '转账',
        '查询余额', '信用卡还款', '转账', '查询余额', '信用卡还款',
        '挂失', '查询余额', '转账', '信用卡还款', '转账',
        '修改密码', '转账', '信用卡还款', '查询余额', '转账',
        '挂失', '挂失', '转账', '查询余额', '客服投诉',
    ]

    # 模型预测结果（包含一些错误预测）
    y_pred = [
        '查询余额', '查询余额', '转账', '查询余额', '信用卡还款',
        '查询余额', '转账', '信用卡还款', '查询余额', '转账',
        '信用卡还款', '转账', '查询余额', '转账', '转账',
        '挂失', '挂失', '修改密码', '转账', '客服投诉',
        '客服投诉', '查询余额', '转账', '信用卡还款', '查询余额',
        '转账', '查询余额', '查询余额', '信用卡还款', '转账',
        '查询余额', '信用卡还款', '转账', '查询余额', '信用卡还款',
        '挂失', '查询余额', '转账', '信用卡还款', '转账',
        '挂失', '转账', '信用卡还款', '查询余额', '转账',
        '挂失', '挂失', '转账', '查询余额', '客服投诉',
    ]

    print("=" * 60)
    print("意图识别混淆矩阵 - 传参示例")
    print("=" * 60)
    print(f"总样本数: {len(y_true)}")
    print(f"意图类别: {intent_labels}")
    print("-" * 60)

    # 示例1：绘制不归一化的混淆矩阵（显示原始数量）
    print("\n[示例1] 绘制数量混淆矩阵...")
    result1 = draw_confusion_matrix(
        y_true, y_pred,
        labels=intent_labels,
        title="意图识别混淆矩阵（数量）",
        save_path=r"/report/intent_confusion_matrix_count.png",
        normalize=None,
        cmap='Blues',
        show=False,
    )

    # 示例2：绘制按行归一化的混淆矩阵（显示召回率 Recall）
    print("\n[示例2] 绘制召回率混淆矩阵...")
    result2 = draw_confusion_matrix(
        y_true, y_pred,
        labels=intent_labels,
        title="意图识别混淆矩阵（召回率）",
        save_path=r"/report/intent_confusion_matrix_recall.png",
        normalize='true',
        cmap='Oranges',
        show=False,
    )

    # 示例3：绘制按列归一化的混淆矩阵（显示精确率 Precision）
    print("\n[示例3] 绘制精确率混淆矩阵...")
    result3 = draw_confusion_matrix(
        y_true, y_pred,
        labels=intent_labels,
        title="意图识别混淆矩阵（精确率）",
        save_path=r"/report/intent_confusion_matrix_precision.png",
        normalize='pred',
        cmap='Greens',
        show=False,
    )

    # 打印评估指标
    print("\n" + "=" * 60)
    print("评估指标")
    print("=" * 60)
    metrics = result1['metrics']
    print(f"  准确率 (Accuracy):        {metrics['accuracy']:.4f}")
    print(f"  精确率 (Precision-Macro): {metrics['precision_macro']:.4f}")
    print(f"  召回率 (Recall-Macro):    {metrics['recall_macro']:.4f}")
    print(f"  F1分数 (Macro):           {metrics['f1_macro']:.4f}")
    print(f"  F1分数 (Weighted):        {metrics['f1_weighted']:.4f}")
    print("-" * 60)
    print("各类别 F1 分数:")
    for label, f1 in metrics['f1_per_class'].items():
        print(f"  {label}: {f1:.4f}")
    print("=" * 60)
