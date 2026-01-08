# -*- coding: utf-8 -*-
"""
# @File    : assertAction.py
# @Date    : 2024-08-12
# @Author  : jeremyzhai
"""

import re
import json
from utils.handle_log import log
from jsonpath import jsonpath


def camel_to_db_res(camel_res: dict) -> dict:
    """
    将驼峰命名的key转为下划线命名，首字母变更为f

    :param camel_res: dict
    :return: db_res, dict
    """
    # 使用正则表达式找到所有大写字母的位置，并在其前插入下划线
    # 然后将所有字符转换为小写
    db_res = dict()
    for camel_key in camel_res.keys():
        db_key = 'f' + re.sub('(?<!^)(?=[A-Z])', '_', camel_key).lower()
        db_res[db_key] = camel_res[camel_key]

    return db_res


def db_res_str_transfer(db_res: dict) -> dict:
    """
    数据库字符字段，尝试转换，考虑断言需要
    :param db_res:
    :return:
    """
    for k, v in db_res.items():
        try:
            db_res[k] = eval(v)
        except:
            log.warning(f"数据库字段：{k},值为{db_res[k]}, 格式无法被转换!")

    return db_res


class AssertAction:
    @classmethod
    def base_assert(cls, res, exp) -> bool:
        """
        基础断言方法，判断数据是否相同
        :param res: 接口实际结果
        :param exp: 预期结果（落库结果）
        :return:
        """
        log.info(f'---实际结果：{type(res)},{res}')
        log.info(f'---预期结果：{type(exp)},{exp}')
        if type(res) == type(exp):
            # dict类型，按key遍历，依次核对
            if isinstance(exp, dict):
                for key in exp.keys():
                    # ps.允许判断非空，若预期结果为非空，则仅断言实际结果是否存在
                    if isinstance(exp[key], (int, float)):
                        assert float(res[key]) == float(exp[key])
                    elif isinstance(exp[key], str) and isinstance(res[key], dict):
                        exp[key] = json.loads(exp[key])
                        cls.base_assert(res=res[key], exp=exp[key])
                    # else:
                    #     base_assert(res=res[key], exp=exp[key])
                return True
            elif isinstance(res, list):
                assert set(res) == set(exp)
            else:
                try:
                    # 尝试做数值断言
                    assert float(res) == float(exp)
                except:
                    assert str(res) == str(exp)

        assert res == exp
        # print(f'---{type(res)}类型断言：通过！')

    @classmethod
    def value_assert(cls, data: dict, assert_rules: dict, desc='DB查询结果') -> None:
        """
        数值断言
        :param desc: 描述
        :param data: dict, 决策结果，db/接口出参
        :param assert_rules: dict, 断言类型+期望结果
        :return: None
        """
        log.info(f"------- 执行{desc}断言 ---------")
        if assert_rules:
            # for key, value in assert_rules.items():
            #     log.info(f"断言字段：{key}, 断言规则为：{value}, 实际结果为：{data[key.lower()]}")
            #     cls.do_assert(res=data[key.lower()], exp=value)

            # 兼容ck查询结果，key无需转换成小写
            try:
                for key, value in assert_rules.items():
                    log.info(f"断言字段：{key}, 断言规则为：{value}, 实际结果为：{data[key.lower()]}")
                res_key =data[key.lower()]
            except:
                for key, value in assert_rules.items():
                    log.info(f"断言字段：{key}, 断言规则为：{value}, 实际结果为：{data[key]}")
                res_key =data[key]

            cls.do_assert(res=res_key, exp=value)
            log.info(f"---{desc}断言通过！！！---")
        else:
            log.warning("断言规则为空，当前用例未执行任何断言！！！")

    @classmethod
    def do_assert(cls, res, exp: dict) -> None:
        """
        针对具体结果数据做断言判断
        :param res: 实际结果
        :param exp: dict,预期结果
        :return:
        """

        def inner_assert(res, assert_type, exp):
            # log.info(f"{res}, {assert_type}, {exp}")
            if isinstance(res, dict):
                res = jsonpath(res, f"$..{exp['key']}")[0]

            if assert_type == "contains":
                if isinstance(res, (int, str)):
                    assert exp['value'] == res
                elif isinstance(res, dict):
                    assert (exp['value'] in res)
            elif assert_type == "equal_to":
                assert res == exp['value']
            elif assert_type == "not_equal_to":
                assert res != exp['value']
            else:
                log.error(f"assert_type: {assert_type}暂不支持！")
                assert False

        # 对期望结果的字段做断言
        if isinstance(exp['type'], list):
            for i in range(len(exp['type'])):
                assert_type = exp['type'][i]
                tmp_exp = {
                    "key": exp['key'][i],
                    "value": exp['value'][i]
                }

                inner_assert(res=res, assert_type=assert_type, exp=tmp_exp)
        else:
            inner_assert(res=res, assert_type=exp.get("type"), exp=exp)


if __name__ == '__main__':
    res = {'rr_level_version': '1.6', 'untag_codes': [], 'min_period': 3, 'effective_end_time': '20240914', 'repay_infos': '[{"periodScene":1,"minPeriod":2,"maxPeriod":14,"repayType":90},{"periodScene":3,"minPeriod":1,"maxPeriod":15,"repayType":150}]', 'rr_level_std': 'R1', 'cause': [], 'temp_quota_type_out': 3, 'offer_code': 150, 'max_period': 6, 'disposal_codes': '', 'approval_result': 0, 'increment_temp_credit': 500, 'price': 22.35, 'credit_limit': 7200, 'tag_codes': [], 'price_infos': '[{"businessScene":230,"price":23.35}]', 'credit_cash': 7200, 'credit_extra_data': {'price': 22.35, 'credit_limit': 7200, 'credit_cash': 7200}}

    # assert_type = 'contains'
    exp = {'type': 'equal_to', 'key': 'offer_code', 'value': 150}
    AssertAction.do_assert(res=res, exp=exp)
