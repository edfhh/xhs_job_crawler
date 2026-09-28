# -*- coding: utf-8 -*-
"""
诊断脚本：判断「当前浏览器上下文是否真的已登录小红书」。

背景：小红书会给未登录游客也下发一个 web_session Cookie，
      因此「cookie 里有 web_session」不能作为登录判据。
      可靠判据是接口 /api/sns/web/v2/user/me（游客返回 -101 / success=false）。

用法：python tools/probe_login.py
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import app_config  # noqa: E402
from core.xhs_client import XhsClient  # noqa: E402

ME_URI = "/api/sns/web/v2/user/me"


async def main():
    from core.browser import XhsBrowser
    br = XhsBrowser()
    await br.start()
    try:
        await br.page.goto(app_config.LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        ck = await br.cookies()
    finally:
        await br.close()

    print("cookie names =", sorted(ck.keys()))
    print("web_session  =", (ck.get("web_session") or "")[:18], "...len=", len(ck.get("web_session") or ""))
    print("a1           =", (ck.get("a1") or "")[:12])

    client = XhsClient(ck)
    data = client._do_signed_get(ME_URI, {})
    print(f"\nGET {ME_URI} ->", str(data)[:400])
    print("\n判定：",
          "已登录" if (data.get("success") and data.get("data") and data["data"].get("user_id" or "userId")
                       or data.get("data", {}).get("guest") is False and data.get("success"))
          else "未登录/游客")
    return data


if __name__ == "__main__":
    asyncio.run(main())
