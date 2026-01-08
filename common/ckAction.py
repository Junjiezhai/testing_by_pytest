# -*- coding: utf-8 -*-
"""
# @File    : ckAction.py
# @Date    : 2024-10-21
# @Author  : jeremyzhai
"""
import os
import traceback

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from utils.handle_log import log
from common.dbAction import DbAction
from typing import Union
from prettytable import PrettyTable
from assert_code.assertAction import camel_to_db_res, AssertAction, db_res_str_transfer
from utils.handle_path import Base_Path
from utils.handle_yaml import read_yaml_data


class CkAction:
    def __init__(self, env='yn_stable'):
        self.env = env

    def __enter__(self):
        """
        创建clickhouse实例连接
        :return: self
        """
        try:
            if self.env == 'yn_stable':
                # 创建 ClickHouse 数据库连接引擎
                # 格式: clickhouse://username:password@host:port/database
                engine = create_engine('clickhouse://RtOdsSync_master:yCkA1vJaWs5NI0qo@10.9.104.238:11000/')

                # 创建会话
                Session = sessionmaker(bind=engine)
                self.session = Session()
                log.info(f"YN-ClickHouse连接成功：")

                return self
            elif self.env == 'mxg_stable':
                # 创建 ClickHouse 数据库连接引擎
                # 格式: clickhouse://username:password@host:port/database
                engine = create_engine('clickhouse://RtOdsSync_master:mxgyCkA1vJaWs5NI0qo@10.9.104.234:11000/')

                # 创建会话
                Session = sessionmaker(bind=engine)
                self.session = Session()
                log.info(f"MXG-ClickHouse连接成功：")

                return self

        except Exception as e:
            log.error(traceback.format_exc())  # 打印详细日志
            raise Exception(f"实例名称输入错误或不存在！错误信息为：{e}")

    def _generate_ck_sql(self, ck_info: dict) -> str:
        """
        组装生成ck的sql语句
        :param ck_info: dict，类似db_info
        :return:
        """
        sql_type = ck_info.get('sql_type', 'select')
        target_column = ck_info.get('target_column', '*')
        target_table = ck_info.get('target_table', '')
        condition = ck_info.get('condition', '1')

        sql = f'{sql_type} {target_column} from {target_table} where {condition} limit 100'
        log.info(f"ck查询的sql语句：{sql}")

        return sql

    def _get_column_name(self, db_name: str, table_name: str) -> list:
        """
        查询数据库表列名称，用于打印输出
        :param db_name: 数据库名
        :param table_name: 表名
        :return: list，数据库表的列名
        """
        try:
            sql = f"SELECT name FROM system.columns WHERE database = '{db_name}' AND " \
                  f"table = '{table_name}'; "
            # 查询数据库表结构
            res_cols = self.session.execute(text(sql))
            # print(sql, type(res_cols), res_cols)

            col_list = []
            for col in res_cols:
                col_list.append(col[0])
            # log.info(f"列名查询结果：{col_list}")

            return col_list

        except Exception as error:
            log.error(traceback.format_exc())  # 打印详细日志
            raise error

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
        for row in results:
            # print(type(row), row)
            tb.add_row(row)
        tb.align = "l"  # l居左 r居右 c居中
        log.info(f"数据结果打印：\n{tb}")

    def exec_query(self, ck_info: dict):
        """
        执行sql查询
        :param ck_info:  dict，类似db_info
        :return:
        """
        # 获取sql语句
        sql = self._generate_ck_sql(ck_info=ck_info)
        # sql = 'SELECT * FROM risk_control_base_db.t_element_decision_log Where 1 LIMIT 10'
        # 执行查询
        results = self.session.execute(text(sql))
        # 将查询结果格式转换成list
        list_results = list(results)
        # print(type(list_results), list_results)

        # 从sql中提取数据库名和表名
        db_name, table_name = (sql.split(" ")[3]).replace(" ", "").split(".")
        target_column = self._get_column_name(db_name=db_name, table_name=table_name)
        # print(type(target_column), db_name, table_name, target_column)

        # 美化打印查询结果
        if ck_info.get('show', False):
            self.print_pretty_table(results=list_results, target_column=target_column)

        # 4, 获取指定的字段值
        ret_col = ck_info.get('ret_col', [])
        if ret_col:
            ret_vals = dict()
            for col in ret_col:
                # print(col, target_column.index(col))
                tmp_res = []
                for row in list_results:
                    tmp_res.append(row[target_column.index(col)])

                # 如果存在个结果，将结果列表转换为tuple？
                if len(tmp_res) > 1:
                    # ret_vals[col] = tuple(tmp_res)
                    ret_vals[col] = tmp_res
                else:
                    ret_vals[col] = tmp_res[0]

            log.info(f"返回字段结果：{ret_vals}")
            return ret_vals

    def __exit__(self, exc_type, exc_val, exc_tb):
        # 关闭数据库连接
        self.session.close()
        log.info(f"关闭ClickHouse连接！")


if __name__ == '__main__':
    # ck_info = {
    #     "sql_type": "select",
    #     "target_column": "*",
    #     "target_table": "risk_control_base_db.t_strategy_node_decision_water",
    #     "condition": "Fseq = 'I2024102410214292897268267147951' and Fnode_id='-1'",
    #     "ret_col": ["Fapproval_result", "Fdecision_status"]
    # }

    ck_info = {
        "sql_type": "select",
        "target_column": "*",
        "target_table": "risk_control_base_db.t_element_decision_log",
        "condition": "finstance_id = 'I2024120617252442416768126727951'",
        "ret_col": ['felement_id', 'fpackage_id'],
        "show": True
    }
    # ck_info = {
    #     "sql_type": "select",
    #     "target_column": "*",
    #     "target_table": "risk_control_base_db.t_test_case",
    #     "condition": "ftask_id = '15303'",
    #     "ret_col": [],
    #     "show": True
    # }

    with CkAction(env='yn_stable') as ck_engine:
        ck_engine.exec_query(ck_info=ck_info)

    # # 4, 根据函数名读取yaml配置的决策结果查询库表信息
    # env = 'yn_stable'
    # log.info(f"\n============== 【当前环境：{env}】DB信息查询 =============\n")
    # db_config = \
    #     read_yaml_data(file_dir=os.path.join(Base_Path, r'config\execute_res_db_assert.yaml'))["MihawkEngine"][
    #         "online_exec_rcflow_decision"]
    #
    # seq = 'I2024102120522614678688825004471'
    # node_id = '285861'
    # ck_info = db_config['ck_info']
    # ck_info['condition'] = str(db_config['ck_info'].get('condition')).format(seq, node_id)
    #
    # with CkAction(env='yn_stable') as ck_engine:
    #     ck_res = ck_engine.exec_query(ck_info=ck_info)
    # log.info(f"CK查询结果: {type(ck_res)}, {ck_res}")
    #
    # # 比对ck结果和用例预期结果
    # assert_rules = {
    #     "Fapproval_result": {
    #         "type": "equal_to",
    #         "value": 0
    #     },
    #     "Fdecision_status": {
    #         "type": "equal_to",
    #         "value": 0
    #     }
    # }
    # AssertAction.value_assert(data=ck_res, assert_rules=assert_rules, desc="CK查询结果")
