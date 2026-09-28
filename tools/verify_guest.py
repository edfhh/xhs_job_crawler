# -*- coding: utf-8 -*-
"""实机验证：① 游客会话的登录判定 ② 免登录主页解析（昵称/小红书号/简介/IP属地）。"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import app_config  # noqa: E402
from core.xhs_client import XhsClient, me_guest_flag, parse_creator_from_html  # noqa: E402

UID = sys.argv[1] if len(sys.argv) > 1 else "5a5a5a5a00000000a5a5a5a5"


async def main():
    from core.browser import XhsBrowser
    br = XhsBrowser()
    await br.start()
    try:
        await br.page.goto(app_config.LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        for _ in range(3):
            await br.page.mouse.wheel(0, 1200)
            await asyncio.sleep(1.5)
        ck = await br.cookies()
    finally:
        await br.close()

    print("cookies =", len(ck), "| web_session len =", len(ck.get("web_session") or ""))
    print("is_logged_in(api) ->", await _login(ck))
    c = XhsClient(ck)
    info = c.get_creator_info(UID)
    print("get_creator_info ->", {k: info.get(k) for k in ("nickname", "red_id", "desc", "ip_location")})
    print("  src =", info.get("_red_id_src"), "| debug =", info.get("_debug"))
    # 顺带验证 HTML 直解
    r = c._do_signed_get("/api/sns/web/v2/user/me", {})
    print("user/me ->", str(r)[:200])


async def _login(ck):
    from core.browser import XhsBrowser
    return "guest=%r" % me_guest_flag(ck)


asyncio.run(main())
