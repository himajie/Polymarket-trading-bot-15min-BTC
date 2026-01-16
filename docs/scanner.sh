#!/bin/bash

# start.sh
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$APP_DIR/apps.conf"
LOG_DIR="$APP_DIR/logs"
PID_DIR="$APP_DIR/pids"

# 创建必要的目录
mkdir -p "$LOG_DIR" "$PID_DIR"

# 应用配置文件格式：应用名:模块路径
# 示例：
# order_scan:src.polymarket
# risk_scan:src.risk_poly

load_apps() {
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "配置文件 $CONFIG_FILE 不存在"
        exit 1
    fi
    # 过滤空行和注释行
    grep -v -E '^$|^#' "$CONFIG_FILE"
}

start_app() {
    local app_name="$1"
    local module_path="$2"
    local pid_file="$PID_DIR/${app_name}.pid"
    local log_file="$LOG_DIR/${app_name}.log"
    
    if [ -f "$pid_file" ] && kill -0 $(cat "$pid_file") 2>/dev/null; then
        echo "应用 $app_name 已经在运行中 (PID: $(cat $pid_file))"
        return 1
    fi
    
    echo "启动应用 $app_name (模块: $module_path)..."
    # 使用python -m方式运行模块
    nohup python3 -m "$module_path" > "$log_file" 2>&1 &
    local pid=$!
    echo $pid > "$pid_file"
    echo "应用 $app_name 已启动 (PID: $pid, 日志: $log_file)"
}

stop_app() {
    local app_name="$1"
    local pid_file="$PID_DIR/${app_name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            echo "停止应用 $app_name (PID: $pid)..."
            kill $pid
            # 等待进程结束
            sleep 2
            if kill -0 $pid 2>/dev/null; then
                echo "进程仍在运行，发送SIGKILL强制终止..."
                kill -9 $pid
            fi
            rm "$pid_file"
            echo "应用 $app_name 已停止"
        else
            echo "PID文件存在但进程不存在，清理PID文件"
            rm "$pid_file"
        fi
    else
        echo "应用 $app_name 未运行"
    fi
}

status_app() {
    local app_name="$1"
    local pid_file="$PID_DIR/${app_name}.pid"
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 $pid 2>/dev/null; then
            echo "应用 $app_name 运行中 (PID: $pid)"
            # 显示进程信息
            ps -p $pid -o pid,cmd,etimes | tail -n +2
        else
            echo "应用 $app_name PID文件存在但进程已停止 (PID: $pid)"
            rm "$pid_file" 2>/dev/null
        fi
    else
        echo "应用 $app_name 未运行"
    fi
}

start_all() {
    echo "启动所有应用..."
    load_apps | while IFS=':' read -r app_name module_path; do
        if [ -n "$app_name" ] && [ -n "$module_path" ]; then
            start_app "$app_name" "$module_path"
        fi
    done
}

stop_all() {
    echo "停止所有应用..."
    for pid_file in "$PID_DIR"/*.pid; do
        if [ -f "$pid_file" ]; then
            local app_name=$(basename "$pid_file" .pid)
            stop_app "$app_name"
        fi
    done
}

restart_all() {
    echo "重启所有应用..."
    stop_all
    sleep 3
    start_all
}

status_all() {
    echo "应用状态："
    if ls "$PID_DIR"/*.pid >/dev/null 2>&1; then
        for pid_file in "$PID_DIR"/*.pid; do
            local app_name=$(basename "$pid_file" .pid)
            status_app "$app_name"
        done
    else
        echo "没有应用在运行"
    fi
}

# 获取应用配置
get_app_config() {
    local app_name="$1"
    local line=$(grep "^${app_name}:" "$CONFIG_FILE")
    if [ -n "$line" ]; then
        IFS=':' read -r found_name module_path <<< "$line"
        echo "$module_path"
    else
        echo ""
    fi
}

case "$1" in
    start)
        if [ -n "$2" ]; then
            # 启动单个应用
            module_path=$(get_app_config "$2")
            if [ -n "$module_path" ]; then
                start_app "$2" "$module_path"
            else
                echo "应用 $2 未在配置文件中定义"
                echo "可用的应用:"
                load_apps | while IFS=':' read -r app_name module_path; do
                    echo "  $app_name"
                done
            fi
        else
            start_all
        fi
        ;;
    stop)
        if [ -n "$2" ]; then
            # 停止单个应用
            module_path=$(get_app_config "$2")
            if [ -n "$module_path" ]; then
                stop_app "$2"
            else
                echo "应用 $2 未在配置文件中定义"
                echo "可用的应用:"
                load_apps | while IFS=':' read -r app_name module_path; do
                    echo "  $app_name"
                done
            fi
        else
            stop_all
        fi
        ;;
    restart)
        if [ -n "$2" ]; then
            # 重启单个应用
            module_path=$(get_app_config "$2")
            if [ -n "$module_path" ]; then
                echo "重启应用 $2..."
                stop_app "$2"
                sleep 2
                start_app "$2" "$module_path"
            else
                echo "应用 $2 未在配置文件中定义"
                echo "可用的应用:"
                load_apps | while IFS=':' read -r app_name module_path; do
                    echo "  $app_name"
                done
            fi
        else
            restart_all
        fi
        ;;
    status)
        if [ -n "$2" ]; then
            # 查看单个应用状态
            module_path=$(get_app_config "$2")
            if [ -n "$module_path" ]; then
                status_app "$2"
            else
                echo "应用 $2 未在配置文件中定义"
                echo "可用的应用:"
                load_apps | while IFS=':' read -r app_name module_path; do
                    echo "  $app_name"
                done
            fi
        else
            status_all
        fi
        ;;
    logs)
        if [ -n "$2" ]; then
            # 查看应用日志
            module_path=$(get_app_config "$2")
            if [ -n "$module_path" ]; then
                local log_file="$LOG_DIR/${2}.log"
                if [ -f "$log_file" ]; then
                    echo "显示 $2 应用日志 (Ctrl+C 退出):"
                    echo "----------------------------------------"
                    tail -f "$log_file"
                else
                    echo "日志文件不存在: $log_file"
                fi
            else
                echo "应用 $2 未在配置文件中定义"
            fi
        else
            echo "用法: $0 logs [app_name]"
            echo "可用的应用:"
            load_apps | while IFS=':' read -r app_name module_path; do
                echo "  $app_name"
            done
        fi
        ;;
    list)
        echo "已配置的应用："
        load_apps | while IFS=':' read -r app_name module_path; do
            echo "  $app_name: python -m $module_path"
        done
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|logs|list} [app_name]"
        echo "命令说明:"
        echo "  start [app]    启动所有应用或指定应用"
        echo "  stop [app]     停止所有应用或指定应用"
        echo "  restart [app]  重启所有应用或指定应用"
        echo "  status [app]   查看应用状态"
        echo "  logs [app]     查看应用日志（实时）"
        echo "  list           列出所有配置的应用"
        echo ""
        echo "示例:"
        echo "  $0 start                   # 启动所有应用"
        echo "  $0 start order_scan        # 启动order_scan应用"
        echo "  $0 stop                    # 停止所有应用"
        echo "  $0 status                  # 查看所有应用状态"
        echo "  $0 status risk_scan        # 查看risk_scan应用状态"
        echo "  $0 logs order_scan         # 查看order_scan应用日志"
        echo "  $0 list                    # 列出所有配置的应用"
        exit 1
        ;;
esac