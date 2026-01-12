log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H")
log_name='simple_arb_bot'
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
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'console_format',
            'level': 'INFO',
            'stream': 'ext://sys.stdout'
        },
        'info_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': f'{log_dir}/{log_name}-info.log',
            'when': 'H',  # 按小时轮转
            'interval': 1,  # 每1小时
            'backupCount': 24,  # 保留24个文件（1天）
            'formatter': 'file_format',
            'level': 'INFO',
        },
            'warn_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': f'{log_dir}/{log_name}-warn.log',
            'when': 'H',  # 按小时轮转
            'interval': 1,  # 每1小时
            'backupCount': 24,  # 保留24个文件（1天）
            'formatter': 'file_format',
            'level': 'INFO',
        },
        'error_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': f'{log_dir}/{log_name}-error.log',
            'when': 'H',
            'interval': 1,
            'backupCount': 24,
            'formatter': 'file_format',
            'level': 'ERROR',
        }
    },
    
    'loggers': {
        f'{log_name}': {
            'handlers': ['console', 'info_file', 'warn_file', 'error_file'],
            'level': 'INFO',
            'propagate': False  # 防止重复记录
        }
    },
    # 根记录器配置（捕获其他未明确配置的logger）
    'root': {
        'handlers': ['console', 'info_file', 'warn_file', 'error_file'],
        'level': 'INFO'
    }
}
logging.config.dictConfig(logConfig)
logger=  logging.getLogger(log_name)