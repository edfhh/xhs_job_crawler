# -*- coding: utf-8 -*-
"""
决定性对照实验：完全复刻 crawler 在「游客模式」下的 HTTP 取数路径，但把原始 HTML 落盘。

目的：crawler 游客模式报告 red_id 来源为 html_text，
      而直接用 requests(匿名 cookie) 抓同一 uid 却拿不到「小红书号」。
      本脚本用与 crawler 完全一致的浏览器会话流程（先逛推荐页拿到完整匿名 cookie），
      再调同样的 GET，看究竟能不能拿到。

用法：python tools/probe_guest2.py <uid>
"""
import asyncio
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import app_config  # noqa: E402
from core.xhs_client import (  # noqa: E402
    WEB, XhsClient, _base_headers, cookie_str, extract_red_id_from_text,
)

UID = sys.argv[1] if len(sys.argv) > 1 else "5a5a5a5a00000000a5a5a5a5"


async def main():
    from core.browser import XhsBrowser
    br = XhsBrowser()
    await br.start()
    try:
        await br.page.goto(app_config.LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(5)
        # 模拟 crawler 的滚动行为（这一步会让小红书下发更完整的匿名会话 cookie）
        for _ in range(3):
            await br.page.mouse.wheel(0, 1200)
            await asyncio.sleep(1.5)
        ck = await br.cookies()
    finally:
        await br.close()

    print("cookie names =", sorted(ck.keys()))
    print("web_session len =", len(ck.get("web_session") or ""))

    import requests
    s = requests.Session()
    url = f"{WEB}/user/profile/{UID}"
    r = s.get(url, headers={"cookie": cookie_str(ck), **_base_headers(referer=f"{WEB}/")}, timeout=20)
    html = r.text or ""
    print(f"\nGET {url} -> {r.status_code} len={len(html)}")
    print("含'小红书号' =", "小红书号" in html)
    print("含__INITIAL_STATE__ =", "__INITIAL_STATE__" in html)
    print("正则结果 =", repr(extract_red_id_from_text(html)))

    # 也用 XhsClient（含签名会话）走一遍
    info = XhsClient(ck).get_creator_info(UID)
    print("\nXhsClient.get_creator_info ->")
    print("  nickname =", repr(info.get("nickname")))
    print("  red_id   =", repr(info.get("red_id")), "src =", info.get("_red_id_src"))
    print("  desc     =", repr(info.get("desc"))[:80])
    print("  _debug   =", info.get("_debug"))

    p = os.path.join(_ROOT, "data", f"_probe2_{UID}.html")
    with open(p, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML =>", p)


if __name__ == "__main__":
    asyncio.run(main())
