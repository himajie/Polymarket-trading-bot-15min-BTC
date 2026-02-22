import asyncio
import json
import websockets
from datetime import datetime, timezone, timedelta
import pytz 
from src.mysql_db_utils import MySQLHelper
import logging
import time

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

dbHelper = MySQLHelper()

class PolymarketWebSocketClient:
    """
    Polymarket WebSocket客户端，带自动重连功能
    """
    
    def __init__(self, max_retries=5, retry_delay=5, initial_retry_delay=1):
        """
        初始化客户端
        
        Args:
            max_retries: 最大重试次数，None表示无限重试
            retry_delay: 重试延迟（秒）
            initial_retry_delay: 初始重试延迟（秒），会逐渐增加
        """
        self.uri = "wss://ws-live-data.polymarket.com"
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.initial_retry_delay = initial_retry_delay
        self.current_retry_delay = initial_retry_delay
        self.retry_count = 0
        self.running = False
        self.websocket = None
        
        # 订阅消息配置
        self.subscribe_message = {
            "action": "subscribe",
            "subscriptions": [
                {
                    "topic": "crypto_prices",
                    "type": "update",
                    "filters": '{\"symbol\":\"btcusdt\"},{\"symbol\":\"solusdt\"},{\"symbol\":\"xrpusdt\"},{\"symbol\":\"ethusdt\"}'
                }
            ]
        }
    
    async def connect(self):
        """建立WebSocket连接并处理重连逻辑"""
        self.running = True
        
        while self.running:
            try:
                logger.info(f"正在连接到 {self.uri} (重试次数: {self.retry_count})")
                
                async with websockets.connect(
                    self.uri, 
                    ping_interval=30, 
                    ping_timeout=10,
                    close_timeout=5
                ) as websocket:
                    
                    self.websocket = websocket
                    self.current_retry_delay = self.initial_retry_delay  # 连接成功后重置重试延迟
                    self.retry_count = 0
                    
                    # 发送订阅消息
                    logger.info("发送订阅消息")
                    await websocket.send(json.dumps(self.subscribe_message))
                    
                    # 监听消息
                    await self.listen_messages(websocket)
                    
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"连接已关闭: {e}")
                await self.handle_disconnect(e)
                
            except websockets.exceptions.ConnectionClosedOK as e:
                logger.info(f"连接正常关闭: {e}")
                await self.handle_disconnect(e)
                
            except Exception as e:
                logger.error(f"连接错误: {e}")
                await self.handle_disconnect(e)
    
    async def handle_disconnect(self, error):
        """处理断开连接，实现重连逻辑"""
        self.websocket = None
        
        # 检查是否应该重试
        if self.max_retries is not None and self.retry_count >= self.max_retries:
            logger.error(f"已达到最大重试次数 {self.max_retries}，停止重连")
            self.running = False
            return
        
        # 计算下次重试的延迟（指数退避）
        if self.retry_count > 0:
            self.current_retry_delay = min(
                self.current_retry_delay * 1.5,  # 指数退避因子
                self.retry_delay  # 最大延迟
            )
        
        self.retry_count += 1
        logger.info(f"等待 {self.current_retry_delay:.1f} 秒后重试... (重试 {self.retry_count}/{self.max_retries if self.max_retries else '无限'})")
        
        # 等待后重连
        await asyncio.sleep(self.current_retry_delay)
    
    async def listen_messages(self, websocket):
        """监听并处理接收到的消息"""
        logger.info("开始监听消息...")
        
        async for message in websocket:
            try:
                if not message or message.strip() == "":
                    logger.debug("收到空消息")
                    continue
                    
                # 解析JSON消息
                message_data = json.loads(message)
                
                # 跳过订阅确认消息
                if message_data.get('type', '') == 'subscribe':
                    continue
                
                # 处理价格数据
                await self.resolve_price(message_data)
                
            except json.JSONDecodeError as e:
                logger.error(f"消息解析错误: {e}")
                logger.debug(f"原始消息: {message}")
            except Exception as e:
                logger.error(f"处理消息时出错: {e}", exc_info=True)
    
    async def resolve_price(self, json_data):
        """解析价格数据并存储到数据库"""
        try:
            payload = json_data.get('payload', {})
            if not payload:
                logger.warning("消息中没有payload字段")
                return
                
            price = payload.get('value')
            symbol = payload.get('symbol')
            timestamp = payload.get('timestamp')
            
            if price is None or symbol is None or timestamp is None:
                logger.warning(f"消息字段不完整: {payload}")
                return
            
            timestamp_sec = int(timestamp) / 1000.0
            
            # 获取时区
            utc_tz = timezone.utc
            shanghai_tz = pytz.timezone('Asia/Shanghai')
            
            # UTC时间
            utc_dt = datetime.fromtimestamp(timestamp_sec, tz=utc_tz)
            # 上海时间
            shanghai_dt = utc_dt.astimezone(shanghai_tz)
            
            db_data = {
                'symbol': symbol,
                'price': price,
                'create_time_iso': utc_dt,
                'create_time': shanghai_dt
            }
            # 插入数据库
            dbHelper.insert_one("polymarket_crypto_price", db_data)
            # print(db_data)
            # 可选：打印日志
            logger.debug(f"{symbol}: {price}")
            
        except Exception as e:
            logger.error(f"解析价格数据时出错: {e}", exc_info=True)
    
    async def disconnect(self):
        """断开连接"""
        self.running = False
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
    
    async def send_heartbeat(self):
        """可选：发送心跳包保持连接活跃"""
        while self.running:
            try:
                if self.websocket and not self.websocket.closed:
                    # 发送ping消息
                    await self.websocket.ping()
                    logger.debug("发送心跳包")
            except Exception as e:
                logger.debug(f"发送心跳包失败: {e}")
            
            # 每30秒发送一次心跳
            await asyncio.sleep(30)


async def main():
    """
    主函数 - 运行WebSocket客户端
    """
    print("Polymarket WebSocket 客户端启动（带自动重连）")
    print("=" * 60)
    
    # 创建客户端实例
    # 参数说明：
    # max_retries=None  # 无限重试
    # max_retries=5     # 最大重试5次
    client = PolymarketWebSocketClient(
        max_retries=None,  # 无限重试
        retry_delay=10,    # 最大重试间隔10秒
        initial_retry_delay=1  # 初始重试间隔1秒
    )
    
    try:
        # 运行客户端
        await client.connect()
    except KeyboardInterrupt:
        logger.info("用户中断程序")
    except Exception as e:
        logger.error(f"程序异常: {e}", exc_info=True)
    finally:
        # 确保断开连接
        await client.disconnect()
        logger.info("程序结束")


def run_client():
    """运行客户端（入口函数）"""
    print("注意：请确保已安装 websockets 库")
    print("安装命令: pip install websockets")
    print("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n程序已被用户中断")
    except Exception as e:
        print(f"程序异常: {e}")


if __name__ == "__main__":
    run_client()