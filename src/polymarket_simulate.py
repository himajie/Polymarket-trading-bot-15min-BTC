import os
import time
import requests
import asyncio
import logging
import json
import pytz
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
from .mysql_db_utils import MySQLHelper
from .trading import (
    get_client,
    place_order,
    get_positions,
    place_orders_fast,
    extract_order_id,
    wait_for_terminal_order,
    cancel_orders,
    get_trades
)

class SeekPolymarket():
    def __init__(self,logger,settings,dbHelper):
        self.dbHelper=dbHelper
        self.settings = settings
        self.client = get_client(settings)
        self.event_tags = ['21']
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
            return  float(response.json().get('price',None))
        except Exception as e:
            return float(0)
            pass
    def get_event_tags(self,event_id):
        try:
            params = {}
            response = self.http_client.get(f'https://gamma-api.polymarket.com/events/{event_id}/tags',params=params)
            response.raise_for_status() 
            df=pd.DataFrame(response.json(),columns=['id','label'])
            if df.empty:
                return []
            return df['id'].drop_duplicates().tolist()
        except Exception as e:
            return []
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

        df = df[(df['end_second'] > self.settings.scan_befor_sec) & (df['end_second'] < self.settings.scan_after_sec) ] #最后3分钟
        if df.empty:
            self.logger.info("==>>无符合条件的数据")  
            return 
        
        df['clobTokens'] = df['clobTokenIds'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
        df['event_slug'] = df['events'].apply(lambda x: x.get('slug') if isinstance(x, dict) else None)    
        df['event_id'] = df['events'].apply(lambda x: x.get('id') if isinstance(x, dict) else None)    
        df[['token-yes', 'token-no']] = df['clobTokens'].apply(lambda x: pd.Series([x[0], x[1]] if isinstance(x, list) and len(x) >= 2 else [None, None]))

        df = df.reset_index(drop=True)
        df=df.loc[df.groupby('id')['end_time'].idxmax()]
        df = df.reset_index(drop=True)

        df = df.drop(df[df['sportsMarketType'].notna()].index)
        if df.empty:
            return
        
        for index, row in df.iterrows():
            # 查询数据库id订单是否存在
            id =row["id"]
            slug=row["event_slug"]
            conditionId=row["conditionId"]
            event_id=row['event_id']
            tags =  self.get_event_tags(event_id)
            start_time_iso= row['start_time']
            end_date_iso= row['end_time']
            if not any(tag in self.event_tags for tag in tags):
                continue
            
            up_price=self.get_price(row["token-yes"])
            down_price=self.get_price(row["token-no"])
            if up_price is None or down_price is None:
                self.logger.info(f"==>价格错误，跳过")   
                continue

            if up_price > self.settings.price_min and up_price <= self.settings.price_max:
                self.logger.warning(f" "*20)  
                self.logger.warning(f"---------------------------------------------------")  
                self.logger.warning(f"=========>> 价格满足，准备下单!{slug}   << ============")  
                self.logger.warning(f"==>> 市场ID: {id}/【{slug} 】 UP最佳:{up_price}, DOWN最佳:{down_price}")
                self.play_order(conditionId,token_id=row["token-yes"],price=up_price,size=self.settings.order_size,slug=slug,start_time_iso=start_time_iso,end_date_iso=end_date_iso,symbol='UP')
            elif down_price > self.settings.price_min and down_price <= self.settings.price_max:
                self.logger.warning(f" "*20)  
                self.logger.warning(f"---------------------------------------------------")  
                self.logger.warning(f"=========>> 价格满足，准备下单!{slug}   << ============")  
                self.logger.warning(f"==>> 市场ID: {id}/【{slug} 】 DOWN最佳:{down_price}, UP最佳:{up_price}")
                self.play_order(conditionId,token_id=row["token-no"],price=down_price,size=self.settings.order_size,slug=slug,start_time_iso=start_time_iso,end_date_iso=end_date_iso,symbol='DOWN')
            else:
                self.logger.warning(f" "*20) 
                self.logger.info(f"==>价格不满足，跳过!{slug}, DOWN:{down_price}, UP:{up_price}")   
                continue    
    def get_benchmark_price(self, dt: datetime, slug: str) -> float:
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
    def play_order(self,conditionId:str,token_id:str=None,price:float=None,size:float=None ,slug:str=None,start_time_iso:datetime=None,end_date_iso:datetime=None,symbol:str=None):
        orders = self.dbHelper.execute_query("SELECT *  FROM polymarket_trades WHERE market_id=%s ", (conditionId,))
        if len(orders) > 0:
            self.logger.warning(f"==>> 交易记录存在：{slug},{conditionId},跳过下单")   
            return
        utc = pytz.UTC
        current_time_utc=datetime.now(utc)
        current_time=datetime.now()
        benchmark_price=self.get_benchmark_price(current_time_utc, slug)
        db_data={
                    'market_slug':slug,
                    'market_id':conditionId,
                    'token_id':token_id,
                    'crypto_benchmark':benchmark_price,
                    'buy_price':price,
                    'size':size,
                    'status':0,
                    'symbol':symbol,
                    'start_date_iso':start_time_iso,
                    'end_date_iso':end_date_iso,
                    'create_time_iso':current_time_utc,
                    'create_time':current_time
        }
        self.dbHelper.insert_one("polymarket_trades", db_data) 
        self.logger.warning(f"===>提交订单:   {token_id}, ${price:.4f} x {size} shares")

    def run(self):
        try:

            start_date, end_date = self.get_dates()
            self.logger.info(f"==> 启动扫描,{start_date},{end_date}")   
            page=0
            limit =500 
            lens=limit
            while lens == limit :
                params = {
                        'limit': limit,
                        'offset': page * limit,
                        'order':'id',
                        'ascending':'true',
                        'tag_id':21, 
                        'closed': 'false',
                        'end_date_min':start_date,
                        'end_date_max':end_date
                    }
                response = self.http_client.get('https://gamma-api.polymarket.com/markets',params=params)
                # 检查请求是否成功
                if response.status_code == 200:
                    data = response.json()
                    columns = ['id', 'slug', 'startDate','eventStartTime','events','conditionId', 'endDate','clobTokenIds','outcomes','sportsMarketType']
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
    logName= "polymarket_simulate"
    settings = load_settings()
    runnerHelper=RunnerHelper() 
    dbHelper = MySQLHelper()
    logConfig=runnerHelper.getLogConfig(logName)
    logging.config.dictConfig(logConfig)
    logger =  logging.getLogger(logName)

    runner=SeekPolymarket(logger,settings,dbHelper) 

    # runner.run()
   
    scheduler = BlockingScheduler()
    Thread(target=runnerHelper.print_countdown, args=(scheduler,logger), daemon=True).start()
    scheduler.add_job(runner.run, 'interval', seconds=5, name=logName,next_run_time=datetime.now() )
    scheduler.start()

