
import logging
import logging.config
from datetime import datetime, timedelta,timezone,time
import time
import os

class RunnerHelper:

    def __init__(self):
        # 创建日志目录
        self.log_dir = "logs"
        os.makedirs(self.log_dir, exist_ok=True)
        # 生成带时间戳的日志文件名
    def getLogConfig(self,logName):
        timestamp = datetime.now().strftime("%Y%m%d_%H")
        log_dir=self.log_dir
        logConfig = {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                # 控制台格式（简洁）
                'console_format': {
                    'format': '%(asctime)s %(name)8s %(levelname)8s %(message)s',
                    'datefmt': '%H:%M:%S'
                },
                # 文件格式（详细）
                'file_format': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S'
                },
                # 统一格式（同时输出到控制台和单个文件）
                'detailed': {
                    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    'datefmt': '%Y-%m-%d %H:%M:%S'
                }
            },
            'handlers': {
                # 控制台处理器
                'console': {
                    'class': 'logging.StreamHandler',
                    'formatter': 'console_format',
                    'level': 'INFO',
                    'stream': 'ext://sys.stdout'
                },
                # file1单独的文件
                'info_file': {
                    'class': 'logging.handlers.TimedRotatingFileHandler',
                    'filename': f'{log_dir}/{logName}-info.log',
                    'when': 'H',  # 按小时轮转
                    'interval': 1,  # 每1小时
                    'backupCount': 24,  # 保留24个文件（1天）
                    'formatter': 'file_format',
                    'level': 'INFO',
                },
                'warn_file': {
                    'class': 'logging.handlers.TimedRotatingFileHandler',
                    'filename': f'{log_dir}/{logName}-warn.log',
                    'when': 'H',  # 按小时轮转
                    'interval': 1,  # 每1小时
                    'backupCount': 24,  # 保留24个文件（1天）
                    'formatter': 'file_format',
                    'level': 'WARNING',
                },
                'error_file': {
                    'class': 'logging.handlers.TimedRotatingFileHandler',
                    'filename': f'{log_dir}/{logName}-error.log',
                    'when': 'H',
                    'interval': 1,
                    'backupCount': 24,
                    'formatter': 'file_format',
                    'level': 'ERROR',
                }
            },
            
            'loggers': {
                f'{logName}': {
                    'handlers': ['console', 'info_file','warn_file', 'error_file'],
                    'level': 'INFO',
                    'propagate': False  # 防止重复记录
                },
                'main': {
                    'handlers': ['console','error_file'],
                    'level': 'INFO',
                    'propagate': False
                },
            },
            # 根记录器配置（捕获其他未明确配置的logger）
            'root': {
                'handlers': ['console', 'error_file'],
                'level': 'WARNING'
            }
        }
        return logConfig;
      
    def print_countdown(self,scheduler,logger):
        while True:
            jobs = scheduler.get_jobs()
            if jobs:
                msg =""
                for job in jobs:
                    now = datetime.now(scheduler.timezone) if scheduler.timezone else datetime.now()
                    next_run_time = job.trigger.get_next_fire_time(None, now)
                    if next_run_time:
                        time_left = (next_run_time - now).total_seconds()
                        if time_left > 0:
                            # msg = msg + f"【{job.name} @ {next_run_time.strftime('%Y-%m-%d-%H:%M:%S')}: {int(time_left)} 秒】"
                            msg = msg + f"【{job.name} : {int(time_left)} 秒】"
                            # print(f"\r下次开始执行【{next_run_time.strftime("%Y-%m-%d %H:%M:%S")}】倒计时: {int(time_left)} 秒",end="", flush=True) 
                time.sleep(1)
                logger.info(msg)
