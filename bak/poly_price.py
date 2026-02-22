import asyncio
import json
import websockets
from datetime import datetime, timezone, timedelta
import pytz 
from src.mysql_db_utils import MySQLHelper



dbHelper = MySQLHelper()
async def polymarket_websocket_client():
    """
    Polymarket WebSocket客户端
    订阅实时数据并打印接收到的消息
    """
    uri = "wss://ws-live-data.polymarket.com"
    
    # 订阅消息配置
    # 如果不需要过滤器，可以直接去掉 filters 字段
    # 如果需要过滤器，必须是有效的 JSON 字符串
    subscribe_message = {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": "crypto_prices",  # 修正：通常使用 markets 而不是 crypto_prices
                "type": "update",  # 这个是正确的
                 "filters": '{\"symbol\":\"BTCUSDT\"},{\"symbol\":\"solusdt\"}'
                # "filters":'{"symbol":"btcusdt"},{"symbol":"solusdt"}'
            }
        ]
    }
    
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 正在连接到 {uri}")
        
        async with websockets.connect(uri, ping_interval=30, ping_timeout=10) as websocket:
            # 发送订阅消息
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送订阅消息:")
            print(json.dumps(subscribe_message, indent=2))
            
            await websocket.send(json.dumps(subscribe_message))
            
            # 监听并打印接收到的消息
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始监听消息...")
            print("-" * 50)
            
            async for message in websocket:
                try:

                    if not message or message.strip() == "":
                        print("收到空消息")
                        continue
                    # 解析JSON消息
                    message_data = json.loads(message)
                    if message_data.get('type','') == 'subscribe':
                        continue
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    await reslove_price(message_data)
                    # print(f"[{timestamp}] 收到消息:")
                    # print(json.dumps(message_data, indent=2))
                    # print("-" * 30)
                    
                except json.JSONDecodeError as e:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 消息解析错误: {e}")
                    print(f"原始消息: {message}")
                    
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 连接已关闭: {e}")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发生错误: {e}")

async def reslove_price(json_data):
    payload = json_data['payload']
    price = payload['value']
    symbol = payload['symbol']
    timestamp= int(payload['timestamp'])
    timestamp_sec = timestamp / 1000.0
    # 获取时区
    utc_tz = timezone.utc
    shanghai_tz = pytz.timezone('Asia/Shanghai')
    # UTC时间
    utc_dt = datetime.fromtimestamp(timestamp_sec, tz=utc_tz)
    # 上海时间
    shanghai_dt = utc_dt.astimezone(shanghai_tz)

    db_data={
                    'symbol':symbol,
                    'price':price,
                    'create_time_iso':utc_dt,
                    'create_time':shanghai_dt
    }
    print(symbol,price)
    dbHelper.insert_one("polymarket_crypto_price", db_data) 

def main():
    """
    主函数 - 运行WebSocket客户端
    """
    print("Polymarket WebSocket 客户端启动")
    print("注意：请确保已安装 websockets 库")
    print("安装命令: pip install websockets")
    print("=" * 60)
    
    try:
        # 运行异步客户端
        asyncio.run(polymarket_websocket_client())
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 用户中断程序")
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 程序异常: {e}")

if __name__ == "__main__":
    main()