# -*- coding: utf-8 -*-
"""诊断 4：行业频道（/explore?channel_id=...）是否可用 + 频道 ID 是否正确。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_channel.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import XhsBrowser

CANDIDATES = [
    ("家居", "homefeed.household_product_v3"),
    ("游戏", "homefeed.gaming_v3"),
    ("宠物", "homefeed.pet"),
]


async def probe(br, label, cid):
    url = "https://www.xiaohongshu.com/explore?channel_id=%s" % cid
    try:
        await br.page.goto(url, wait_until="commit", timeout=15000)
    except Exception as e:
        print("[%s] %-26s goto=%s" % (label, cid, type(e).__name__))
        return
    await asyncio.sleep(5)
    try:
        info = await br.page.evaluate("""() => {
            const t = [...document.querySelectorAll('section.note-item, .note-item')].slice(0, 3)
                .map(e => (e.innerText || '').replace(/\\n+/g, ' / ').trim().slice(0, 46));
            return {
                links: document.querySelectorAll('a[href*="/user/profile/"]').length,
                notes: t,
                title: document.title
            };
        }""")
        keep = "channel_id=" in br.page.url
        print("[%s] %-26s 保持频道=%s links=%d\n      标题=%s\n      前3条=%s"
              % (label, cid, keep, info["links"], info["title"][:40], info["notes"]))
    except Exception as e:
        print("[%s] %-26s 提取失败=%s" % (label, cid, type(e).__name__))


async def main():
    br = XhsBrowser()
    await br.start()
    try:
        for label, cid in CANDIDATES:
            await probe(br, label, cid)
    finally:
        await br.close()


asyncio.run(main())
