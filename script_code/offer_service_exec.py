# -*- coding: utf-8 -*-
"""
# @File    : offer_service_exec.py
# @Date    : 2024-08-23
# @Author  : jeremyzhai
"""
import calendar

from common.rpcAction import BaseRpc
from utils.handle_log import log
from datetime import datetime, timedelta
from assert_code.assert_decorators import schema_assert, retry

from common.riskMock import RiskMock
from script_code.process_engine_exec import ProcessEngine


# offer入参构造类
class OfferDataDependency:
    def __init__(self, env='stable', group='stable'):
        self.env = env
        self.group = group

    def exec_offer_update(self, uid, process_id: str, mock_req: dict) -> None:
        """
        执行offer更新，先mock，再执行流程引擎
        :param uid:
        :param process_id: str，流程id
        :param mock_req: dict， mock入参
        :return:
        """
        # 1，执行风控2.0流程mock
        RiskMock(env=self.env).process_mock_v2(uid=uid, process_id=process_id, mock_req=mock_req)

        # 2, 构造参数，执行在线实时流程决策
        process_info = {
            "uid": uid,
            "processId": process_id,
            "fieldSet": {}
        }
        ProcessEngine(env=self.env, group=self.group).execute_online(process_info=process_info)

    def card_common_pool(self, uid, pool_type: str, credit_hat_general: int = None, draw_out_param: dict = {}) -> None:
        """
        通用池额度卡，刷入&支取
        :param draw_out_param: dict,支取参数
        :param pool_type: 额度池类型，支取-draw_out， 刷入-brush_in
        :param uid:
        :param credit_hat_general: int，通用池额度（刷入）
        :return:
        """
        # 1，mock参数初始化
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {}

        }
        # 2, 设置通用池额度参数
        if pool_type == 'brush_in':
            process_id = "SP00000541" if self.env == 'stable' else 'P00000193'  # 授予
            mock_req["credit_hat_general"] = credit_hat_general
        else:
            process_id = "P00000154"  # 支取
            if draw_out_param["general_increment_type"] == 1:  # 固定额度
                mock_req["general_increment_type"] = 1
                mock_req["general_fix_credit_up"] = draw_out_param["general_fix_credit_up"]  # 支取的额度值
                mock_req["dhedtz_fix_credit_amount"] = draw_out_param["dhedtz_fix_credit_amount"]  # 支取前的额度
                mock_req["current_credit_limit"] = draw_out_param["current_credit_limit"]  # 支取后的额度
            elif draw_out_param["general_increment_type"] == 0:  # 临时额度
                mock_req["general_increment_type"] = 0
                mock_req["temp_quota_type_out"] = draw_out_param["temp_quota_type_out"]  # 临时额度类型
                mock_req["general_temp_credit_up"] = draw_out_param["general_temp_credit_up"]  # 临时额度值
                mock_req["temp_end_date_general"] = draw_out_param["temp_end_date_general"]  # 临时额度有效期

        # 3，执行数据刷入
        log.info(f"【通用池-特殊额度卡】offer写入(pool_type={pool_type})： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def card_100(self, uid, credit_limit, credit_cash=None, increment_temp_credit=None, effective_end_time=None,
                 credit_limit_hat_buff=None, frozen_credit_limit=None):
        """
        乐卡100刷数，支持指定固定额度、临时额度、盖帽buff
        ref: https://ledocs.oa.fenqile.com/doc/3926d3295d0c2741613b98cbe3c83e51
        :param frozen_credit_limit: 冻结额度, 解冻传0
        :param uid:
        :param credit_limit: 固定额度
        :param credit_cash:  取现额度，不传默认等于固定额度
        :param increment_temp_credit: 临时额度增加值
        :param effective_end_time: 临时额度失效时间，不传默认生效到当前月底，格式："20240930"
        :param credit_limit_hat_buff: 盖帽buff值，不传默认无盖帽
        :return:
        """
        # 1, 设置固定额度参数
        process_id = "P00000198"  # 固定
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {},
            "offer_code": 150,
            "credit_limit": credit_limit,
            "credit_cash": credit_limit if credit_cash is None else credit_cash
        }

        # 2，设置临时额度参数，更新process_id
        if increment_temp_credit is not None:
            process_id = "P00000228"  # 固定+临时
            mock_req["temp_quota_type_out"] = 4
            mock_req["increment_temp_credit"] = increment_temp_credit
            if effective_end_time is None:
                # 获取当前月份的最后一天
                last_day = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
                effective_end_time = f"{datetime.now().year}{datetime.now().month:02d}{last_day:02d}"
            mock_req["effective_end_time"] = effective_end_time

        # 3, 设置冻结额度参数
        if frozen_credit_limit is not None:
            mock_req["frozen_credit_limit"] = frozen_credit_limit

        # 4, 设置盖帽参数
        if credit_limit_hat_buff is not None:
            mock_req["credit_limit_hat_scene"] = 10
            mock_req["credit_limit_hat_max"] = credit_limit_hat_buff

        # 5，执行数据刷入
        log.info(f"【乐卡-100卡】offer写入： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def card_101(self, uid, credit_limit, credit_cash=None, min_period=1, max_period=36):
        """
        乐花卡101卡刷数，支持刷入固定额度和最小最大期数
        :param uid:
        :param credit_limit: 固定额度
        :param credit_cash:  取现额度，不传默认等于固定额度
        :param min_period: 最小期数，默认1期
        :param max_period: 最大期数，默认36期
        :return:
        """
        # 1, 设置固定额度参数
        process_id = "SP00000504" if self.env == 'stable' else 'P00000335'
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {},
            "offer_code": 100,
            "repay_infos": [{
                "repayType": 90,
                "max_period": max_period,
                "min_period": min_period
            }],
            "credit_limit": credit_limit,
            "credit_cash": credit_limit if credit_cash is None else credit_cash
        }
        # 2，执行数据刷入
        log.info(f"【乐花卡-101卡】offer写入： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def card_102(self, uid, credit_limit, credit_cash=None, offer_state=1, min_period=1, max_period=1,
                 effective_end_time=None):
        """
        乐花卡102卡刷数，支持刷入固定额度、期数、失效时间和offer状态
        :param offer_state: offer状态，0:未授予,1:已授予,2:初始化,3:冻结,4:失效
        :param uid:
        :param credit_limit: 固定额度
        :param credit_cash: 取现额度，不传默认等于固定额度
        :param min_period: 最小期数，默认1期
        :param max_period: 最大期数，默认36期
        :param effective_end_time: 临时额度失效时间，不传默认生效到当前月底，格式："20240930"
        :return:
        """
        # 1, 设置固定额度参数
        process_id = "SP00000505" if self.env == 'stable' else 'P00000336'
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {},
            "offer_code": 102,
            "offer_status": offer_state,
            "price": 0,
            "repay_infos": [{
                "repayType": 90,
                "max_period": max_period,
                "min_period": min_period
            }],
            "credit_limit": credit_limit,
            "credit_cash": credit_limit if credit_cash is None else credit_cash
        }

        # 2, 设置失效时间
        if effective_end_time is None:
            # 获取当前月份的最后一天
            effective_end_time = (datetime.now().replace(day=28) + timedelta(days=4) - timedelta(
                days=datetime.now().day)).strftime('%Y%m%d')
        mock_req["effective_end_time"] = effective_end_time

        # 3，执行数据刷入
        log.info(f"【乐花卡-102卡】offer写入： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def card_169(self, uid, credit_limit, credit_cash=None):
        """
        微粒贷专项卡169，整笔借据结清，永久循环额度，支持固定额度，取现额度
        :param uid:
        :param credit_limit: 固定额度
        :param credit_cash:  取现额度，不传默认等于固定额度
        :return:
        """
        # 1, 设置固定额度参数
        process_id = "P00000338"  # 固定
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {},
            "credit_limit": credit_limit,
            "credit_cash": credit_limit if credit_cash is None else credit_cash
        }

        # 2，执行数据刷入
        log.info(f"【微粒贷-169卡】offer写入： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def card_800(self, uid, credit_limit, credit_cash=None, temp_credit_limit=None, temp_credit_end_time=None,
                 credit_limit_hat_buff=None):
        """
        电商通用800刷数，支持指定固定额度、临时额度、盖帽buff
        ref: https://ledocs.oa.fenqile.com/doc/3926d3295d0c2741613b98cbe3c83e51
        :param uid:
        :param credit_limit: 固定额度
        :param credit_cash:  取现额度，不传默认等于固定额度
        :param temp_credit_limit: 临时额度增加值
        :param temp_credit_end_time: 临时额度失效时间，不传默认生效到当前月底，格式："20240930"
        :param credit_limit_hat_buff: 盖帽buff值，不传默认无盖帽
        :return:
        """
        # 1, 设置固定额度参数
        process_id = "SP00000456" if self.env == 'stable' else 'P00000297'
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {},
            "credit_limit": credit_limit,
            "credit_cash": credit_limit if credit_cash is None else credit_cash
        }

        # 2，设置临时额度参数，更新process_id
        if temp_credit_limit is not None:
            process_id = "SP00000468" if self.env == 'stable' else 'P00000296'  # 固定+临时
            mock_req["temp_credit_limit"] = temp_credit_limit
            if temp_credit_end_time is None:
                # 获取当前月份的最后一天
                last_day = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
                temp_credit_end_time = f"{datetime.now().year}{datetime.now().month:02d}{last_day:02d}"

                # temp_credit_end_time = "-2"

            mock_req["temp_credit_end_time"] = temp_credit_end_time

        # 3, 设置盖帽参数
        if credit_limit_hat_buff is not None:
            mock_req["credit_limit_hat_scene"] = 80
            mock_req["credit_limit_hat_max"] = credit_limit_hat_buff

        # 4，执行数据刷入
        log.info(f"【电商-800卡】offer写入： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def card_402(self, uid, credit_limit, credit_cash=None, effective_end_time=None, credit_limit_hat_buff=None):
        """
        电商402卡刷数，支持刷入固定额度和失效时间
        :param uid:
        :param credit_limit: 固定额度
        :param credit_cash: 取现额度，不传默认等于固定额度
        :param effective_end_time: 额度失效时间，不传默认生效到当前月底，格式："20240930"
        :param credit_limit_hat_buff: 盖帽buff值，不传默认无盖帽
        :return:
        """
        # 1, 设置固定额度参数
        process_id = "P00000291"  # 固定
        mock_req = {
            "approval_result": "0",
            "cause": [""],
            "disposal_codes": "",
            "tag_codes": "",
            "untag_codes": [],
            "credit_extra_data": {},
            "credit_limit": credit_limit,
            "credit_cash": credit_limit if credit_cash is None else credit_cash
        }

        # 2, 设置失效时间
        if effective_end_time is None:
            # 获取当前月份的最后一天
            last_day = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
            effective_end_time = f"{datetime.now().year}{datetime.now().month:02d}{last_day:02d}"
        mock_req["effective_end_time"] = effective_end_time

        # 3, 设置盖帽参数
        if credit_limit_hat_buff is not None:
            mock_req["credit_limit_hat_scene"] = 80
            mock_req["credit_limit_hat_max"] = credit_limit_hat_buff

        # 4，执行数据刷入
        log.info(f"【电商-402卡】offer写入： uid-{uid}, 流程id-{process_id}, mock参数-{mock_req}")
        self.exec_offer_update(uid=uid, process_id=process_id, mock_req=mock_req)

    def build_uid_with_condition(self, uid, condition_info: dict) -> None:
        """
        给指定uid按条件刷新额度,支持同时刷多张额度卡
        :param uid:
        :param condition_info: dict，格式如下
        {
            "card_100": {
                "credit_limit": 10000
            },
            "card_101": {
                "credit_limit": 10000
            },
        }
        :return:
        """
        for key, value in condition_info.items():
            # 乐卡
            if key == "card_100":
                credit_limit = value.get('credit_limit')
                credit_cash = value.get('credit_cash', None)
                increment_temp_credit = value.get('increment_temp_credit', None)
                effective_end_time = value.get('effective_end_time', None)
                credit_limit_hat_buff = value.get('credit_limit_hat_buff', None)
                frozen_credit_limit = value.get('frozen_credit_limit', None)
                self.card_100(uid=uid, credit_limit=credit_limit, credit_cash=credit_cash,
                              increment_temp_credit=increment_temp_credit, frozen_credit_limit=frozen_credit_limit,
                              effective_end_time=effective_end_time, credit_limit_hat_buff=credit_limit_hat_buff)
            # 乐花卡101卡
            elif key == 'card_101':
                credit_limit = value.get('credit_limit')
                credit_cash = value.get('credit_cash', None)
                min_period = value.get('min_period', 1)
                max_period = value.get('max_period', 36)
                self.card_101(uid=uid, credit_limit=credit_limit, credit_cash=credit_cash,
                              min_period=min_period, max_period=max_period)
            # 乐花卡102卡
            elif key == 'card_102':
                credit_limit = value.get('credit_limit')
                credit_cash = value.get('credit_cash', None)
                offer_state = value.get('offer_state', 1)
                min_period = value.get('min_period', 1)
                max_period = value.get('max_period', 36)
                effective_end_time = value.get('effective_end_time', None)
                self.card_102(uid=uid, credit_limit=credit_limit, credit_cash=credit_cash, offer_state=offer_state,
                              min_period=min_period, max_period=max_period, effective_end_time=effective_end_time)
            # 微粒贷169卡
            elif key == 'card_169':
                credit_limit = value.get('credit_limit')
                credit_cash = value.get('credit_cash', None)
                self.card_169(uid=uid, credit_limit=credit_limit, credit_cash=credit_cash)
            # 电商通用800卡
            elif key == "card_800":
                credit_limit = value.get('credit_limit')
                credit_cash = value.get('credit_cash', None)
                temp_credit_limit = value.get('temp_credit_limit', None)
                temp_credit_end_time = value.get('temp_credit_end_time', None)
                credit_limit_hat_buff = value.get('credit_limit_hat_buff', None)
                self.card_800(uid=uid, credit_limit=credit_limit, credit_cash=credit_cash,
                              temp_credit_limit=temp_credit_limit,
                              temp_credit_end_time=temp_credit_end_time, credit_limit_hat_buff=credit_limit_hat_buff)
            # 电商专项商品402卡
            elif key == "card_402":
                credit_limit = value.get('credit_limit')
                credit_cash = value.get('credit_cash', None)
                effective_end_time = value.get('effective_end_time', None)
                credit_limit_hat_buff = value.get('credit_limit_hat_buff', None)
                self.card_402(uid=uid, credit_limit=credit_limit, credit_cash=credit_cash,
                              effective_end_time=effective_end_time, credit_limit_hat_buff=credit_limit_hat_buff)
            # 通用池common_pool卡
            elif key == "card_common_pool":
                pool_type = value.get('pool_type', 'brush_in')  # draw_out
                if pool_type == 'brush_in':
                    credit_hat_general = value.get('credit_hat_general')
                    self.card_common_pool(uid=uid, pool_type=pool_type, credit_hat_general=credit_hat_general)
                elif pool_type == 'draw_out':
                    general_increment_type = value.get("general_increment_type", "1")  # 默认固定额度
                    if general_increment_type == 1:
                        draw_out_param = {
                            "general_increment_type": general_increment_type,
                            "general_fix_credit_up": value.get('general_fix_credit_up'),  # 支取的额度值
                            "dhedtz_fix_credit_amount": value.get('dhedtz_fix_credit_amount'),  # 支取前的额度
                            "current_credit_limit": value.get('current_credit_limit'),  # 支取后的额度
                        }
                    else:  # general_increment_type == 0:
                        draw_out_param = {
                            "general_increment_type": general_increment_type,
                            "temp_quota_type_out": value.get('temp_quota_type_out'),  # 临时额度类型
                            "general_temp_credit_up": value.get('general_temp_credit_up'),  # 临时额度值
                            "temp_end_date_general": value.get('temp_end_date_general'),  # 临时额度有效期
                        }
                    self.card_common_pool(uid=uid, pool_type=pool_type, draw_out_param=draw_out_param)

        log.info(f"uid:{uid}, 刷额度成功，本次更新额度卡列表： [{list(condition_info.keys())}]")


if __name__ == '__main__':
    uid = '3123396'  # '3134440'#'3130984'
    condition_info = {
        "card_100": {
            "credit_limit": 7601,
            "credit_cash": 7601,
            # "frozen_credit_limit": 2000,
            # "increment_temp_credit": 5,
            # "credit_limit_hat_buff": 3000
        },
        # "card_101": {
        #     "credit_limit": 100000,
        #     "min_period": 1,
        #     "max_period": 36
        # },
        # "card_102": {
        #     "credit_limit": 6000,
        #     "offer_state": 1,
        #     "min_period": 1,
        #     "max_period": 1,
        #     "effective_end_time": "20251228"
        # },
        # "card_800": {
        #     "credit_limit": 5000,
        #     "temp_credit_limit": -2,
        #     # "credit_limit_hat_buff": 5000
        # },
        # "card_402": {
        #     "credit_limit": 3000,
        #     # "credit_limit_hat_buff": 1000,
        #     "effective_end_time": "20251231"
        # },
        # "card_169": {
        #     "credit_limit": 2500,
        # },
        # "card_common_pool": {
        #     "pool_type": "brush_in",
        #     "credit_hat_general": 80
        # },
        # "card_common_pool": {
        #     "pool_type": "draw_out",
        #     "general_increment_type": 1,
        #     "general_fix_credit_up": 10,
        #     "dhedtz_fix_credit_amount": 10010,
        #     "current_credit_limit": 10000,
        # },
        # "card_common_pool": {
        #     "pool_type": "draw_out",
        #     "general_increment_type": 0,
        #     "temp_quota_type_out": 4,
        #     "general_temp_credit_up": 1,
        #     "temp_end_date_general": "20250228",
        # },
    }
    odd = OfferDataDependency(env='stable', group='stable')
    # odd = OfferDataDependency(env='pre', group='default')
    odd.build_uid_with_condition(uid=uid, condition_info=condition_info)

    # # DB数据查看
    # from common.dbAction import quota_test_credit
    #
    # quota_test_credit(uid=uid)
