#!/bin/bash

# start.sh
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$APP_DIR/logs/risk.log"
PID_FILE="$APP_DIR/risk.pid"

start_app() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "应用已经在运行中 (PID: $(cat $PID_FILE))"
        exit 1
    fi
    
    echo "启动应用..."
    # nohup python3 "$APP_DIR/scanner_mq.py" >> "$LOG_FILE" 2>&1 &
    nohup python -m src.risk_poly > /dev/null 2>&1 &
    echo $! > "$PID_FILE"
    echo "应用已启动 (PID: $(cat $PID_FILE))"
}

stop_app() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            echo "停止应用 (PID: $PID)..."
            kill $PID
            rm "$PID_FILE"
            echo "应用已停止"
        else
            echo "PID文件存在但进程不存在，清理PID文件"
            rm "$PID_FILE"
        fi
    else
        echo "应用未运行"
    fi
}

status_app() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "应用运行中 (PID: $(cat $PID_FILE))"
    else
        echo "应用未运行"
    fi
}

case "$1" in
    start)
        start_app
        ;;
    stop)
        stop_app
        ;;
    restart)
        stop_app
        sleep 2
        start_app
        ;;
    status)
        status_app
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac