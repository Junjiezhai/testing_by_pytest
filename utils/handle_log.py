# -*- coding: utf-8 -*-
"""
# @File    : handle_log.py
# @Date    : 2024-08-02
# @Author  : jeremyzhai
"""

import logging
from loguru import logger


class PropogateHandler(logging.Handler):
    def emit(self, record):
        logging.getLogger(record.name).handle(record)


logger.add(PropogateHandler(), format="{time:YYYY-MM-DD at HH:mm:ss} | {message}") #, encoding="utf-8"

log = logger

if __name__ == '__main__':
    log.debug("这是一条debug日志")
    log.info("第二条")
