# -*- coding: utf-8 -*-
"""诊断 6：从页面 JS 中提取全部行业频道 ID（用于游客态行业筛选）。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_channels_js.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import XhsBrowser


async def main():
    br = XhsBrowser()
    await br.start()
    try:
        try:
            await br.page.goto("https://www.xiaohongshu.com/explore",
                               wait_until="commit", timeout=20000)
        except Exception as e:
            print("goto:", type(e).__name__)
        await asyncio.sleep(6)
        res = await br.page.evaluate("""async () => {
            const srcs = [...document.querySelectorAll('script[src]')].map(s => s.src);
            const ids = new Set();
            const ctx = [];
            let scanned = 0, bytes = 0;
            for (const s of srcs) {
                try {
                    const r = await fetch(s);
                    const t = await r.text();
                    bytes += t.length; scanned++;
                    for (const m of t.matchAll(/homefeed[._][a-z0-9_]+/g)) ids.add(m[0]);
                    for (const m of t.matchAll(/.{0,70}homefeed\\.[a-z0-9_]+.{0,40}/g)) {
                        if (ctx.length < 60 && /[\\u4e00-\\u9fa5]/.test(m[0])) ctx.push(m[0]);
                    }
                } catch (e) {}
            }
            return {scanned, bytes, ids: [...ids].sort(), ctx};
        }""")
        print("扫描脚本数=%s 总字节=%s" % (res["scanned"], res["bytes"]))
        print("发现频道 ID（%d）：" % len(res["ids"]))
        print("   " + ", ".join(res["ids"]))
        print("带中文上下文的片段（%d，展示前 24）：" % len(res["ctx"]))
        for c in res["ctx"][:24]:
            print("   -", c.replace("\n", " ")[:150])
    finally:
        await br.close()


asyncio.run(main())
