# -*- coding: utf-8 -*-
"""
# @File    : dbAction.py.py
# @Date    : 2024-08-05
# @Author  : jeremyzhai
"""

import pymysql
import os
from utils.handle_log import log
import traceback
import re
from prettytable import PrettyTable
import requests
from typing import Union
import urllib3
from common.httpAction import LxcloudPlat

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.UTF8'  # 注：设置环境编码方式，可解决读取数据库乱码问题

USER_COOKIE = 'client_type=h5; fs_tag=7FA2565E2CBE36DB2DF0974F273F65AB; isc=LINK_BUYCART.MES202003270237290; _ISC={' \
              '"key":"_ISC","value":"99VIP_DDXQY_TITLE","time_stamp":1656322248541}; choose_product_id=1; _CSC={' \
              '"key":"_CSC","value":"CASH.HOME.00000001","expire":300,"priority":0,"time_stamp":1662633884779}; ' \
              'sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2210000001259%22%2C%22%24device_id%22%3A' \
              '%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%2C%22props%22%3A%7B%7D%2C%22first_id' \
              '%22%3A%221800e6e04ce2-09b26dbb6e9e78-1a343370-1fa400-1800e6e04cfc1a%22%7D; ' \
              'sensorsdata2015session=%7B%7D; channel_extend_info={"entry":"","channel":"","csc":"",' \
              '"min":"jeremyzha*","mid":"36623","retcode":30181032,"fs_tag":"7FA2565E2CBE36DB2DF0974F273F65AB"}; ' \
              'Hm_lvt_6617828cdccae4d04f1557b9a67df803=1696731505; ' \
              'Hm_cv_6617828cdccae4d04f1557b9a67df803=1*uid*36623; ' \
              'Hm_lpvt_6617828cdccae4d04f1557b9a67df803=1698051292; cash_up_id=COM.guding_XQY_banner.LHJQ.JDDHBXQYXE; ' \
              'fp=2eca3ce25b3423f4bb85e76a55afd222; x-s3-sid=6754c6df-7cc1-49f0-b0d4-b0f451dd6a1d; ' \
              'session=5859fa7ee4134ba3aa2922b53b4d7572; Hm_lvt_3592cc1c1f867054320b2773e17711c4=1718336891; ' \
              'Hm_lpvt_3592cc1c1f867054320b2773e17711c4=1718336908; fit_app_id=1000; ' \
              '_SUTC=s_909cd4f33b4307b07c8d9332e039371c; x-s3-sid=TS122bM7n10ubtacro8; ' \
              'Authorization=Bearer%20eyJhbGciOiJIUzUxMiJ9' \
              '.eyJzdWIiOiJqZXJlbXl6aGFpIiwiY3JlYXRlZCI6MTcyNDA1Mjk2NzE2OSwiZXhwIjoxNzU1NTg4OTY3fQ' \
              '.eG2U_Wsg6nGn2weeQ68P4PPPvSOlqsxN9FViUWEcmuNCkJ86k4jEI9xPwVWjy3l6Sb8e_Ytgu_XlXvlkRgoNQw; ' \
              'oa_session=gba6pdpp51hfrm6m73k5t01411; mid=36623; rog_session_test=64e7f734d4331f9d333039f0d8d311c1; ' \
              'rog_session=64e7f734d4331f9d333039f0d8d311c1; ' \
              'www_token_id=Ow8BbLq5PU9yPd0RQcAQgzdTWkCAUwi0WAD8pxORFYfxafXdYskN%2FQG0Efh%2BYjLV%2Fi%2BHbpAHH28259V' \
              '%2FVFnXXQ%3D%3D; uid=3111005; ' \
              'oa_token_id=U%2FHkQpGd0XoVVsx99zTOI2lMR%2BzIBZJB7zJN' \
              '%2FQWhOLFegGep7QpPBUxUsdq3B8rYvvyyuW6BNAKmAjm9uPV0Tg%3D%3D; ticket=8e220806eaca80efdc8d9a65dd29a785; ' \
              'lxcloud_session=t8G6mzllDu9KqQp3ZH '


class DbAction:
    def __init__(self, instance_name, env='stable'):
        """
        获取对应实例的账号名和密码
        :param instance_name: 实例名
        :return: self.instance 实例信息
        """
        self.instance_name = instance_name
        self.env = env

        # 兼容印尼前缀实例名
        # self.instance_name = 'yn' + instance_name

    def __enter__(self):
        """
        创建数据库实例连接
        :return: self.mysql， self.cursor
        """
        # stable环境
        if self.env == 'stable':
            # 兼容印尼流程引擎无法获取DB实例信息
            # log.info(self.instance_name.lower())
            if self.instance_name.lower() == 'ynprocessenginedb':
                self.instance = {
                    "host": '10.9.121.234',
                    "user": 'ynproceng_master',
                    "password": 'ynproceng_master@123',
                    "port": 20015
                }
            else:
                self._get_db_info(self.instance_name.lower())

            try:
                self.mysql = pymysql.connect(host=self.instance["host"], user=self.instance["user"],
                                             password=self.instance["password"],
                                             port=self.instance["port"])
                self.cursor = self.mysql.cursor()
                log.info("数据库实例{}连接成功！".format(self.instance_name))

                return self
            except Exception as e:
                log.error(traceback.format_exc())  # 打印详细日志
                raise Exception(f"实例名称输入错误或不存在！错误信息为：{e}")
        # 预发布及以上环境
        else:
            self.lxcloud = LxcloudPlat(env='pro')
            return self

    def _get_db_info(self, instance_name):
        """
        获取数据库实例对应的账号和密码
        :param instance_name: DB实例名
        :return: dict, 数据库实例信息，例：{
                "host": "10.9.21.121",
                "user": "autoadt_master",
                "password": "autoadt_master@123",
                "port": 20007
            }
        """
        url = r'https://stable-lxcloud.oa.fenqile.com/v1/mysql/conn_info'
        data = {"ftype": f"{instance_name}"}
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': USER_COOKIE
        }
        response = requests.post(url, data=data, headers=headers, verify=False, proxies={})
        try:
            result = response.json()['data'][0]
            result['db_info'] = {
                "host": result['fmysql_host'],
                "user": result['fmaster_user'],
                "password": result['fmaster_pass'],
                "port": int(result['fmysql_port'])
            }
            self.instance = result['db_info']
        except Exception as e:
            log.error(traceback.format_exc())
            raise Exception(f"数据库实例{instance_name}信息获取失败！")

    def _get_column_name(self, db_name: str, table_name: str) -> list:
        """
        查询数据库表列名称，用于打印输出
        :param db_name: 数据库名
        :param table_name: 表名
        :return: list，数据库表的列名
        """
        try:
            sql = f"SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = '{db_name}' AND " \
                  f"TABLE_NAME = '{table_name}'; "
            # 查询数据库表结构
            res_cols = self.query_data(sql=sql)

            pattern = re.compile(r"'[a-zA-Z0-9\_]+'")  # 查找字母&数字
            res = pattern.findall(str(res_cols))
            # resObj = re.search(r"'[a-zA-Z\_]+'", str(res_cols), re.M) #判断是否匹配
            for i in range(len(res)):
                res[i] = (res[i]).replace("'", "").lower()
            # log.info(f"列名查询结果：{res}")
            return res
        except Exception as error:
            log.error(traceback.format_exc())  # 打印详细日志
            raise error

    def _get_table_seq(self, condition: str, key_indicator: str = 'order_id', num: int = 3) -> list:
        """
        判断查询表为单库单表还是百库十表
        :param condition: 查询条件
        :param key_indicator: 查询条件中的key
        :param num:
        :return: list 表序号
        """
        # 判断是否存在key_indicator
        match_key = re.search(r"({0}\ *=\ *'.+?')".format(key_indicator), condition, re.I)
        if match_key:
            param = []
            key_ind = match_key.group()
            if num == 5:
                if len(key_ind) >= 7:
                    # 测试账号只有7位，故本处直接判断是否存在uid，存在置表序号为'00'
                    if 'uid' in key_indicator:
                        param.append('00')
                    else:
                        param.append(key_ind[-6:-4])
                    param.append(key_ind[-4:-2])
                    param.append(key_ind[-2])
                else:
                    raise Exception(f"{key_indicator}输入错误！")
            elif num == 3:
                param.append(key_ind[-4:-2])
                param.append(key_ind[-2])
            elif num == 8:  # 年库天表, 通过instance_id识别
                param.append(key_ind.split("'")[1][1:5])
                param.append(key_ind.split("'")[1][5:9])

            return param
        else:
            log.error(f"查询条件为：{condition}，关键指标为：{key_indicator}")
            raise Exception("输入错误，请输入正确指标以确定表序号！")

    def query_data(self, sql: str) -> tuple:
        """
        数据库查询
        :param sql: sql
        :return: res: tuple
        # 返回的数据类型是元组类型，每个条数据元素为元组类型:
        # (('第一条数据的字段1的值','第一条数据的字段2的值',...,'第一条数据的字段N的值'),(第二条数据),...,(第N条数据))
        """
        try:
            self.cursor.execute(sql)  # 执行sql
            results = self.cursor.fetchall()  # 用于返回多条数据
            # fetchall遍历execute执行的结果集。取execute执行后放在缓冲区的数据，遍历结果，返回数据。
            # log.info('数据查询成功！')
            return results
        except Exception as error:
            # 日志打印
            log.error(traceback.format_exc())  # 打印详细日志
            raise error

    def update_data(self, sql: str) -> None:
        """
        :param sql: sql
        :return: None
        """
        try:
            self.cursor.execute(sql)  # 执行sql
            self.mysql.commit()  # 数据提交
            log.info('数据更新成功！')
        except Exception as error:
            # 日志打印
            log.error(traceback.format_exc())  # 打印详细日志
            raise error

    def insert_data(self, sql: str) -> None:
        """
        :param sql: sql
        :return: None
        """
        try:
            self.cursor.execute(sql)  # 执行sql
            self.mysql.commit()  # 数据提交
            print('数据插入成功！')
        except Exception as error:
            # 日志打印
            log.error(traceback.format_exc())  # 打印详细日志
            raise error

    def _generate_sql(self, inData: dict) -> str:
        """
        组装并生成可执行的sql
        :param inData: sql条件字典
        :return: sql： 可执行的sql语句
        """
        # 1，解析sql相关字段
        sql_type = inData.get('sql_type', 'select')
        target_table = inData.get('target_table')
        condition = inData.get('condition')
        target_column = inData.get('target_column', '*')
        key_indicator = inData.get('key_indicator', 'order_id')
        order_by = inData.get('order_by', False)

        # 2，更新目标表的值，若#==5，则千库十表，=0则为单库单表，=3百库十表, =8年库天表
        table_type = target_table.count("#")
        if table_type == 3:  # 百库十表
            param = self._get_table_seq(condition=condition, key_indicator=key_indicator, num=3)
            ind = target_table.find("_##")
            target_table = target_table[:ind] + "_{0}".format(param[0]) + target_table[ind + 3:-1] + '{0}'.format(
                param[1])
        elif table_type == 5:  # 千库十表
            param = self._get_table_seq(condition=condition, key_indicator=key_indicator, num=5)
            ind = target_table.find("##_##")
            target_table = target_table[:ind] + "{0}_{1}".format(param[0], param[1]) + target_table[
                                                                                       ind + 5:-1] + '{0}'.format(
                param[2])
        elif table_type == 8:  # 年库天表
            param = self._get_table_seq(condition=condition, key_indicator=key_indicator, num=8)
            ind = target_table.find("####")
            target_table = target_table[:ind] + f"{param[0]}_" + target_table[ind + 5:-4] + f'{param[1]}'
            # print(param, target_table)

        # 3， 组装sql语句
        sql = ''
        if sql_type == 'select':
            sql = f"select {target_column} from {target_table} where {condition}"
            if order_by:  # 排序条件非空
                order_by_condition = inData.get('order_by_condition', 'fmodify_time')
                seq = inData.get('seq', 'DESC')
                limits = inData.get('limits', 100)
                sql = sql + f" order by {order_by_condition} {seq} limit {limits}"

            log.info(f"sql查询语句为：{sql}")
        elif sql_type == 'update':
            sql = f"UPDATE {target_table} SET {target_column}, fmodify_time=NOW() WHERE {condition};"
            log.info(f"sql更新语句为：{sql}")
        else:
            raise Exception("暂不支持组装insert语句！！！")

        return sql

    def send_sql_fetch_res(self, inData: dict) -> Union[None, dict]:
        """
        执行sql，返回结果
        :param inData: dict, sql相关信息
        :return: none/dict
        """
        # 1, 组装sql语句，并执行
        sql = self._generate_sql(inData=inData)
        # stable 环境
        if self.env == 'stable':
            results = self.query_data(sql=sql)
            # print(type(results), results)

            if inData['sql_type'] == 'select':
                # 2, 获取列名
                target_column = inData['target_column']
                if target_column == "*":
                    # 从sql中提取数据库名和表名
                    db_name, table_name = (sql.split(" ")[3]).replace(" ", "").split(".")
                    target_column = self._get_column_name(db_name=db_name, table_name=table_name)
                    # print(type(target_column),db_name, table_name, target_column)

                # 3, 格式化打印数据库字段值
                if 'show' in inData.keys():
                    self.print_pretty_table(results, target_column)

                # 4, 获取指定的字段值
                ret_col = inData.get('ret_col', [])
                if ret_col:
                    if len(results) <= 0:
                        raise Exception(f'数据库查询返回结果行数为{len(results)}，无法获取到指定字段值!')

                    for i in range(0, len(ret_col)):
                        ret_col[i] = str(ret_col[i]).lower()
                    ret_vals = dict()
                    for i in range(len(ret_col)):
                        tmp = []
                        for j in range(len(results)):
                            if isinstance(target_column, str):
                                target_column = (target_column.replace(' ', '').lower()).split(',')
                            tmp.append(str(results[j][target_column.index(ret_col[i].lower())]))
                        if len(tmp) > 1:
                            ret_vals[ret_col[i]] = tuple(tmp)
                        else:
                            ret_vals[ret_col[i]] = results[j][target_column.index(ret_col[i])]
                    # print(ret_vals)
                    return ret_vals

            elif inData['sql_type'] == 'update':
                self.update_data(sql=sql)  # 执行sql， 数据提交
                log.info('更新语句执行成功！')
            else:
                raise Exception("插入和删除操作尚未封装，请期待！")
        # 预发布及以上
        else:
            # 组装查询参数
            db_info = {
                "db_type": f"{self.instance_name}",
                "sql": sql,
                "desc": "sql查询"
            }
            results, target_column = self.lxcloud.exec_db_req(db_info=db_info)

            # 3, 格式化打印数据库字段值
            if 'show' in inData.keys():
                self.print_pretty_table(results, target_column)

    @classmethod
    def print_pretty_table(cls, results: Union[list, tuple], target_column: list) -> None:
        """
        美化打印数据库查询结果
        :param results: list，数据库查询结果
        :param target_column: list，列名
        :return:
        """
        if isinstance(target_column, str):
            target_column = (target_column.lower().replace(" ", "")).split(',')
        # 创建表对象
        tb = PrettyTable()
        tb.field_names = target_column
        for row in range(len(results)):
            tb.add_row(results[row])
        tb.align = "l"  # l居左 r居右 c居中
        log.info(f"数据结果打印：\n{tb}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        # stable 环境
        if self.env == 'stable':
            # 关闭数据库连接
            self.cursor.close()
            self.mysql.close()
            log.info(f"关闭{self.instance_name}连接！")
        # 预发布及以上
        else:
            log.info(f"【{self.env}环境】 实例：{self.instance_name}，查询完毕！")


# 额度重构测试
def quota_test_credit(uid='4085145', order_id='O2024202412121438000984', env='stable'):
    # uid = '3122258'

    # print('################  乐卡额度表(CreditlimitDB)   ##########################')
    total_leka_credit = {
        'sql_type': 'select',
        'target_table': "user_quota_db.t_credit_limit",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    # print('################  乐卡额度流水表(CreditlimitDB)   ##########################')
    total_leka_credit_water = {
        'sql_type': 'select',
        'target_table': "user_quota_##_db.t_credit_limit_water_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  非乐卡额度表(专项额度)(CreditlimitDB)   ##########################')
    special_credit = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_card_credit_limit_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }
    # print('################  非乐卡额度流水表(CreditlimitDB)   ##########################')
    special_credit_water = {
        'sql_type': 'select',
        'target_table': "credit_limit_water_##_db.t_card_credit_limit_water_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  盖帽用户表(CreditlimitDB)   ##########################')
    user_credit_hat = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_user_credit_limit_hat_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    # print('################  预授信用户表(CreditlimitDB)   ##########################')
    user_pre_credit = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_pre_credit_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    # print('################  单批类在贷表(CreditlimitDB)   ##########################')
    single_batch_debt = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_single_batch_credit_trade_info_#",
        'condition': f"fuid = '{uid}'",  # and forder_id='{order_id}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    with DbAction(instance_name='CreditlimitDB', env=env) as credit_limit_db:
        log.info('################  乐卡额度表(CreditlimitDB)   ##########################')
        credit_limit_db.send_sql_fetch_res(inData=total_leka_credit)
        log.info('################  乐卡额度流水表(CreditlimitDB)   ##########################')
        credit_limit_db.send_sql_fetch_res(inData=total_leka_credit_water)
        log.info('################  非乐卡额度表(专项额度) (CreditlimitDB) ##########################')
        credit_limit_db.send_sql_fetch_res(inData=special_credit)
        log.info('################  非乐卡额度流水表(CreditlimitDB)  ##########################')
        credit_limit_db.send_sql_fetch_res(inData=special_credit_water)

        log.info('################  盖帽用户表(CreditlimitDB)  ##########################')
        credit_limit_db.send_sql_fetch_res(inData=user_credit_hat)

        log.info('################  预授信用户表(CreditlimitDB)  ##########################')
        credit_limit_db.send_sql_fetch_res(inData=user_pre_credit)

        log.info('################  单批类在贷表(CreditlimitDB)  ##########################')
        credit_limit_db.send_sql_fetch_res(inData=single_batch_debt)

    # print('################  盖帽用户流水表(QuotaLogDB)   ##########################')
    user_credit_hat_water = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_user_credit_limit_hat_change_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  预授信用户流水表(QuotaLogDB)   ##########################')
    user_pre_credit_water = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_pre_credit_water_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='QuotaLogDB', env=env) as quota_log_db:
        log.info('################  乐卡额度流水表(QuotaLogDb)   ##########################')
        quota_log_db.send_sql_fetch_res(inData=total_leka_credit_water)

        log.info('################  非乐卡额度流水表(QuotaLogDb)   ##########################')
        quota_log_db.send_sql_fetch_res(inData=special_credit_water)

        log.info('################  盖帽用户流水表(QuotaLogDB)   ##########################')
        quota_log_db.send_sql_fetch_res(inData=user_credit_hat_water)

        log.info('################  预授信用户流水表(QuotaLogDB)   ##########################')
        quota_log_db.send_sql_fetch_res(inData=user_pre_credit_water)

    # print('################  额度~临时额度表(CreditoperationDB)   ##########################')
    tmp_credit = {
        'sql_type': 'select',
        'target_table': "user_credit_operation_##_db.t_user_temp_credit_detail_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    # print('################  额度~临时额度明细(CreditoperationDB)   ##########################')
    tmp_credit_details = {
        'sql_type': 'select',
        'target_table': "user_credit_operation_##_db.t_user_temp_credit_increment_detail_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    # print('################  用户通用额度池(CreditoperationDB)   ##########################')
    general_pool_credit = {
        'sql_type': 'select',
        'target_table': "user_credit_operation_##_db.t_generator_quota_pool_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    # print('################  用户通用额度池流水(CreditoperationDB)   ##########################')
    general_pool_credit_water = {
        'sql_type': 'select',
        'target_table': "user_credit_operation_##_db.t_generator_quota_pool_water_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    # print('################  用户通用额度池订单表(CreditoperationDB)   ##########################')
    general_pool_credit_order = {
        'sql_type': 'select',
        'target_table': "user_credit_operation_##_db.t_generator_quota_pool_order_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    with DbAction(instance_name='CreditoperationDB', env=env) as credit_operation_db:
        log.info('################  额度~临时额度表(CreditoperationDB)   ##########################')
        credit_operation_db.send_sql_fetch_res(inData=tmp_credit)
        log.info('################  额度~临时额度明细(CreditoperationDB)   ##########################')
        credit_operation_db.send_sql_fetch_res(inData=tmp_credit_details)
        log.info('################  用户通用额度池(CreditoperationDB)   ##########################')
        credit_operation_db.send_sql_fetch_res(inData=general_pool_credit)
        log.info('################  用户通用额度池流水(CreditoperationDB)   ##########################')
        credit_operation_db.send_sql_fetch_res(inData=general_pool_credit_water)
        log.info('################  用户通用额度池订单表(CreditoperationDB)   ##########################')
        credit_operation_db.send_sql_fetch_res(inData=general_pool_credit_order)

    # order_id = 'O20240918999815700256'
    # print('################  额度~交易|授信单导致额度变更明细表(CreditreportDB)   ##########################')
    credit_change_details = {
        'sql_type': 'select',
        'target_table': "user_trade_credit_##_db.t_trade_credit_change_info_#",
        'condition': f"fuid = '{uid}'",  # and ftrade_id='{order_id}'",
        'key_indicator': 'uid',  # 'ftrade_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    # print('################  额度~乐卡固定额度&临时额度变更记录表(CreditreportDB)   ##########################')
    tmp_credit_change_details = {
        'sql_type': 'select',
        'target_table': "credit_limit_##_db.t_credit_limit_change_#",
        'condition': f"fuid = '{uid}'",  # and forder_id='{order_id}' ",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
    }

    with DbAction(instance_name='CreditreportDB', env=env) as credit_report_db:
        log.info('################  额度~交易|授信单导致额度变更明细表(CreditreportDB)   ##########################')
        credit_report_db.send_sql_fetch_res(inData=credit_change_details)
        log.info('################  额度~乐卡固定额度&临时额度变更记录表(CreditreportDB)   ##########################')
        credit_report_db.send_sql_fetch_res(inData=tmp_credit_change_details)

    # order_id = 'O20240918999815700256'
    # print('################  额度~每笔交易订单或账单数据表(QuotaDB)   ##########################')
    trade_details = {
        'sql_type': 'select',
        'target_table': "user_credit_##_##_db.t_trade_each_amount_#",
        'condition': f"fuid = '{uid}' ",  # and ftrade_id='{order_id}'",
        'key_indicator': 'fuid',  # 'ftrade_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 100
    }

    # print('################  额度~用户总借款/还款信息表(QuotaDB)   ##########################')
    loan_repay = {
        'sql_type': 'select',
        'target_table': "user_credit_##_##_db.t_trade_total_amount_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    with DbAction(instance_name='QuotaDB', env=env) as quota_db:
        log.info('################  额度~每笔交易订单或账单数据表(QuotaDB)  ##########################')
        quota_db.send_sql_fetch_res(inData=trade_details)
        log.info('################  额度~用户总借款/还款信息表(QuotaDB)   ##########################')
        quota_db.send_sql_fetch_res(inData=loan_repay)

    # print('################  用户offer表(RcofferDB)   ##########################')
    user_offer = {
        'sql_type': 'select',
        'target_table': "offer_##_db.t_offer_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    # print('################  用户期数表(RcofferDB)   ##########################')
    user_period = {
        'sql_type': 'select',
        'target_table': "offer_##_db.t_user_period_#",
        'condition': f"fuid = '{uid}'",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    with DbAction(instance_name='RcofferDB', env=env) as rcoffer_db:
        log.info('################  用户offer表(RcofferDB) ##########################')
        rcoffer_db.send_sql_fetch_res(inData=user_offer)

        log.info('################  用户期数表(RcofferDB) ##########################')
        rcoffer_db.send_sql_fetch_res(inData=user_period)

    # print('################  生效定价表(PricingDB)   ##########################')
    user_price = {
        'sql_type': 'select',
        'target_table': "pricing_info_##_db.t_effect_price_info_#",
        'condition': f"fuid = '{uid}' and fbusiness_type in (20,10)",
        'key_indicator': 'fuid',
        'target_column': "*",
        'show': True,
        'order_by': False,
    }

    with DbAction(instance_name='PricingDB', env=env) as pricing_db:
        log.info('################  生效定价表(PricingDB) ##########################')
        pricing_db.send_sql_fetch_res(inData=user_price)


# 增信补件测试
def zxbj_test(uid='3170100', order_id='O20250516103810100100', env='stable'):
    # print('################  路由规则表(CredopeDB)   ##########################')
    t_rule = {
        'sql_type': 'select',
        'target_table': "credit_route_db.t_rule",
        'condition': f"Fbiz_id = '{100}' ",
        'key_indicator': 'Fbiz_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  路由规则流水表(CredopeDB)   ##########################')
    t_rule_water = {
        'sql_type': 'select',
        'target_table': "credit_route_db.t_rule_water",
        'condition': f"Fbiz_id = '{100}'",
        'key_indicator': 'Fbiz_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  路由规则流水表(CredopeDB)   ##########################')
    t_rule_res_water = {
        'sql_type': 'select',
        'target_table': "rule_result_####_db.t_rule_result_log_####",
        'condition': f"Fmain_order_id = '{order_id}'",
        'key_indicator': 'Fmain_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredopeDB', env=env) as credope_db:
        log.info('################  路由规则表(CredopeDB)   ##########################')
        credope_db.send_sql_fetch_res(inData=t_rule)

        log.info('################  路由规则流水表(CredopeDB)   ##########################')
        credope_db.send_sql_fetch_res(inData=t_rule_water)

        log.info('################  路由结果流水表(CredopeDB)   ##########################')
        credope_db.send_sql_fetch_res(inData=t_rule_res_water)


    # print('################  授信单表(CreditordDB)   ##########################')
    t_rc_order_id = {
        'sql_type': 'select',
        'target_table': "rc_order_##_##_db.t_rc_order_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CreditordDB', env=env) as creditord_db:
        log.info('################  授信单表(CreditordDB)   ##########################')
        creditord_db.send_sql_fetch_res(inData=t_rc_order_id)

    # # print('################  授信流水单号表(CreditordDB)   ##########################')
    # t_rc_order_id_water = {
    #     'sql_type': 'select',
    #     'target_table': "rc_order_##_##_db.t_rc_order_#",
    #     'condition': f"Fmain_order_id = '{order_id}'",
    #     'key_indicator': 'Fmain_order_id',
    #     'target_column': "*",
    #     'show': True,
    #     'order_by': True,
    #     'limits': 10
    # }

    # print('################  授信流水表(WaterDB)   ##########################')
    t_rc_water = {
        'sql_type': 'select',
        'target_table': "rc_order_water_####_db.t_rc_order_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterDB', env=env) as water_db:
        # log.info('################  授信流水单号表(WaterDB)   ##########################')
        # water_db.send_sql_fetch_res(inData=t_rc_order_id_water)

        log.info('################  授信流水表(WaterDB)   ##########################')
        water_db.send_sql_fetch_res(inData=t_rc_water)


    # print('################  基础资料表--订单维度(CredbasordDB)   ##########################')
    t_basic_order_id = {
        'sql_type': 'select',
        'target_table': "order_data_##_##_db.t_order_data_basic_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredbasordDB', env=env) as Credbasord_db:
        log.info('################  基础资料表--订单维度(CredbasordDB)  ##########################')
        Credbasord_db.send_sql_fetch_res(inData=t_basic_order_id)

    # print('################  基础资料表--用户维度(CredbasuserDB)   ##########################')
    t_basic_user = {
        'sql_type': 'select',
        'target_table': "user_data_##_##_db.t_user_data_basic_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredbasuserDB', env=env) as Credbasuser_db:
        log.info('################  基础资料表--用户维度(CredbasuserDB)  ##########################')
        Credbasuser_db.send_sql_fetch_res(inData=t_basic_user)

    # print('################  基础资料流水表--订单维度(WaterriskcreditDB)   ##########################')
    t_basic_order_id_water = {
        'sql_type': 'select',
        'target_table': "rc_order_data_basic_water_####_db.t_rc_order_data_basic_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  基础资料流水表--用户维度(WaterriskcreditDB)   ##########################')
    t_basic_user_water = {
        'sql_type': 'select',
        'target_table': "rc_user_data_basic_water_##_db.t_rc_user_data_basic_water_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  基础资料流水表--订单维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_basic_order_id_water)

        log.info('################  基础资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_basic_user_water)


    # print('################  教育资料表--订单维度(CrededuordDB)   ##########################')
    t_edu_order_id = {
        'sql_type': 'select',
        'target_table': "order_data_##_##_db.t_order_data_edu_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CrededuordDB', env=env) as Crededuord_db:
        log.info('################  教育资料表--订单维度(CrededuordDB)  ##########################')
        Crededuord_db.send_sql_fetch_res(inData=t_edu_order_id)

    # print('################  教育资料表--用户维度(CrededuuserDB)   ##########################')
    t_edu_user = {
        'sql_type': 'select',
        'target_table': "user_data_##_##_db.t_user_data_edu_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CrededuuserDB', env=env) as Crededuuser_db:
        log.info('################  教育资料表--用户维度(CrededuuserDB)  ##########################')
        Crededuuser_db.send_sql_fetch_res(inData=t_edu_user)

    # print('################  教育资料流水表--订单维度(WaterriskcreditDB)   ##########################')
    t_edu_order_id_water = {
        'sql_type': 'select',
        'target_table': "rc_order_data_edu_water_####_db.t_rc_order_data_edu_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  教育资料流水表--用户维度(WaterriskcreditDB)   ##########################')
    t_edu_user_water = {
        'sql_type': 'select',
        'target_table': "rc_user_data_edu_water_##_db.t_rc_user_data_edu_water_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  教育资料流水表--订单维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_edu_order_id_water)

        log.info('################  教育资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_edu_user_water)


    # print('################  工作资料表--订单维度(CredworkordDB)   ##########################')
    t_work_order_id = {
        'sql_type': 'select',
        'target_table': "rc_order_data_##_##_db.t_rc_order_data_work_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredworkordDB', env=env) as Credworkord_db:
        log.info('################  工作资料表--订单维度(CredworkordDB)  ##########################')
        Credworkord_db.send_sql_fetch_res(inData=t_work_order_id)

    # print('################  工作资料表--用户维度(UserExtDB)   ##########################')
    t_work_user = {
        'sql_type': 'select',
        'target_table': "user_data_##_##_db.t_user_work_info_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='UserExtDB', env=env) as UserExt_db:
        log.info('################  工作资料表--用户维度(UserExtDB)  ##########################')
        UserExt_db.send_sql_fetch_res(inData=t_work_user)

    # print('################  工作资料流水表--订单维度(WaterriskcreditDB)   ##########################')
    t_work_order_id_water = {
        'sql_type': 'select',
        'target_table': "rc_order_data_work_water_####_db.t_rc_order_data_work_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  工作资料流水表--用户维度(WaterriskcreditDB)   ##########################')
    t_work_user_water = {
        'sql_type': 'select',
        'target_table': "rc_user_data_work_water_##_db.t_rc_user_data_work_water_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  工作资料流水表--订单维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_work_order_id_water)

        log.info('################  工作资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_work_user_water)

        # print('################  图片资料表--订单维度(CredpicordDB)   ##########################')
    t_pic_order_id = {
        'sql_type': 'select',
        'target_table': "rc_order_data_##_##_db.t_rc_order_data_pic_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredpicordDB', env=env) as Credpicord_db:
        log.info('################  图片资料表--订单维度(CredpicordDB)  ##########################')
        Credpicord_db.send_sql_fetch_res(inData=t_pic_order_id)

    # print('################  图片资料表--用户维度(CredpicuserDB)   ##########################')
    t_pic_user = {
        'sql_type': 'select',
        'target_table': "rc_user_data_##_##_db.t_rc_user_data_pic_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredpicuserDB', env=env) as Credpicuser_db:
        log.info('################  图片资料表--用户维度(CredpicuserDB)  ##########################')
        Credpicuser_db.send_sql_fetch_res(inData=t_pic_user)

    # print('################  图片资料流水表--订单维度(WaterriskcreditDB)   ##########################')
    t_pic_order_id_water = {
        'sql_type': 'select',
        'target_table': "rc_order_data_pic_water_####_db.t_rc_order_data_pic_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  图片资料流水表--用户维度(WaterriskcreditDB)   ##########################')
    t_pic_user_water = {
        'sql_type': 'select',
        'target_table': "rc_user_data_pic_water_##_db.t_rc_user_data_pic_water_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  图片资料流水表--订单维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_pic_order_id_water)

        log.info('################  图片资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_pic_user_water)

    # print('################  扩展资料表--订单维度(CredextordDB)   ##########################')
    t_ext_order_id = {
        'sql_type': 'select',
        'target_table': "rc_order_data_##_##_db.t_rc_order_data_ext_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredextordDB', env=env) as Credextord_db:
        log.info('################  扩展资料表--订单维度(CredextordDB)  ##########################')
        Credextord_db.send_sql_fetch_res(inData=t_ext_order_id)

    # print('################  扩展资料表--用户维度(CredextuserDB)   ##########################')
    t_ext_user = {
        'sql_type': 'select',
        'target_table': "rc_user_data_##_##_db.t_rc_user_data_ext_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredextuserDB', env=env) as Credextuser_db:
        log.info('################  扩展资料表--用户维度(CredextuserDB)  ##########################')
        Credextuser_db.send_sql_fetch_res(inData=t_ext_user)

    # print('################  扩展资料流水表--订单维度(WaterriskcreditDB)   ##########################')
    t_ext_order_id_water = {
        'sql_type': 'select',
        'target_table': "rc_order_data_ext_water_####_db.t_rc_order_data_ext_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  扩展资料流水表--用户维度(WaterriskcreditDB)   ##########################')
    t_ext_user_water = {
        'sql_type': 'select',
        'target_table': "rc_user_data_ext_water_##_db.t_rc_user_data_ext_water_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  扩展资料流水表--订单维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_ext_order_id_water)

        log.info('################  扩展资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_ext_user_water)


    # print('################  联系人资料表--单表(CredcontordDB)   ##########################')
    t_cont_order_id = {
        'sql_type': 'select',
        'target_table': "credit_user_db.t_contact",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    # print('################  联系人资料表--用户维度(CredcontuserDB)   ##########################')
    t_cont_user = {
        'sql_type': 'select',
        'target_table': "rc_user_data_##_##_db.t_rc_user_data_contact_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CredcontuserDB', env=env) as Credcontuser_db:
        log.info('################  联系人资料表--单表(CredcontordDB)  ##########################')
        Credcontuser_db.send_sql_fetch_res(inData=t_cont_order_id)

        log.info('################  联系人资料表--用户维度(CredcontuserDB)  ##########################')
        Credcontuser_db.send_sql_fetch_res(inData=t_cont_user)



    # print('################  联系人资料流水表--用户维度(WaterriskcreditDB)   ##########################')
    t_cont_user_water = {
        'sql_type': 'select',
        'target_table': "rc_user_data_contact_water_##_db.t_rc_user_data_contact_water_#",
        'condition': f"Fuid = '{uid}'",
        'key_indicator': 'Fuid',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  联系人资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_cont_user_water)

        # print('################  刷脸信息表(CreditdalDB)   ##########################')
    t_face_info = {
        'sql_type': 'select',
        'target_table': "rc_order_data_##_##_db.t_rc_order_data_face_#",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='CreditdalDB', env=env) as Creditdal_db:
        log.info('################  刷脸信息表(CreditdalDB)  ##########################')
        Creditdal_db.send_sql_fetch_res(inData=t_face_info)


    # print('################  刷脸信息流水表(WaterriskcreditDB)   ##########################')
    t_face_info_water = {
        'sql_type': 'select',
        'target_table': "rc_order_data_face_water_####_db.t_rc_order_data_face_water_####",
        'condition': f"Frc_order_id = '{order_id}'",
        'key_indicator': 'Frc_order_id',
        'target_column': "*",
        'show': True,
        'order_by': True,
        'limits': 10
    }

    with DbAction(instance_name='WaterriskcreditDB', env=env) as Waterriskcredit_db:
        log.info('################  联系人资料流水表--用户维度(WaterriskcreditDB)  ##########################')
        Waterriskcredit_db.send_sql_fetch_res(inData=t_face_info_water)

if __name__ == '__main__':
    # quota_test_credit(env='pro')
    zxbj_test(env='pro')

    # order_id = 'O202208201544379043882413'
    #
    # # print('################  分组路径表   ##########################')
    # # fundinpooldb_inData = {
    # #     'sql_type': 'select',
    # #     'target_table': "fund_inpool_2022_db.t_asset_inpool_ext_0820",
    # #     'condition': f"forder_id = '{order_id}'",
    # #     'key_indicator': 'order_id',
    # #     'target_column': "fuid, forder_id,fcreate_time,fmodify_time,fasset_group_path",
    # #     # 'target_column': "*",
    # #     'order_by': False,
    # #     'ret_col': ['fuid', 'forder_id']
    # # }
    # #
    # # with DbAction(instance_name='fundinpooldb') as fundinpooldb:
    # #     fundinpooldb.send_sql_fetch_res(inData=fundinpooldb_inData)
    # #
    # # print('################  订单表   ##########################')
    # # fenqiledb_inData = {
    # #     'sql_type': 'select',
    # #     'target_table': "order_##_##_db.t_order_info_#",
    # #     'condition': f"forder_id = 'O20200618755677300770'",
    # #     'key_indicator': 'order_id',
    # #     # 'target_column': "fuid, forder_id,fcreate_time,fmodify_time,fasset_group_path",
    # #     'target_column': "*",
    # #     'order_by': False,
    # #     'ret_col': ['fuid', 'forder_id']
    # # }
    # #
    # # with DbAction(instance_name='fenqiledb') as fenqile_db:
    # #     fenqile_db.send_sql_fetch_res(inData=fenqiledb_inData)
    #
    # print('################  米霍克决策流水表   ##########################')
    # finstance_id = 'I2024081955116282257893566850471'
    # hawkdb_inData = {
    #     'sql_type': 'select',
    #     'target_table': "hawkeye_decision_engine_record_####_db.t_strategy_node_with_param_decision_####",
    #     'condition': f"fseq = '{finstance_id}' and fnode_id='100987'",
    #     'key_indicator': 'fseq',
    #     'target_column': "*",
    #     'order_by': False,
    #     'ret_col': ['Fapproval_result']
    # }
    #
    # with DbAction(instance_name='hawkdecisionallwaterdb') as hawkdecisionallwaterdb:
    #     res = hawkdecisionallwaterdb.send_sql_fetch_res(inData=hawkdb_inData)
    #     print(type(res), res)
