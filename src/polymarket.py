import os
import time
import requests
import asyncio
import logging
import json
import pandas as pd
import numpy as np 
from datetime import datetime, timedelta,timezone,time
import logging
from apscheduler.schedulers.blocking import BlockingScheduler
import pandas as pd
from .http_client import ConfigurableHTTPClient
from .config import load_settings
from .config_validator import ConfigValidator
from threading import Thread
from .runner_utils import RunnerHelper
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
)

class SeekPolymarket():
    def __init__(self,logger,settings):
        self.settings = settings
        self.client = get_client(settings)
        self.order_count=5

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
        # Setup logging with proper verbosity
        # setup_logging(verbose=settings.verbose, use_rich=settings.use_rich_output)


    def _levels_to_tuples(self, levels) -> list[tuple[float, float]]:
        """Convert OrderSummary-like objects into (price, size) tuples."""
        tuples: list[tuple[float, float]] = []
        for level in levels or []:
            try:
                price = float(level.price)
                size = float(level.size)
            except Exception:
                continue
            if size <= 0:
                continue
            tuples.append((price, size))
        return tuples
    
    def get_dates(self):
        today = datetime.now(timezone.utc).date()  # 获取当前日期
        start_of_day = datetime.combine(today, time.min)


        future_date = today + timedelta(days=1)  # 计算3天后的日期
        end_of_day=datetime.combine(future_date, time.max)
        return start_of_day.strftime("%Y-%m-%d"), end_of_day.strftime("%Y-%m-%d")

    
    
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

    def reslove(self,dfs):
        if dfs.empty:
            return

        df = dfs.explode('events')
        current_time = pd.Timestamp.now(tz='UTC')


        df['start_time'] = pd.to_datetime(df['startDate'], format='ISO8601', utc=True)
        df['end_time'] = pd.to_datetime(df['endDate'], format='ISO8601', utc=True)


        df['end_second'] = df['end_time'].apply(lambda x: (x-current_time).total_seconds())
        df['market_second'] = df.apply(lambda row: (row['end_time'] - row['start_time']).total_seconds(), axis=1)
        df = df[(df['end_second'] > 60) & (df['end_second'] < 3600) & (df['market_second'] > (60*60*6))] #6小时
        if df.empty:
            self.logger.info("==>>无符合条件的数据")  
            return 

      
        # time_diff = current_time - df['end_time']
        # # 结束时间大于3分钟且小于等于30分钟
        # mask = (time_diff > pd.Timedelta(minutes=3)) & (time_diff <= pd.Timedelta(minutes=60))
        # df = df[mask]
        # if df.empty:
        #     self.logger.info("==>>无符合条件的数据")   
        #     return

        
        # df[['token-yes', 'token-no']] = df['clobTokenIds'].apply(lambda x: pd.Series(x) if isinstance(x, list) else pd.Series([None, None]))
        df['clobTokens'] = df['clobTokenIds'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)

        df['event_slug'] = df['events'].apply(lambda x: x.get('slug') if isinstance(x, dict) else None)      
        df[['token-yes', 'token-no']] = df['clobTokens'].apply(lambda x: pd.Series([x[0], x[1]] if isinstance(x, list) and len(x) >= 2 else [None, None]))

        df = df.reset_index(drop=True)
        df=df.loc[df.groupby('id')['end_time'].idxmax()]
        df = df.reset_index(drop=True)

        df = df.drop(df[df['sportsMarketType'].notna()].index)
        # df = df.drop(['events', 'outcomes', 'clobTokenIds','conditionId','slug'], axis=1)
        if df.empty:
            return
        # df = df.drop(['events', 'outcomes', 'clobTokenIds','conditionId','slug'], axis=1)
        # print(df)
        for index, row in df.iterrows():
            # 查询数据库id订单是否存在
            id =row["id"]
            slug=row["event_slug"]
            conditionId=row["conditionId"]


            # trades= get_trades(self.settings) 
           

            up_price=self.get_price(row["token-yes"])
            down_price=self.get_price(row["token-no"])
            if up_price is None or down_price is None:
                self.logger.info(f"==>价格错误，跳过")   
                continue

            if up_price > 0.92 and up_price <= 0.97:
                self.logger.warning(f" "*20)  
                self.logger.warning(f"---------------------------------------------------")  
                self.logger.warning(f"=========>> 价格满足，准备下单!{slug}   << ============")  
                self.logger.warning(f"==>> 市场ID: {id}/【{slug} 】 UP最佳:{up_price}, DOWN最佳:{down_price}")
                self.play_order(conditionId,token_id=row["token-yes"],price=up_price,size=self.order_count)
            elif down_price > 0.92 and down_price <= 0.97:
                self.logger.warning(f" "*20)  
                self.logger.warning(f"---------------------------------------------------")  
                self.logger.warning(f"=========>> 价格满足，准备下单!{slug}   << ============")  
                self.logger.warning(f"==>> 市场ID: {id}/【{slug} 】 DOWN最佳:{down_price}, UP最佳:{up_price}")
                self.play_order(conditionId,token_id=row["token-no"],price=down_price,size=self.order_count)
            else:
                self.logger.warning(f" "*20) 
                self.logger.info(f"==>价格不满足，跳过!{slug}")   
                continue    
    def play_order(self,conditionId:str,token_id:str=None,price:float=None,size:float=None ):
        trades= get_trades(self.settings,market=conditionId)     
        if len(trades) != 0:
            trade = trades[0]
            self.logger.warning(f"==>> 交易记录存在：{trade['id']},{trade['side']},{trade['price']},{trade['size']},跳过下单")   
            return
        curr_balance =get_balance(self.settings)

        if curr_balance < self.settings.reserve_balance + self.settings.order_size:
            self.logger.warning(f"===> ⚠️ 余额不足，当前余额: ${curr_balance:.6f},保留余额: ${self.settings.reserve_balance:.6f},跳过下单")
            return
        place_order(
            self.settings,
            side="BUY",
            token_id=token_id,
            price=float(price),
            size=float(size),
            tif="GTC",
        )
        self.logger.warning(f"===>提交订单:   {token_id}, ${price:.4f} x {size} shares")

    def run(self):


        # place_order(
        #     self.settings,
        #     side="BUY",
        #     token_id='67907923640754422536549983884687639959795729031667929337463354290420556044100',
        #     price=float(0.05),
        #     size=float(5),
        #     tif="FAK",
        # )
        # return

        # place_order(
        #     self.settings,
        #     side="BUY",
        #     token_id='104663890405767427718480543493833762398617970079292208022284840939078090957432',
        #     price=float(0.72),
        #     size=float(2),
        #     tif="GTC",
        # )
        try:

            curr_balance =get_balance(self.settings)
            self.logger.info(f"   💰 当前余额: ${curr_balance:.6f},预留金额:{self.settings.reserve_balance}")

            #   trades= get_trades(self.settings) market =>condition
            #   self.trades = pd.DataFrame( trades,columns=['id','market','asset_id','side','size','price','status','outcome'])
            start_date, end_date = self.get_dates()
            lens=1
            self.logger.info(f"==> 启动扫描,{start_date},{end_date}")   
            page=0
            limit =500 
            while lens > 0 :
                params = {
                        'limit': limit,
                        'offset': page * limit,
                        'order':'id',
                        'ascending':'true',
                        'closed': 'false',
                        'end_date_min':start_date,
                        'end_date_max':end_date
                    }
                response = self.http_client.get('https://gamma-api.polymarket.com/markets',params=params)
                # 检查请求是否成功
                if response.status_code == 200:
                    data = response.json()

                    columns = ['id', 'slug', 'startDate','events','conditionId', 'endDate','clobTokenIds','outcomes','sportsMarketType']
                    df = pd.DataFrame(data,columns=columns)
                    lens=len(df)
                    self.logger.info(f"==> 查询第{page+1}页数据】数量:{lens}")   
                    self.reslove(df)
                    page += 1
                else:
                    self.logger.error(f"请求失败，状态码: {response.status_code}, 响应内容: {response.text}")
                    break
        except Exception as e:
            self.logger.info(f"完整异常: {e.__class__.__name__}: {e}",exc_info=True)
                           
if __name__ == "__main__":
    logName= "poly-scan"
    settings = load_settings()
    runnerHelper=RunnerHelper() 
    logConfig=runnerHelper.getLogConfig(logName)
    logging.config.dictConfig(logConfig)
    logger =  logging.getLogger(logName)

    runner=SeekPolymarket(logger,settings) 

    # runner.run()
   
    scheduler = BlockingScheduler()
    # Thread(target=runnerHelper.print_countdown, args=(scheduler,logger), daemon=True).start()
    # scheduler.add_job(runner.run, 'cron', second='1,31',name='polymarket')
    scheduler.add_job(runner.run, 'interval', minutes=1, name=logName,next_run_time=datetime.now() )
    scheduler.start()

