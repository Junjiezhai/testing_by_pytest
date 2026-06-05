# -*- coding: utf-8 -*-
"""
# @File    : handle_plot.py
# @Date    : 2026-06-02
# @Author  : jeremyzhai
# @Description  : 模型多维度雷达图绘制工具，支持同一模型多轮次测试表现对比
"""

import os
from typing import Dict, List, Optional, Tuple, Union

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np

# ============================================================
# 配置中文字体（Windows 环境）
# ============================================================
# 优先尝试使用 Microsoft YaHei，其次 SimHei/SimSun
# 如果系统没有这些字体，matplotlib 会自动回退
plt.rcParams['font.sans-serif'] = [
    'Microsoft YaHei',
    'SimHei',
    'SimSun',
    'WenQuanYi Micro Hei',
    'sans-serif',
]
# 解决负号 '-' 显示为方块的问题
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
    # 如果都找不到，返回 None，让 matplotlib 使用默认字体
    return None


# 默认配色方案（高对比度，覆盖多轮次对比）
# 每行: 颜色, 线型, 标记样式
default_line_styles = ['-', '--', '-.', ':', (0, (5, 1, 1, 1, 1, 1)), (0, (10, 2))]
default_markers = ['o', 's', 'D', '^', 'v', 'p']

# 高对比度配色方案（支持6轮对比，每轮颜色差异明显）
DEFAULT_COLORS = [
    '#1E90FF',  # 道奇蓝（蓝色）
    '#FF6B6B',  # 珊瑚红（红色）
    '#2ECC71',  # 翡翠绿
    '#FF9F43',  # 活力橙
    '#9B59B6',  # 紫色
    '#00CEC9',  # 青色
]


# 渐变色方案（如需表达时间递进趋势，可手动传入）
GRADIENT_COLORS = [
    '#FFB6C1',  # 浅粉
    '#FF69B4',  # 粉红
    '#FF1493',  # 深粉
    '#FF6B6B',  # 浅红
    '#DC143C',  # 深红
    '#8B0000',  # 暗红
]


def _validate_data(
    models_data: Dict[str, List[Union[int, float]]], categories: List[str]
) -> None:
    """验证输入数据的有效性."""
    if not models_data:
        raise ValueError("models_data 不能为空字典")

    if not categories:
        raise ValueError("categories 不能为空列表")

    expected_len = len(categories)
    for model_name, values in models_data.items():
        if len(values) != expected_len:
            raise ValueError(
                f"模型 '{model_name}' 的数据维度 ({len(values)}) "
                f"与分类维度数量 ({expected_len}) 不匹配"
            )


def draw_radar_chart(
    models_data: Dict[str, List[Union[int, float]]],
    categories: List[str],
    *,
    title: str = "模型效果评估雷达图",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (10, 10),
    colors: Optional[List[str]] = None,
    line_styles: Optional[List[str]] = None,
    markers: Optional[List[str]] = None,
    show_legend: bool = True,
    legend_loc: str = "upper right",
    bbox_to_anchor: Tuple[float, float] = (1.3, 1.1),
    font_size: int = 12,
    title_font_size: int = 18,
    label_font_size: int = 13,
    grid_alpha: float = 0.6,
    fill_alpha: float = 0.08,
    line_width: float = 2.5,
    marker_size: int = 8,
    y_limit: Tuple[int, int] = (0, 100),
    y_ticks: Optional[List[int]] = None,
    show: bool = True,
    dpi: int = 150,
    close_after_save: bool = True,
    annotate_points: bool = False,
) -> str:
    """
    绘制雷达图（支持同一模型多轮次表现对比）

    Args:
        models_data: 模型数据，格式为 {轮次/时间标识: [各维度得分列表]}
                     例如: {"2025-01": [92, 89, ...], "2025-02": [93, 90, ...]}
        categories: 评估维度名称列表
        title: 图表标题
        save_path: 保存路径（如 'output/radar.png'），None 则不保存
        figsize: 图表大小，默认 (10, 10)
        colors: 自定义颜色列表，None 则使用默认高对比度配色
        line_styles: 自定义线型列表，None 则自动分配不同线型
                     可选: '-', '--', '-.', ':', (0, (5, 1)), (0, (10, 2)) 等
        markers: 自定义标记样式列表，None 则自动分配不同标记
                 可选: 'o', 's', 'D', '^', 'v', 'p', '*', 'h' 等
        show_legend: 是否显示图例
        legend_loc: 图例位置
        bbox_to_anchor: 图例位置偏移
        font_size: 基础字体大小
        title_font_size: 标题字体大小
        label_font_size: 标签字体大小
        grid_alpha: 网格线透明度
        fill_alpha: 填充区域透明度
        line_width: 线条宽度
        marker_size: 数据点大小
        y_limit: Y轴范围，默认 (0, 100)
        y_ticks: Y轴刻度值，默认 [20, 40, 60, 80, 100]
        show: 是否显示图表（调试用）
        dpi: 保存图片的DPI
        close_after_save: 保存后是否关闭图表（防止内存泄漏）
        annotate_points: 是否在数据点上标注数值

    Returns:
        保存的图片路径（如果 save_path 不为 None），否则返回空字符串

    Example:
        # 多轮次同一模型对比
        rounds = {
            "第一轮": [92, 89, 85, 87, 94, 78],
            "第二轮": [93, 90, 86, 88, 95, 79],
            "第三轮": [95, 92, 88, 90, 96, 82],
        }
        categories = ["意图识别准确率", "加权准确率", "合规Recall",
                      "卡片正确率", "含义一致性", "推理耗时"]
        draw_radar_chart(rounds, categories, save_path="output/radar.png")
    """
    # 参数校验
    _validate_data(models_data, categories)

    # 设置全局字体
    plt.rcParams['font.size'] = font_size

    # 计算角度（闭合图形需要首尾相连）
    num_categories = len(categories)
    angles = np.linspace(0, 2 * np.pi, num_categories, endpoint=False).tolist()
    angles += angles[:1]  # 闭合

    # 创建图形
    fig, ax = plt.subplots(figsize=figsize, subplot_kw=dict(polar=True))

    # 获取颜色
    num_rounds = len(models_data)
    if colors:
        color_list = colors[:num_rounds] if len(colors) >= num_rounds else colors + DEFAULT_COLORS[num_rounds - len(colors):]
    else:
        color_list = DEFAULT_COLORS[:num_rounds]

    # 获取线型
    if line_styles:
        style_list = line_styles[:num_rounds] if len(line_styles) >= num_rounds else line_styles + default_line_styles[num_rounds - len(line_styles):]
    else:
        style_list = default_line_styles[:num_rounds]

    # 获取标记样式
    if markers:
        marker_list = markers[:num_rounds] if len(markers) >= num_rounds else markers + default_markers[num_rounds - len(markers):]
    else:
        marker_list = default_markers[:num_rounds]

    # 绘制每个轮次的雷达图
    for idx, (round_name, values) in enumerate(models_data.items()):
        values_closed = list(values) + values[:1]

        ax.plot(
            angles,
            values_closed,
            linestyle=style_list[idx],
            linewidth=line_width,
            label=round_name,
            color=color_list[idx],
            marker=marker_list[idx],
            markersize=marker_size,
            markerfacecolor='white',
            markeredgewidth=1.5,
            markeredgecolor=color_list[idx],
        )
        ax.fill(angles, values_closed, alpha=fill_alpha, color=color_list[idx])

        # 可选：在数据点上标注数值
        if annotate_points:
            for angle, value in zip(angles, values_closed):
                ax.annotate(
                    f'{value:.0f}',
                    xy=(angle, value),
                    xytext=(angle, value + 3),
                    fontsize=font_size - 2,
                    ha='center',
                    va='center',
                    color=color_list[idx],
                )

    # 设置X轴刻度标签
    ax.set_xticks(angles[:-1])
    font_prop = _get_font_prop()
    if font_prop:
        ax.set_xticklabels(categories, fontsize=label_font_size, fontproperties=font_prop)
    else:
        ax.set_xticklabels(categories, fontsize=label_font_size)

    # 设置Y轴范围
    ax.set_ylim(*y_limit)
    if y_ticks is None:
        y_ticks = list(range(y_limit[0] + 20, y_limit[1] + 1, 20))
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([str(t) for t in y_ticks], fontsize=font_size - 2, color='gray')

    # 设置网格线
    ax.grid(True, linestyle='--', alpha=grid_alpha)

    # 标题
    if font_prop:
        plt.title(title, fontsize=title_font_size, fontweight='bold', pad=30, fontproperties=font_prop)
    else:
        plt.title(title, fontsize=title_font_size, fontweight='bold', pad=30)

    # 图例
    if show_legend and len(models_data) > 1:
        legend = ax.legend(
            loc=legend_loc,
            bbox_to_anchor=bbox_to_anchor,
            fontsize=font_size,
            frameon=True,
            fancybox=True,
            shadow=True,
            prop=font_prop or {'size': font_size},
        )

    plt.tight_layout()

    # 保存图片
    result_path = ""
    if save_path:
        dir_path = os.path.dirname(save_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        plt.savefig(save_path, dpi=dpi, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        result_path = save_path
        print(f"[OK] 雷达图已保存: {save_path}")

    # 显示图表
    if show:
        plt.show()

    # 关闭图表释放内存
    if close_after_save:
        plt.close(fig)

    return result_path


def draw_multi_round_radar(
    round_data: Dict[str, List[Union[int, float]]],
    categories: List[str],
    *,
    save_path: Optional[str] = None,
    **kwargs,
) -> str:
    """
    快捷函数：绘制同一模型多轮次表现对比雷达图

    Args:
        round_data: 多轮次数据，格式为 {轮次名: [各维度得分列表]}
                    例如: {"第一轮": [92, 89, ...], "第二轮": [93, 90, ...]}
        categories: 评估维度名称列表
        save_path: 保存路径
        **kwargs: 其他参数透传给 draw_radar_chart

    Returns:
        保存的图片路径
    """
    return draw_radar_chart(round_data, categories, save_path=save_path, **kwargs)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    # 示例：同一模型多轮次测试对比
    # 每轮自动化测试结束后，收集数据
    model_rounds = {
        "第一轮 (2025-01)": [92, 89, 85, 87, 94, 78],
        "第二轮 (2025-02)": [93, 90, 86, 88, 95, 79],
        "第三轮 (2025-03)": [95, 92, 88, 90, 96, 82],
    }
    categories = [
        '意图识别准确率\nAccuracy',
        '意图识别准确率（加权）\nWeighted Accuracy',
        '合规易诉类\nRecall',
        '卡片推送正确率',
        '含义一致性通过率',
        '模型推理耗时ms',
    ]

    draw_radar_chart(
        model_rounds,
        categories,
        title="模型多轮次表现对比",
        save_path=r"E:\code_resource\process_logic_test\making_decison_test\report\model_multi_round_radar.png",
        colors=['#FFB6C1', '#FF6B6B', '#8B0000'],  # 浅->深 递进色
    )
