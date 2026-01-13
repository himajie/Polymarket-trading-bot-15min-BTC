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
from .logger import setup_logging, print_header, print_success, print_error
from threading import Thread
from .runner_utils import RunnerHelper
from .trading import (
    get_client,
    place_order,
    get_positions,
    place_orders_fast,
    extract_order_id,
    wait_for_terminal_order,
    cancel_orders,
)

class SeekPolymarket():
    def __init__(self,logger,settings):
        self.settings = settings
        self.client = get_client(settings)
        self.logger=logger 
        self.delay_seconds=2 * 24 * 60 * 60
        CLIENT_CONFIG = {
            'rate_limit_seconds': 0.05,
            'timeout': 30,
            'headers': {
                'User-Agent': 'MyApp/1.0',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
        }
        # 获取全局客户端实例
        self.http_client = ConfigurableHTTPClient.get_instance(CLIENT_CONFIG)
        settings = load_settings()
        # Setup logging with proper verbosity
        setup_logging(verbose=settings.verbose, use_rich=settings.use_rich_output)


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


    def get_order_book(self, token_id: str) -> dict:
        try:
            book = self.client.get_order_book(token_id=token_id)
            # The result is an OrderBookSummary object, not a dict
            bids = book.bids if hasattr(book, 'bids') and book.bids else []
            asks = book.asks if hasattr(book, 'asks') and book.asks else []

            bid_levels = self._levels_to_tuples(bids)
            ask_levels = self._levels_to_tuples(asks)

            best_bid = max((p for p, _ in bid_levels), default=None)
            best_ask = min((p for p, _ in ask_levels), default=None)

            bid_size = 0.0
            if best_bid is not None:
                for p, s in bid_levels:
                    if p == best_bid:
                        bid_size = s
                        break

            ask_size = 0.0
            if best_ask is not None:
                for p, s in ask_levels:
                    if p == best_ask:
                        ask_size = s
                        break

            spread = (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None

            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "bids": bid_levels,
                "asks": ask_levels,
            }
        except Exception as e:
            logger.error(f"Error getting order book: {e}")
            logger.exception("Full traceback:") 
            return {}

    # async def _fetch_order_books_parallel(self,yes_token_id,no_token_id) -> tuple[dict, dict]:
    #     try:
    #         up_task = asyncio.to_thread(self.get_order_book, yes_token_id)
    #         down_task = asyncio.to_thread(self.get_order_book, no_token_id)
    #         up_book, down_book = await asyncio.gather(up_task, down_task)
    #         return up_book, down_book
    #     except Exception as e:
    #         logger.warning(f"Parallel order book fetch failed, falling back to sequential: {e}")
    #         return self.get_order_book(self.yes_token_id), self.get_order_book(self.no_token_id)
        
    def get_multiple_price(self,tokens):
        request_body=[{"token_id": token, "side": "SELL"} for token in tokens]
        response = requests.post(
            url="https://clob.polymarket.com/prices",
            headers={"Content-Type": "application/json"},
            json=request_body,
            timeout=30  # 设置超时
        )
        response.raise_for_status() 
        price_map = {token_id: round( 1.0/float(data['SELL']),4) for token_id, data in response.json().items()}
        return price_map
    
    def get_price(self,token):
        params = {
                        'token_id': token,
                        'side': 'SELL'
                    }
        response = self.http_client.get('https://clob.polymarket.com/price',params=params)
        response.raise_for_status() 
        # price_map = {token_id: round( 1.0/float(data['SELL']),4) for token_id, data in response.json().items()}
        return  float(response.json().get('price',None))

    def reslove(self,dfs):

        df = dfs.explode('events')
        current_time = pd.Timestamp.now(tz='UTC')
        df['datetime'] = pd.to_datetime(df['endDate'], utc=True) 
        time_diff = current_time - df['datetime']
        # 结束时间大于3分钟且小于等于30分钟
        mask = (time_diff > pd.Timedelta(minutes=3)) & (time_diff <= pd.Timedelta(minutes=300))
        df = df[mask]
        if df.empty:
            self.logger.info("【无符合条件的数据】")   
            return
        
        # df[['token-yes', 'token-no']] = df['clobTokenIds'].apply(lambda x: pd.Series(x) if isinstance(x, list) else pd.Series([None, None]))
        df['clobTokens'] = df['clobTokenIds'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)

        df['event_slug'] = df['events'].apply(lambda x: x.get('slug') if isinstance(x, dict) else None)

        # new_cols = pd.DataFrame(df['clobTokenIds'].tolist(), columns=['token-yes', 'token-no'])
        # df[['token-yes', 'token-no']] = new_cols[['token-yes', 'token-no']]         
        df[['token-yes', 'token-no']] = df['clobTokens'].apply(lambda x: pd.Series([x[0], x[1]] if isinstance(x, list) and len(x) >= 2 else [None, None]))
        for index, row in df.iterrows():
            # 查询数据库id订单是否存在
            id =row["id"]
            slug=row["event_slug"]

            up_price=self.get_price(row["token-yes"])
            down_price=self.get_price(row["token-no"])
            if up_price is None or down_price is None:
                continue


            if up_price > 0.95 and up_price <= 0.99:
                self.logger.warning(f"==>> 市场ID: {id}/【{slug} 】 UP最佳:{up_price},DOWN最佳:{down_price}")
            elif down_price > 0.95 and down_price <= 0.99:
                self.logger.warning(f"==>> 市场ID: {id}/【{slug} 】 UP最佳:{up_price},DOWN最佳:{down_price}")
            else:
                continue    
            
            # up_book, down_book = await self._fetch_order_books_parallel(row["token-yes"], row["token-no"])
            
            # if up_book is None or down_book is None:
            #     # self.logger.warning(f"无法获取市场ID: {id}的订单簿数据，跳过该市场。")
            #     continue   
            # if 'spread' not in up_book or 'spread' not in down_book:
            #     continue    
            # if up_book['spread'] is None or down_book['spread'] is None:
            #     # self.logger.warning(f"市场ID: {id}的订单簿数据不完整，跳过该市场。")
            #     continue    
            # if up_book['spread'] > 0.03 or down_book['spread'] > 0.03:
            #     # self.logger.info(f"市场ID: {id}的买卖差价过大，跳过该市场。spread_up:{up_book['spread']},spread_down:{down_book['spread']}")
            #     continue    

            

            # if up_book['best_ask'] > 0.95 and up_book['best_ask'] <= 0.99:
            #     self.logger.warning(f"==>> 市场ID: {id}/{slug}  UP最佳:{up_book['best_ask']},DOWN最佳:{down_book['best_ask']},spread_up:{up_book['spread']},spread_down:{down_book['spread']},UP_size:{up_book['ask_size']},DOWN_size:{down_book['ask_size']}")
            # elif down_book['best_ask'] > 0.95 and down_book['best_ask'] <= 0.99:
            #     self.logger.warning(f"==>> 市场ID: {id}/{slug}  UP最佳:{up_book['best_ask']},DOWN最佳:{down_book['best_ask']},spread_up:{up_book['spread']},spread_down:{down_book['spread']},UP_size:{up_book['ask_size']},DOWN_size:{down_book['ask_size']}")
            # else:
            #     continue





        
    def run(self):
        try:
            start_date, end_date = self.get_dates()
            lens=1
            self.logger.info(f"【启动】polymarket,{start_date},{end_date}")   
            page=0
            limit =200 
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

                    columns = ['id', 'slug', 'startDate','events', 'endDate','clobTokenIds','outcomes']
                    df = pd.DataFrame(data,columns=columns)
                    lens=len(df)
                    self.reslove(df)
                    self.logger.info(f"【polymarket-第{page+1}页数据】数量:{lens}")   
                    page += 1
                else:
                    self.logger.error(f"请求失败，状态码: {response.status_code}, 响应内容: {response.text}")
                    break
        except Exception as e:
            self.logger.info(f"完整异常: {e.__class__.__name__}: {e}",exc_info=True)
                           
if __name__ == "__main__":
 
    settings = load_settings()
    runnerHelper=RunnerHelper() 
    logger=  logging.getLogger(__name__)
    runner=SeekPolymarket(logger,settings) 

    runner.run()
   
    # scheduler = BlockingScheduler()
    # Thread(target=runnerHelper.print_countdown, args=(scheduler,logger), daemon=True).start()
    # scheduler.add_job(runner.run, 'cron', second='1,31',name='polymarket')
    # scheduler.start()

