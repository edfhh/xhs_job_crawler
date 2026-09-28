# -*- coding: utf-8 -*-
"""聚焦探测登录弹窗：
A) 不点击时二维码弹窗是否已可见
B) 点击「登录」后弹窗是打开还是被切掉
C) 二维码用什么元素承载（canvas / img / data:URL）
D) 窗口是否在前台
结果写 data/_diag_login2.txt
"""
import asyncio
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app_config  # noqa: E402
from core.browser import XhsBrowser  # noqa: E402

MODAL_SELS = [".login-container", "div.login-container", "text=扫码登录", "text=手机号登录",
              "text=获取验证码", "text=二维码"]


async def modal_state(page, tag, log):
    for sel in MODAL_SELS:
        try:
            cnt = await page.locator(sel).count()
            vis = await page.locator(sel).first.is_visible() if cnt else False
            log.append("    %-16s [%s] count=%d visible=%s" % (tag, sel, cnt, vis))
        except Exception as e:
            log.append("    %-16s [%s] ERR %r" % (tag, sel, e))


async def main():
    log = []
    br = XhsBrowser()
    try:
        await br.start()
        log.append("[A] goto /explore 后（不点击任何东西）")
        await br.page.goto(app_config.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)
        await modal_state(br.page, "no-click", log)

        log.append("[B] 点击「登录」按钮后")
        try:
            el = br.page.locator("button:has-text('登录')").first
            log.append("    按钮 count=%d visible=%s" % (await el.count(), await el.is_visible()))
            await el.click(timeout=5000)
            await asyncio.sleep(3)
            log.append("    点击成功，URL=%r" % br.page.url)
        except Exception as e:
            log.append("    点击异常: %r" % e)
        await modal_state(br.page, "after-click", log)

        log.append("[C] 二维码承载元素")
        for sel in ["canvas", ".login-container canvas", "img", ".qrcode img",
                    "img[src^='data:image']", ".login-container img"]:
            try:
                cnt = await br.page.locator(sel).count()
                log.append("    %-26s count=%d" % (sel, cnt))
            except Exception as e:
                log.append("    %-26s ERR %r" % (sel, e))
        try:
            srcs = await br.page.eval_on_selector_all(
                ".login-container img, .login-container canvas",
                "els => els.map(e => e.tagName + ':' + String(e.src || e.width + 'x' + e.height).slice(0, 60))")
            log.append("    login-container 内元素: %s" % srcs[:6])
        except Exception as e:
            log.append("    枚举失败: %r" % e)

        log.append("[D] 窗口前台/尺寸")
        try:
            await br.page.bring_to_front()
            log.append("    bring_to_front 调用成功")
            vp = br.page.viewport_size
            log.append("    viewport=%s" % vp)
        except Exception as e:
            log.append("    失败: %r" % e)

        try:
            await br.page.screenshot(path=os.path.join(app_config.DATA_DIR, "_login_page2.png"))
            log.append("[E] 截图: data/_login_page2.png")
        except Exception as e:
            log.append("[E] 截图失败: %r" % e)
    except Exception:
        log.append("FATAL\n" + traceback.format_exc())
    finally:
        try:
            await br.context.close()
            await br._pw.stop()
        except Exception:
            pass
        with open(os.path.join(app_config.DATA_DIR, "_diag_login2.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(log))


asyncio.run(main())
