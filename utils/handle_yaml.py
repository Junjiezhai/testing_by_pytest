# -*- coding: utf-8 -*-
"""
# @File    : handle_instanceid.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""

import yaml
import os
from utils.handle_log import log


# yaml文件读取
def read_yaml_data(file_dir: str) -> dict:
    """
    读取指定yaml文件内容
    :param file_dir: 文件路径
    :return:
    """
    # 转换获取文件的绝对路径
    # BASEDIR = os.path.dirname(os.path.dirname(__file__))
    # CONF_DIR = os.path.join(BASEDIR, "case_data")
    # fileDir = os.path.join(CONF_DIR, fileDir)
    if os.path.exists(file_dir) and os.access(file_dir, os.R_OK):
        # 1- 把文件open到内存里
        with open(file_dir, encoding='utf-8') as fo:
            return yaml.safe_load(fo.read())  # 2- 使用yaml读取
    else:
        log.info(f"File {file_dir} does not exist or is not readable.")


def get_test_config():
    """
    读取测试环境配置文件(config/env_group_config.yaml)
    :return: dict, {'env': str, 'group': str}
    """
    # 获取配置文件路径（config目录）
    config_file_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_group_config.yaml')

    # 如果配置文件不存在，使用默认配置
    if not os.path.exists(config_file_path):
        log.info(f"警告: 配置文件 {config_file_path} 不存在，使用默认配置 env='pro', group='default'")
        return {'env': 'pro', 'group': 'default'}

    try:
        config = read_yaml_data(file_dir=config_file_path)
        if config is None:
            log.info(f"警告: 配置文件 {config_file_path} 内容为空，使用默认配置 env='pro', group='default'")
            return {'env': 'pro', 'group': 'default'}

        env = config.get('env', 'pro')
        group = config.get('group', 'default')
        return {'env': env, 'group': group}
    except Exception as e:
        log.info(f"读取配置文件失败: {e}，使用默认配置 env='pro', group='default'")
        return {'env': 'pro', 'group': 'default'}


def update_test_config(env: str = None, group: str = None):
    """
    更新测试环境配置文件(config/env_group_config.yaml)
    :param env: 环境标识，可选值: stable, yn_stable, mxg_stable, yn_pro, mxg_pro, pro
    :param group: 分组标识，可选值: stable, project_109111228, project_10963208, default
    :return: bool, 更新是否成功
    """
    # 获取配置文件路径
    config_file_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'env_group_config.yaml')

    try:
        # 读取现有配置
        current_config = {}
        if os.path.exists(config_file_path):
            current_config = read_yaml_data(file_dir=config_file_path) or {}

        # 更新配置
        if env is not None:
            current_config['env'] = env
        if group is not None:
            current_config['group'] = group

        # 写入配置文件
        with open(config_file_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        log.info(f"配置文件更新成功: env='{current_config.get('env')}', group='{current_config.get('group')}'")
        return True
    except Exception as e:
        log.info(f"更新配置文件失败: {e}")
        return False


if __name__ == '__main__':
    fileDir = '../config/process_para_format.yaml'
    res = read_yaml_data(file_dir=fileDir)
    log.info(f"{type(res)}, {res}")
