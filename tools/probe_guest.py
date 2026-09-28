# -*- coding: utf-8 -*-
"""
诊断脚本：在「游客（未登录）」状态下，看博主主页 HTTP 响应里到底有哪些字段可用。

用途：量化免登录模式能拿到 昵称/小红书号/简介 中的哪几项，据此决定解析策略。

用法：python tools/probe_guest.py [user_id ...]
"""
import asyncio
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import app_config  # noqa: E402
from core.xhs_client import (  # noqa: E402
    WEB, UA, cookie_str, extract_initial_state, extract_red_id_from_text,
)

OUT_DIR = os.path.join(_ROOT, "data")
UIDS = sys.argv[1:]


def analyze(uid, html):
    print(f"\n===== uid={uid} =====")
    state = extract_initial_state(html)
    upd = (state.get("user") or {}).get("userPageData")
    print(f"html_len={len(html)} 含'小红书号'={'小红书号' in html} "
          f"含__INITIAL_STATE__={'__INITIAL_STATE__' in html} userPageData={bool(upd)}")
    if upd:
        bi = upd.get("basicInfo") or {}
        print("  basicInfo keys =", list(bi.keys()))
        print("  nickname =", repr(bi.get("nickname") or bi.get("nickName")))
        print("  redId    =", repr(bi.get("redId") or bi.get("red_id")))
        print("  desc     =", repr(bi.get("desc"))[:100])
    print("  正则小红书号 =", repr(extract_red_id_from_text(html)))
    for pat, label in [
        (r'<meta[^>]+name="description"[^>]+content="([^"]*)"', "meta description"),
        (r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', "og:description"),
        (r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', "og:title"),
        (r'<title[^>]*>([^<]*)</title>', "title"),
    ]:
        m = re.search(pat, html, re.S)
        if m:
            print(f"  {label} = {m.group(1).strip()[:170]!r}")

    path = os.path.join(OUT_DIR, f"_probe_{uid}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML 已存 =>", path)


async def main():
    uids = UIDS or ["123456789"]
    from core.browser import XhsBrowser
    br = XhsBrowser()
    await br.start()
    try:
        await br.page.goto(app_config.LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(4)
        ck = await br.cookies()
    finally:
        await br.close()
    print(f"Cookie 数={len(ck)} 含 web_session={bool(ck.get('web_session'))}")

    import requests
    sess = requests.Session()
    for uid in uids:
        url = f"{WEB}/user/profile/{uid}"
        r = sess.get(url, headers={
            "user-agent": UA,
            "referer": f"{WEB}/",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "cookie": cookie_str(ck),
        }, timeout=20)
        print(f"\nGET {url} -> {r.status_code}")
        analyze(uid, r.text or "")


if __name__ == "__main__":
    asyncio.run(main())
