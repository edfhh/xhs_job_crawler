# -*- coding: utf-8 -*-
"""诊断 7：直接验证「行业频道」采集是否真能取到博主（不经过 Web 服务）。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_chan_e2e.py
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.browser import XhsBrowser


async def main():
    br = XhsBrowser()
    t0 = time.time()
    await br.start()
    print("MARK 浏览器启动 %.1fs" % (time.time() - t0))
    try:
        for cid in ["homefeed.travel_v3", "homefeed.food_v3"]:
            t1 = time.time()
            got = await br.harvest_creators_by_channel(cid, 10)
            print("MARK channel=%s n=%d 用时%.1fs" % (cid, len(got), time.time() - t1))
            for c in got[:4]:
                print("   - uid=%s name=%s src=%s" % (
                    c.get("user_id"), (c.get("nickname_raw") or c.get("nickname") or "")[:18],
                    c.get("source")))
            # 直接看页面 URL 与作者链接数，判断是否真的进了频道（而不是回退推荐流）
            print("   page.url =", br.page.url)
    finally:
        await br.close()


asyncio.run(main())
