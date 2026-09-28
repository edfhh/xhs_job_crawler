# -*- coding: utf-8 -*-
"""诊断：行业关键词搜索链路（搜索接口 + 搜索页 DOM）。

    DISPLAY=:0.0 .venv/bin/python tools/diag_search.py 旅游攻略
"""
import asyncio
import json
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
import time

from core.browser import XhsBrowser
from core.xhs_client import XhsClient

KW = sys.argv[1] if len(sys.argv) > 1 else "旅游攻略"


async def main():
    br = XhsBrowser()
    await br.start()
    try:
        st = await br.page.context.storage_state()
        names = [c.get("name") for c in st.get("cookies", [])]
        print("[1] 当前会话 cookie 数 =", len(names), "含 web_session =", "web_session" in names)

        cookies = await br.cookies()
        client = XhsClient(cookies)
        uri = "/api/sns/web/v1/search/notes"
        payload = {
            "keyword": KW,
            "page": 1,
            "page_size": 20,
            "search_id": "%d%03d" % (int(time.time() * 1000), random.randint(0, 999)),
            "sort": "general",
            "note_type": 0,
            "ext_flags": [],
            "image_formats": ["jpg", "webp", "avif"],
        }
        try:
            data = await asyncio.to_thread(client._do_signed_post, uri, payload)
            print("[2] 接口 success =", data.get("success"), "code =", data.get("code"),
                  "msg =", str(data.get("msg"))[:80])
            d = data.get("data") or {}
            items = d.get("items") or []
            print("    data keys =", list(d.keys())[:8], " items =", len(items))
            if items:
                it = items[0]
                print("    第一条 keys:", list(it.keys())[:14])
                print("    model_type =", it.get("model_type"), " note_card?", bool(it.get("note_card")))
                nc = it.get("note_card") or {}
                print("    note_card keys:", list(nc.keys())[:14])
                print("    user =", json.dumps(nc.get("user"), ensure_ascii=False)[:220])
        except Exception as e:
            print("[2] 接口异常:", type(e).__name__, str(e)[:220])

        url = ("https://www.xiaohongshu.com/search_result?keyword=%s"
               "&source=web_search_result_notes&type=51" % quote(KW))
        try:
            await br.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("[3] goto 超时/异常（继续尝试提取 DOM）:", type(e).__name__, str(e)[:120])
        await asyncio.sleep(6)
        print("[3] 页面标题:", await br.page.title())
        print("    URL:", br.page.url[:130])
        info = await br.page.evaluate("""() => {
            const links = [...document.querySelectorAll('a[href*="/user/profile/"]')];
            const cards = document.querySelectorAll('section.note-item, .note-item');
            const body = document.body.innerText || '';
            return {
                profileLinks: links.length,
                sample: links.slice(0, 3).map(a => a.getAttribute('href')),
                cards: cards.length,
                hasLoginWall: /扫码登录|登录后查看|立即登录/.test(body),
                text: body.slice(0, 260)
            };
        }""")
        print("    profile 链接数:", info["profileLinks"], " 笔记卡片数:", info["cards"],
              " 登录墙:", info["hasLoginWall"])
        for s in info["sample"]:
            print("      href:", (s or "")[:110])
        print("    文本片段:", info["text"].replace("\n", " | ")[:220])
    finally:
        await br.close()


asyncio.run(main())
