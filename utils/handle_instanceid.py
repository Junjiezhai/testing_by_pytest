# -*- coding: utf-8 -*-
"""
# @File    : handle_instanceid.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""

import random
from datetime import datetime
from typing import Union


def check_test_uid(uid: Union[str, int]) -> bool:
    """
    检查uid是否为测试账号
    :param uid: 支持传入int/str类型
    :return: 是则返回True，否则返回False
    """
    if 3000000 <= int(uid) <= 5000000:
        return True
    else:
        raise Exception(f"传入的uid：{uid}, 非三百万到五百万之间的测试账号！")


def generate_instance_id(uid: Union[str, int]) -> str:
    """
    根据uid随机生成用于决策的instance_id
    :param uid: int/str
    :return:
    """
    # 获取当前日期并格式化为YYYYMMDD
    date_str = datetime.now().strftime('%Y%m%d%H%M%S')

    # 生成19位随机数字
    random_numbers = ''.join([str(random.randint(0, 9)) for _ in range(13)])

    # 取uid尾号后四位
    # if check_test_uid(uid):
    #     uid_tails = (str(uid))[-4:]
    #
    #     # 拼接最终的字符串
    #     random_string = 'I' + date_str + random_numbers + uid_tails
    #
    #     return random_string
    # else:
    #     raise Exception('非测试账号，生成instance_id 失败！')

    # 特殊逻辑，兼容印尼
    uid_tails = (str(uid))[-4:]

    # 拼接最终的字符串
    random_string = 'I' + date_str + random_numbers + uid_tails

    return random_string


if __name__ == '__main__':
    print(generate_instance_id(19182111))
