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
        self.trade_cache=[]
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
    def sell_order(self,token_id:str=None,price:float=None,size:float=None ):
        try:
            place_order(
            self.settings,
            side="SELL",
            token_id=token_id,
            price=float(price),
            size=float(size),
            tif="GTC",
            )
            self.logger.warning(f"===>卖出订单:   {token_id}, ${price:.4f} x {size} shares")
        except Exception as e:
            self.logger.info(f"卖出失败:  {e}")

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
           
            trades= get_trades_page(self.settings,before=befor_timastamp,after=after_timestamp) 
            # with open('trade_list.json', 'w', encoding='utf-8') as f:
            #     json.dump(trades, f, ensure_ascii=False, indent=2)


            df=pd.DataFrame(trades,columns=['id','side','market','size','price','status','asset_id','match_time','outcome']) 
            df = df.sort_values(by='match_time', ascending=False)
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df = df[df['side'] == 'BUY']
            if df.empty:
                return
            for index, row in df.iterrows():
                market_id=row['market']
                market = get_market(self.settings,market_id)
                if market['closed']:
                    continue
                end_date_iso= pd.to_datetime(market['end_date_iso'], format='ISO8601', utc=True)
                buy_price = float(row['price'])

                
                # with open(f'./files/low_trade_{befor_timastamp}.json', 'w', encoding='utf-8') as f:
                #     json.dump(row.to_dict(), f, ensure_ascii=False, indent=2)
                side = row['side']
                size = row['size']
                outcome = row['outcome']
                slug= market['market_slug']
                token_id=row['asset_id']
                if (buy_price < 0.2) and (slug not in self.trade_cache):
                    with open(f'./files/low_trade_{slug}_{befor_timastamp}.json', 'w', encoding='utf-8') as f:
                        json.dump(trades, f, ensure_ascii=False, indent=2)
                    self.trade_cache.append(slug)


                curr_price=self.get_price(token_id)
                db_data={
                    'market_slug':slug,
                    'market_id':market_id,
                    'token_id':token_id,
                    'outcome':outcome,
                    'side':side,
                    'price':curr_price,
                    'buy_price':buy_price,
                    'size':size,
                    'end_date_iso':end_date_iso,
                    'create_time_iso':current_time_utc,
                    'create_time':current_time
                }
                if curr_price > 0 :
                    self.logger.info(f'==> 记录数据:{slug}')
                    self.dbHelper.insert_one("polymarket_trades", db_data) 
                    self.logger.info(f'==> 开始处理订单:【{self.settings.unwind_price}/{curr_price}/{buy_price}】, outcome:{outcome}, side:{side}, size:{size} 【{slug} 】')
                if curr_price <= 0.001:
                    #没有意义了，放弃
                    self.logger.warning(f'==> 价格过低，放弃处理')
                elif curr_price <= self.settings.unwind_price:
                    self.logger.warning(f'==> 订单价格异常: 强制平仓  平仓价格{curr_price}')
                    self.sell_order(token_id,price,float(curr_price))  
                else:
                    self.logger.info(f'==> 订单状态正常')
        except Exception as e:
                self.logger.info(f"完整异常: {e.__class__.__name__}: {e}",exc_info=True)
                pass
                           
if __name__ == "__main__":
    logName= "risk-poly"
    settings = load_settings()
    runnerHelper=RunnerHelper() 
    logConfig=runnerHelper.getLogConfig(logName)
    logging.config.dictConfig(logConfig)
    logger =  logging.getLogger(logName)
    dbHelper = MySQLHelper()
    runner=RiskPolymarket(logger,settings,dbHelper) 
    

    # runner.run()
   
    scheduler = BlockingScheduler()
    scheduler.add_job(runner.run, 'interval', seconds=10, name=logName,next_run_time=datetime.now() )
    scheduler.start()

