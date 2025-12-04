#!/bin/bash

# 项目工作目录
PROJECT_DIR="/www/wwwroot/discord-2"
# 你的脚本文件名
SCRIPT_NAME="2.py"

# 检查进程是否在运行
# pgrep -f "python ${SCRIPT_NAME}" 会查找包含 "python 2.py" 字符串的进程
if ! pgrep -f "python ${SCRIPT_NAME}" > /dev/null
then
    echo "脚本未运行，正在重启..."
    # 进入项目目录，使用 nohup 重新启动脚本
    cd ${PROJECT_DIR}
    nohup /www/wwwroot/discord-2/venv/bin/python ${SCRIPT_NAME} > output.log 2>&1 &
    echo "脚本已重新启动。"
else
    echo "脚本正在运行。"
fi