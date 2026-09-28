#!/bin/sh
# 本地 Web 接口自测（不联网、不登录）
cd "$(dirname "$0")/.." || exit 1
PORT=8777
LOG=data/_server.log

# 若端口被占用，先清掉旧进程
if command -v lsof >/dev/null 2>&1; then
  OLD=$(lsof -ti tcp:$PORT 2>/dev/null)
  [ -n "$OLD" ] && kill $OLD 2>/dev/null && sleep 1
fi

python3 -c "import uvicorn;from web.server import app;uvicorn.run(app,host='127.0.0.1',port=$PORT,log_level='warning')" > "$LOG" 2>&1 &
SRV=$!
sleep 5

{
echo "===== GET / ====="
curl -s -o /dev/null -w "http=%{http_code} size=%{size_download}\n" "http://127.0.0.1:$PORT/"
echo
echo "===== POST /api/demo ====="
curl -s -X POST "http://127.0.0.1:$PORT/api/demo"; echo
echo
echo "===== GET /api/status ====="
curl -s "http://127.0.0.1:$PORT/api/status"; echo
echo
echo "===== GET /api/export?fmt=csv ====="
curl -s "http://127.0.0.1:$PORT/api/export?fmt=csv"; echo
echo
echo "===== GET /api/export?fmt=xlsx ====="
curl -s -o data/_demo.xlsx -w "http=%{http_code} bytes=%{size_download}\n" "http://127.0.0.1:$PORT/api/export?fmt=xlsx"
echo
echo "===== POST /api/start（当前无 playwright，应给出友好错误）====="
curl -s -X POST -H 'Content-Type: application/json' -d '{"count":10}' "http://127.0.0.1:$PORT/api/start"; echo
sleep 2
echo "----- status after start -----"
curl -s "http://127.0.0.1:$PORT/api/status"; echo
} > data/_web_test.txt 2>&1

kill $SRV 2>/dev/null
sleep 1
echo "=== server log ==="
cat "$LOG"
echo "=== done ==="
