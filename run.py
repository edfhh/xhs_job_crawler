# -*- coding: utf-8 -*-
"""
一键启动：起本地 Web 服务并自动打开页面。

用法：
    python run.py
然后在浏览器页面点「开始」，会弹出一个浏览器窗口跳转小红书，扫码登录即可。
"""
import threading
import webbrowser

import uvicorn

import app_config
from web.server import app


def _open():
    webbrowser.open(f"http://{app_config.WEB_HOST}:{app_config.WEB_PORT}/")


if __name__ == "__main__":
    print(f"* 控制台: http://{app_config.WEB_HOST}:{app_config.WEB_PORT}/")
    print("* 关闭本窗口即停止服务。")
    threading.Timer(1.2, _open).start()
    uvicorn.run(app, host=app_config.WEB_HOST, port=app_config.WEB_PORT, log_level="info")
