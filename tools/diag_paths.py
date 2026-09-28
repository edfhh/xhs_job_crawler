# -*- coding: utf-8 -*-
"""诊断 2：各路径可达性对比（首页/探索页/搜索页/搜索接口/频道入口）。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_paths.py
"""
import asyncio
import json
import os
import random
import sys
import time
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import XhsBrowser
from core.xhs_client import XhsClient


async def load(br, url, label, timeout=25000, wait=6):
    t0 = time.time()
    status = "ok"
    try:
        await br.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except Exception as e:
        status = type(e).__name__
    await asyncio.sleep(wait)
    try:
        title = (await br.page.title())[:46]
    except Exception:
        title = "?"
    try:
        n = await br.page.evaluate(
            "() => document.querySelectorAll('a[href*=\"/user/profile/\"]').length")
        cur = br.page.url[:95]
    except Exception:
        n, cur = -1, "?"
    print("[%s] %-58s -> %-14s %.1fs  links=%s\n        title=%s\n        url=%s"
          % (label, url[:58], status, time.time() - t0, n, title, cur))
    return status


async def main():
    br = XhsBrowser()
    await br.start()
    try:
        print("=== A. 探索页（登录入口，也是推荐流入口）===")
        await load(br, "https://www.xiaohongshu.com/explore", "A1", timeout=30000, wait=8)
        try:
            chans = await br.page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('a[href*="channel_id"], a[href*="/explore?channel"]')
                    .forEach(a => out.push((a.getAttribute('href')||'') + ' :: ' + (a.innerText||'').trim().slice(0,10)));
                const nav = [...document.querySelectorAll('#channel-container *, .channels *')]
                    .map(e => (e.innerText||'').trim()).filter(t => t && t.length < 12).slice(0, 40);
                return {links: out.slice(0, 40), navText: [...new Set(nav)].slice(0, 30)};
            }""")
            print("    频道链接:", json.dumps(chans["links"], ensure_ascii=False)[:900])
            print("    侧栏文字:", json.dumps(chans["navText"], ensure_ascii=False)[:500])
        except Exception as e:
            print("    频道探测异常:", type(e).__name__, str(e)[:120])

        print("=== B. 博主页（正文链路是否正常）===")
        href = await br.page.evaluate(
            "() => { const a = document.querySelector('a[href*=\"/user/profile/\"]');"
            " return a ? a.getAttribute('href') : ''; }")
        if href:
            u = href if href.startswith("http") else "https://www.xiaohongshu.com" + href
            await load(br, u, "B1", timeout=25000, wait=5)
        else:
            print("    探索页没抓到博主页链接（推荐流可能被登录墙挡）")

        print("=== C. 搜索页（两种参数）===")
        await load(br, "https://www.xiaohongshu.com/search_result?keyword=%s&source=web_search_result_notes&type=51"
                   % quote("旅游攻略"), "C1", timeout=20000, wait=6)
        await load(br, "https://www.xiaohongshu.com/search_result?keyword=%s" % quote("旅游"), "C2",
                   timeout=20000, wait=5)

        print("=== D. 搜索接口（多种参数变体）===")
        cookies = await br.cookies()
        client = XhsClient(cookies)
        base = {
            "keyword": "旅游攻略", "page": 1, "page_size": 20, "search_id": "2dz8m9k1",
            "sort": "general", "note_type": 0, "ext_flags": [], "image_formats": ["jpg", "webp", "avif"],
        }
        variants = {
            "原样": dict(base),
            "search_id=毫秒时间戳": dict(base, search_id="%d" % int(time.time() * 1000)),
            "无search_id": {k: v for k, v in base.items() if k != "search_id"},
            "带search_request_id": dict(base, search_request_id="%d%03d" % (int(time.time() * 1000), random.randint(0, 999))),
        }
        for label, p in variants.items():
            try:
                d = await asyncio.to_thread(client._do_signed_post,
                                            "/api/sns/web/v1/search/notes", p)
                dd = d.get("data") or {}
                print("    %-20s success=%s code=%s msg=%s items=%d"
                      % (label, d.get("success"), d.get("code"), str(d.get("msg"))[:34],
                         len(dd.get("items") or [])))
            except Exception as e:
                print("    %-20s 异常 %s %s" % (label, type(e).__name__, str(e)[:100]))
    finally:
        await br.close()


asyncio.run(main())
