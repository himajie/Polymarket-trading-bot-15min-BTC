import requests
import time
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any, Generator

class ConfigurableHTTPClient:
    """可配置的限流 HTTP 客户端"""
    
    _instance: Optional['ConfigurableHTTPClient'] = None
    _lock = threading.Lock()
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.rate_limit_seconds = self.config.get('rate_limit_seconds', 1.0)
        self.timeout = self.config.get('timeout', 30)
        
        self.session = requests.Session()
        self.last_request_time = 0
        self.rate_lock = threading.Lock()
        
        # 配置 session
        if 'headers' in self.config:
            self.session.headers.update(self.config['headers'])
        
        if 'auth' in self.config:
            self.session.auth = self.config['auth']
    
    @classmethod
    def get_instance(cls, config: Dict[str, Any] = None) -> 'ConfigurableHTTPClient':
        """获取单例实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance
    
    def _enforce_rate_limit(self):
        """强制执行限流"""
        with self.rate_lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            wait_time = max(0, self.rate_limit_seconds - elapsed)
            
            if wait_time > 0:
                # print(f"限流等待: {wait_time:.2f}秒")
                time.sleep(wait_time)
            
            self.last_request_time = time.time()
    
    @contextmanager
    def request_context(self) -> Generator[requests.Session, None, None]:
        """使用上下文管理器进行请求"""
        self._enforce_rate_limit()
        try:
            yield self.session
        except Exception as e:
            raise e
    
    def get(self, url: str, **kwargs) -> requests.Response:
        with self.request_context():
            return self.session.get(url, timeout=self.timeout, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        with self.request_context():
            return self.session.post(url, timeout=self.timeout, **kwargs)
    
    def make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """通用请求方法"""
        with self.request_context():
            return self.session.request(method, url, timeout=self.timeout, **kwargs)



if __name__ == "__main__":
    # 配置示例
    CLIENT_CONFIG = {
        'rate_limit_seconds': 3,
        'timeout': 30,
        'headers': {
            'User-Agent': 'MyApp/1.0',
            'Accept': 'application/json',
        }
    }

    # 获取全局客户端实例
    http_client = ConfigurableHTTPClient.get_instance(CLIENT_CONFIG)

    for i in range(10):
        params = {
                'limit': 1,
                'offset': 0,
                'timePeriod':'all',
                'category':'overall'
            }
        response = http_client.get('https://data-api.polymarket.com/v1/biggest-winners',params=params)
        print(response)
