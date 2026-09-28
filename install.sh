#!/usr/bin/env bash
# 一键安装依赖（换机器后只需执行一次）
# 用法： ./install.sh
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

echo "[1/4] 检查 Python ..."
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "× 未找到 $PY。请先安装 Python 3.10+（推荐 3.11/3.12），或指定：PYTHON=/path/to/python3 ./install.sh"
  exit 1
fi
"$PY" - <<'EOF'
import sys
if sys.version_info < (3, 10):
    sys.exit("× 需要 Python 3.10 及以上，当前为 %s" % sys.version.split()[0])
print("  Python 版本 OK：", sys.version.split()[0])
EOF

echo "[2/4] 创建虚拟环境 .venv ..."
if [ -d .venv ]; then
  echo "  已存在，跳过"
else
  "$PY" -m venv .venv
fi

echo "[3/4] 安装 Python 依赖（requirements.txt）..."
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt

echo "[4/4] 安装 Playwright 浏览器内核 chromium（约 150MB，只需一次）..."
.venv/bin/python -m playwright install chromium

cat <<'EOF'

安装完成 ✅

启动服务：   ./start.sh
自检登录链：  DISPLAY=:0.0 .venv/bin/python tools/diag_login3.py
离线验证预测： .venv/bin/python tools/predict_cli.py

若启动报缺少系统共享库（Linux 上常见 libnss3 / libatk 等），执行：
  .venv/bin/python -m playwright install-deps chromium     # 需要 root/sudo
EOF
