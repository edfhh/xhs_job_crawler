# -*- coding: utf-8 -*-
"""诊断 8：完整跑一次「行业筛选」流程，每 2 秒采样 phase，拿到完整阶段历史。

    DISPLAY=:0.0 .venv/bin/python -u tools/diag_industry_e2e.py [行业名] [数量]
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.crawler import CrawlTask


async def main():
    ind = sys.argv[1] if len(sys.argv) > 1 else "旅游"
    cnt = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    t = CrawlTask(cnt, mode="guest", industries=[ind])
    print("MARK 参数 industries=%s count=%s 展开=%s" % ([ind], cnt, t.industries))
    t0 = time.time()
    task = asyncio.create_task(t.run())
    last = None
    while not task.done():
        await asyncio.sleep(2)
        if t.phase != last:
            print("PHASE %5.1fs %s" % (time.time() - t0, t.phase))
            last = t.phase
    try:
        await task
    except Exception as e:
        print("RUN EXC %s %s" % (type(e).__name__, str(e)[:300]))
    print("STATE=%s 用时=%.1fs 结果数=%d" % (t.state, time.time() - t0, len(t.results)))
    for r in t.results:
        print("   ROW " + json.dumps(r, ensure_ascii=False)[:240])


asyncio.run(main())
