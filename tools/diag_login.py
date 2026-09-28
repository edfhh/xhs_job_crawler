# -*- coding: utf-8 -*-
"""诊断登录模式：逐步复现 core/browser.py::wait_login，把真实异常抓出来。

只做一次页面加载，不循环、不提交任何表单。
结果写入 data/_diag_login.txt，并截一张图 data/_login_page.png。
"""
import asyncio
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_config  # noqa: E402
from core.browser import XhsBrowser  # noqa: E402

SELS = [
    "button:has-text('登录')",
    "text=登录",
    "#login-btn",
    ".login-btn",
    "span:has-text('登录')",
]


async def main():
    log = []
    br = XhsBrowser()
    try:
        log.append("[1] 启动浏览器 (channel=%r headless=%r)" % (app_config.BROWSER_CHANNEL, app_config.HEADLESS))
        await br.start()
        log.append("    启动成功, context.pages=%d" % len(br.context.pages))
        log.append("    page.url=%r  is_closed=%s" % (br.page.url, br.page.is_closed()))

        log.append("[2] goto(%s)" % app_config.LOGIN_URL)
        try:
            resp = await br.page.goto(app_config.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            log.append("    HTTP=%s" % (resp.status if resp else None))
        except Exception as e:
            log.append("    GOTO_ERROR: %r" % e)
        await asyncio.sleep(3)
        try:
            log.append("    实际落点 url=%r" % br.page.url)
            log.append("    标题=%r" % (await br.page.title()))
        except Exception as e:
            log.append("    URL/标题读取失败: %r" % e)

        log.append("[3] 探测「登录」按钮")
        for sel in SELS:
            try:
                el = br.page.locator(sel).first
                cnt = await el.count()
                vis = await el.is_visible() if cnt else False
                log.append("    %-24s count=%d visible=%s" % (sel, cnt, vis))
            except Exception as e:
                log.append("    %-24s ERR %r" % (sel, e))

        log.append("[4] 页面关键元素统计")
        for sel in ["#app", ".login-container", ".login-btn", "canvas", "img[src*='qrcode']"]:
            try:
                cnt = await br.page.locator(sel).count()
                log.append("    %-22s count=%d" % (sel, cnt))
            except Exception as e:
                log.append("    %-22s ERR %r" % (sel, e))

        try:
            body = (await br.page.inner_text("body"))[:300].replace("\n", " | ")
            log.append("[5] body 前 300 字: %s" % body)
        except Exception as e:
            log.append("[5] body 读取失败: %r" % e)

        try:
            await br.page.screenshot(path=os.path.join(app_config.DATA_DIR, "_login_page.png"))
            log.append("[6] 截图成功: data/_login_page.png")
        except Exception as e:
            log.append("[6] 截图失败: %r" % e)

        log.append("[7] is_logged_in=%s login_check=%s" % (await br.is_logged_in(), br.login_check))
        ck = await br.cookies()
        log.append("    cookies=%d web_session_len=%s" % (
            len(ck), len(str(ck.get("web_session", "")))))

    except Exception:
        log.append("FATAL\n" + traceback.format_exc())
    finally:
        try:
            await br.context.close()
            await br._pw.stop()
        except Exception:
            pass
        with open(os.path.join(app_config.DATA_DIR, "_diag_login.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(log))


asyncio.run(main())
