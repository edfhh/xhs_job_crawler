# -*- coding: utf-8 -*-
"""诊断 3：搜索页实际渲染内容 + 探索页行业频道 ID 提取。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_dom.py
"""
import asyncio
import json
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import XhsBrowser


async def probe_search(br, kw):
    url = "https://www.xiaohongshu.com/search_result?keyword=%s&source=web_search_result_notes&type=51" % quote(kw)
    try:
        await br.page.goto(url, wait_until="domcontentloaded", timeout=25000)
    except Exception as e:
        print("[搜索页] goto:", type(e).__name__, str(e)[:80])
    await asyncio.sleep(6)
    for i in range(3):
        await br.page.mouse.wheel(0, 1400)
        await asyncio.sleep(2)
    info = await br.page.evaluate("""() => {
        const body = document.body.innerText || '';
        const q = s => document.querySelectorAll(s).length;
        return {
            noteItem: q('section.note-item'),
            exploreLinks: q('a[href*="/explore/"]'),
            profileLinks: q('a[href*="/user/profile/"]'),
            anyCards: q('.note-item, .feeds-container > *'),
            loginWall: /扫码登录|登录后查看|立即登录|登录查看更多|登录\/注册/.test(body),
            text: body.replace(/\\n+/g, ' | ').slice(0, 420)
        };
    }""")
    print("[搜索页 keyword=%s] note-item=%d explore链接=%d profile链接=%d 其他卡片=%d 登录墙=%s"
          % (kw, info["noteItem"], info["exploreLinks"], info["profileLinks"], info["anyCards"], info["loginWall"]))
    print("   文本:", info["text"][:400])
    try:
        await br.page.screenshot(path="data/_diag_search_page.png", full_page=False)
        print("   截图已存 data/_diag_search_page.png")
    except Exception as e:
        print("   截图失败:", str(e)[:60])


async def probe_channels(br):
    try:
        await br.page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print("[探索页] goto:", type(e).__name__, str(e)[:80])
    await asyncio.sleep(6)
    nodes = await br.page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('#channel-container *, nav *, [class*=channel] *').forEach(e => {
            const t = (e.innerText || '').trim();
            if (!t || t.length > 10 || t.includes('\\n')) return;
            out.push({tag: e.tagName, cls: String(e.className).slice(0, 36),
                      ds: JSON.stringify(e.dataset || {}), txt: t});
        });
        return out.slice(0, 50);
    }""")
    print("[探索页侧栏节点] 共 %d 个（截断展示）" % len(nodes))
    for n in nodes[:18]:
        print("   ", n["txt"], "|", n["tag"], "|", n["cls"], "|", n["ds"][:90])

    for name in ("旅行", "穿搭", "美食", "职场"):
        await br.page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        try:
            await br.page.get_by_text(name, exact=True).first.click(timeout=8000)
            await asyncio.sleep(5)
            print("[点击 %s] url=%s" % (name, br.page.url[:140]))
        except Exception as e:
            print("[点击 %s] 失败: %s %s" % (name, type(e).__name__, str(e)[:80]))


async def main():
    br = XhsBrowser()
    await br.start()
    try:
        await probe_search(br, "旅游攻略")
        await probe_channels(br)
    finally:
        await br.close()


asyncio.run(main())
