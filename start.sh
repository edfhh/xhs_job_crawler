#!/usr/bin/env bash
# 启动采集器（打开 http://127.0.0.1:8777/）
#
# 常用环境变量：
#   XHS_PORT=8899      换端口（默认 8777）
#   XHS_HOST=0.0.0.0   让局域网其它机器也能访问（默认仅本机）
#   XHS_HEADLESS=1     强制无头（无图形界面的服务器；扫码登录会不可用）
#   XHS_CHANNEL=chrome 使用本机 Google Chrome（登录态目录会自动换成 *_chrome）
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "× 还没安装依赖，请先执行： ./install.sh"
  exit 1
fi

if [ -z "${DISPLAY:-}" ]; then
  export DISPLAY=:0.0
  echo "[提示] 未检测到 DISPLAY，已默认设为 :0.0。登录（扫码）模式需要图形界面；仅用游客模式可忽略。"
fi

echo "启动中… 浏览器访问 http://${XHS_HOST:-127.0.0.1}:${XHS_PORT:-8777}/"
exec .venv/bin/python run.py
