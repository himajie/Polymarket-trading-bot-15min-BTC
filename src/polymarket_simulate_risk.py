import os
import time
import requests
import asyncio
import logging
import json
import pytz
import pandas as pd
import numpy as np 
from datetime import datetime, timedelta,timezone
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
import pandas as pd
from .http_client import ConfigurableHTTPClient
from .config import load_settings
from .config_validator import ConfigValidator
from threading import Thread
from .runner_utils import RunnerHelper
from .mysql_db_utils import MySQLHelper
# from .logger import setup_logging
from .trading import (
    get_client,
    place_order,
    get_positions,
    place_orders_fast,
    extract_order_id,
    wait_for_terminal_order,
    cancel_orders,
    get_trades,
    get_balance,
    get_trades_page,
    get_market,
)

class RiskPolymarket():
    def __init__(self,logger,settings,dbHelper):
        self.dbHelper=dbHelper
        self.settings = settings
        self.client = get_client(settings)
        self.logger=logger 
        CLIENT_CONFIG = {
            'rate_limit_seconds': 0.05,
            'timeout': 30,
            'headers': {
                'User-Agent': 'MyApps/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
        }
        # 获取全局客户端实例
        self.http_client = ConfigurableHTTPClient.get_instance(CLIENT_CONFIG)
        settings = load_settings()
    def get_price(self,token):
        try:
            params = {
                            'token_id': token,
                            'side': 'SELL'
                        }
            response = self.http_client.get('https://clob.polymarket.com/price',params=params)
            response.raise_for_status() 
            # price_map = {token_id: round( 1.0/float(data['SELL']),4) for token_id, data in response.json().items()}
            return  float(response.json().get('price',None))
        except Exception as e:
            return float(0)
            pass

    def get_crypto_price(self, dt: datetime, slug: str) -> float:
        try:
            # 确保传入的时间是UTC时间
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            
            slug_lower = slug.lower()
            symbol_mapping = {
                'btc': 'btcusdt',
                'sol': 'solusdt', 
                'xrp': 'xrpusdt',
                'eth': 'ethusdt',
                'bitcoin': 'btcusdt',
                'ethereum': 'ethusdt',
                'solana': 'solusdt',
            }
            matched_symbol = None
            for prefix, symbol in symbol_mapping.items():
                if slug_lower.startswith(prefix):
                    matched_symbol = symbol
                    break
            
            if not matched_symbol:
                logger.warning(f"无法匹配slug: {slug} 到任何symbol")
                return 0.0
            
            # 计算时间范围：dt的前一分钟（UTC时间）
            one_minute_ago = dt - timedelta(minutes=1)
            
            sql = """
                SELECT price, create_time_iso
                FROM polymarket_crypto_price 
                WHERE symbol = %s 
                AND create_time_iso >= %s 
                AND create_time_iso <= %s
                ORDER BY id DESC
                LIMIT 1
            """
            
            params = (matched_symbol, one_minute_ago, dt)
            result = self.dbHelper.select_one(sql, params)
            
            if result and 'price' in result and result['price'] is not None:
                price = float(result['price'])
                logger.debug(f"找到价格: {matched_symbol} = {price} (时间范围: {one_minute_ago} 到 {dt})")
                return price
            else:
                logger.debug(f"在 {one_minute_ago} 到 {dt} (UTC) 范围内未找到 {matched_symbol} 的价格数据")
                return 0.0    
        except Exception as e:
            logger.error(f"获取基准价格时出错: {e}")
            return 0.0
    def run(self):

        try:
            utc = pytz.UTC
            current_time_utc=datetime.now(utc)
            current_time=datetime.now()
            self.logger.info(f' '*20)
            self.logger.info(f'=='*20)
            self.logger.info(f'==> 开始扫描订单')
            befor_timastamp = int(time.time())  
            after_timestamp = int(time.time() - 60*60*3)
           

            orders = self.dbHelper.execute_query("SELECT *  FROM polymarket_trades WHERE status =0;", ())
            if len(orders) ==0:
                self.logger.info(f'==> 无未平仓订单，跳过本次扫描')
                return
            for index, row in enumerate(orders):
                end_date_iso= pd.to_datetime(row['end_date_iso'],utc=True)
                slug=row['market_slug']
                id = row['id']
                market_id=row['market_id']
                if end_date_iso < current_time_utc:
                    last_trade_price = self.dbHelper.select_one("SELECT *  FROM polymarket_trades_price_his WHERE trade_id =%s ORDER BY id DESC LIMIT 1;", (id,))
                    sell_price= last_trade_price['price'] if last_trade_price else -1
                    self.logger.info(f'==> 订单已过期，修改状态结束处理:{row["market_slug"]}')
                    self.dbHelper.execute_query("UPDATE polymarket_trades set sell_time=%s, sell_time_iso=%s,sell_price=%s,status=1 where id=%s", (current_time,current_time_utc,sell_price,id ))
                    continue
                token_id=row['token_id']
                buy_price = float(row['buy_price'])
                curr_price=self.get_price(token_id)
                unwind_price= self.settings.unwind_price
                if buy_price <= unwind_price or curr_price == 0:
                    self.logger.info(f'==> 已经达到平仓价，平仓:{row["market_slug"]}  买入价:{buy_price}  当前价:{curr_price} 平仓价:{curr_price} ')
                    self.dbHelper.execute_query("UPDATE polymarket_trades set sell_time=%s, sell_time_iso=%s,sell_price=%s,status=2 where id=%s", (current_time,current_time_utc,curr_price,id ))
                    continue

                crypto_current= self.get_crypto_price(current_time_utc,slug)
                db_data={
                    'trade_id':id,
                    'market_slug':slug,
                    'market_id':market_id,
                    'token_id':token_id,
                    'crypto_benchmark':row['crypto_benchmark'],
                    'crypto_current':crypto_current,
                    'buy_price':buy_price,
                    'cur_price':curr_price,
                    'create_time_iso':current_time_utc,
                    'create_time':current_time
                }
                self.dbHelper.insert_one('polymarket_trades_price_his',db_data)
        except Exception as e:
                self.logger.info(f"完整异常: {e.__class__.__name__}: {e}",exc_info=True)
                pass 
                           
if __name__ == "__main__":
    logName= "polymarket_simulate_risk"
    settings = load_settings()
    runnerHelper=RunnerHelper() 
    logConfig=runnerHelper.getLogConfig(logName)
    logging.config.dictConfig(logConfig)
    logger =  logging.getLogger(logName)
    dbHelper = MySQLHelper()
    runner=RiskPolymarket(logger,settings,dbHelper) 
    

    # runner.run()
   
    scheduler = BlockingScheduler()
    scheduler.add_job(runner.run, 'interval', seconds=6, name=logName,next_run_time=datetime.now() )
    scheduler.start()

