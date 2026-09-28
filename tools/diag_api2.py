# -*- coding: utf-8 -*-
"""诊断 5：签名 API 是否可用（homefeed / user_posted）+ 搜索页正文内容。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_api2.py
"""
import asyncio
import os
import sys
from urllib.parse import quote, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import XhsBrowser
from core.xhs_client import XhsClient


async def main():
    br = XhsBrowser()
    await br.start()
    try:
        cookies = await br.cookies()
        client = XhsClient(cookies)

        print("=== 1) 签到友好接口：homefeed（浏览器的推荐流就是它）===")
        try:
            items = await asyncio.to_thread(client.get_home_recommend)
            print("    get_home_recommend ->", type(items).__name__, "len =",
                  len(items) if hasattr(items, "__len__") else "?")
            if items:
                it = items[0]
                print("    第一条 keys:", list(it.keys())[:10])
        except Exception as e:
            print("    异常:", type(e).__name__, str(e)[:200])

        print("=== 2) 取一个博主 uid 后调 user_posted ===")
        href = await br.page.evaluate(
            "() => { const a = document.querySelector('a[href*=\"/user/profile/\"]');"
            " return a ? a.getAttribute('href') : ''; }")
        uid = ""
        if href:
            seg = urlparse(href).path.strip("/").split("/")
            uid = seg[-1] if seg else ""
        print("    uid =", uid)
        if uid:
            try:
                d = await asyncio.to_thread(
                    client._do_signed_post, "/api/sns/web/v1/user_posted",
                    {"num": 20, "cursor": "", "user_id": uid,
                     "image_formats": ["jpg", "webp", "avif"]})
                print("    user_posted success=%s code=%s msg=%s notes=%d"
                      % (d.get("success"), d.get("code"), str(d.get("msg"))[:40],
                         len((d.get("data") or {}).get("notes") or [])))
            except Exception as e:
                print("    异常:", type(e).__name__, str(e)[:200])

        print("=== 3) 搜索页正文（是否登录墙）===")
        url = "https://www.xiaohongshu.com/search_result?keyword=%s&source=web_search_result_notes&type=51" % quote("旅游攻略")
        try:
            await br.page.goto(url, wait_until="commit", timeout=15000)
        except Exception as e:
            print("    goto:", type(e).__name__)
        await asyncio.sleep(6)
        info = await br.page.evaluate("""() => {
            const body = document.body.innerText || '';
            return {
                noteItem: document.querySelectorAll('section.note-item').length,
                exploreLinks: document.querySelectorAll('a[href*="/explore/"]').length,
                profileLinks: document.querySelectorAll('a[href*="/user/profile/"]').length,
                text: body.replace(/\\n+/g, ' | ').slice(0, 400)
            };
        }""")
        print("    note-item=%d explore链接=%d profile链接=%d"
              % (info["noteItem"], info["exploreLinks"], info["profileLinks"]))
        print("    正文:", info["text"][:380])
    finally:
        await br.close()


asyncio.run(main())
