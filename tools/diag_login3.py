"""登录链路一次性自检（约 30 秒，只跑一轮，不做长等待）。

验证改动后的 core/browser.py：
  1) 浏览器能起来（记录实际渠道 + profile 目录）
  2) 能真的跳到 xiaohongshu.com（不是空白页 / chrome-error）
  3) 登录弹窗与二维码是否渲染出来

用法：
    .venv/bin/python tools/diag_login3.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_config  # noqa: E402
from core.browser import XhsBrowser  # noqa: E402


async def main():
    br = XhsBrowser()
    await br.start()
    print("[1] 浏览器已启动")
    print("    渠道        :", br.diag.get("channel"))
    print("    profile目录 :", br.diag.get("profile_dir"))
    print("    headless    :", br.diag.get("headless"))
    if br.warnings:
        print("    启动提示    :", "；".join(br.warnings))

    url = await br.open_login_page()
    print("[2] 页面已跳转   :", url)
    print("    标题        :", (await br.page.title())[:80])

    qr = await br._qr_ready()
    box = await br._login_box_visible()
    print("[3] 登录弹窗可见 :", box)
    print("    二维码已渲染 :", qr)
    print("    已登录        :", await br.is_logged_in())

    if qr or box:
        print("\n结果：登录链路正常（窗口里应能看到二维码）。")
    else:
        print("\n结果：页面打开了但没看到登录弹窗/二维码 —— 窗口可能被压在后台，请切到前台看看。")

    await br.close()


if __name__ == "__main__":
    asyncio.run(main())
