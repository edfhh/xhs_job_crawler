# -*- coding: utf-8 -*-
"""
风控核心 #3：反检测浏览器 + 扫码登录 + 推荐流采集。

参考 MediaCrawler 的做法并精简：
  - 持久化上下文（user_data_dir）复用登录态，避免频繁登录触发风控；
  - 注入 stealth.min.js，并关闭 AutomationControlled 指纹；
  - 登录交给用户扫码（有头模式）；
  - 「主页推荐」里每个笔记卡片都带作者主页链接，直接从 DOM 采集作者，稳健且无需额外签名。
"""
import asyncio
import os
from urllib.parse import urlparse, parse_qs

import app_config

_STEALTH = ""
try:
    with open(os.path.join(os.path.dirname(__file__), "stealth.min.js"), encoding="utf-8") as f:
        _STEALTH = f.read()
except Exception:
    _STEALTH = ""


class XhsBrowser:
    def __init__(self):
        self._pw = None
        self.context = None
        self.page = None
        self.login_check = "unknown"
        self.channel_used = ""      # 实际用上的渠道（""=Playwright 自带 chromium）
        self.warnings = []          # 需要在界面上暴露的问题提示
        self.diag = {}              # 登录过程诊断（当前 URL / 二维码是否可见 / 用的哪个浏览器）  # api | cookie_fallback | unknown（登录判定依据，透出到界面）

    async def start(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "未安装 playwright。请先执行：pip install playwright && playwright install chromium"
            ) from e
        self._pw = await async_playwright().start()
        launch_args = list(app_config.LAUNCH_ARGS) + ["--disable-dev-shm-usage"]
        # 登录态目录按渠道区分：chrome 与 chromium 的 profile 不通用，
        # 混用会开出一个空白、无法跳转的窗口。
        profile_dir = app_config.profile_dir()
        os.makedirs(profile_dir, exist_ok=True)
        lock = os.path.join(profile_dir, "SingletonLock")
        if os.path.exists(lock):
            self.warnings.append(
                "登录态目录里存在 SingletonLock：若还有旧的浏览器窗口开着，请先全部关掉再跑，"
                "否则新窗口可能停在空白页、无法跳转。"
            )

        kwargs = dict(
            user_data_dir=profile_dir,
            headless=app_config.HEADLESS,
            args=launch_args,
            viewport=None,          # 交给 --start-maximized，避免窗口被压成固定小窗
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        # 渠道策略：默认用自带 chromium（与登录态目录同源，最稳）。
        # 只有显式设置 XHS_CHANNEL=chrome 时才用本机 Chrome；失败则明确回退并记下原因。
        if app_config.BROWSER_CHANNEL:
            try:
                self.context = await self._pw.chromium.launch_persistent_context(
                    channel=app_config.BROWSER_CHANNEL, **kwargs
                )
                self.channel_used = app_config.BROWSER_CHANNEL
            except Exception as e:
                self.warnings.append(
                    "渠道 %r 启动失败（%s），已回退到自带 chromium。"
                    % (app_config.BROWSER_CHANNEL, str(e).splitlines()[0][:160])
                )
        if self.context is None:
            self.context = await self._pw.chromium.launch_persistent_context(**kwargs)
            self.channel_used = ""

        if _STEALTH:
            await self.context.add_init_script(_STEALTH)
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        # 把窗口提到前台：否则可能被压在其它窗口下面，看起来像「没打开 / 点不开」
        try:
            await self.page.bring_to_front()
        except Exception:
            pass
        self.diag = {
            "channel": self.channel_used or "chromium(自带)",
            "profile_dir": profile_dir,
            "headless": app_config.HEADLESS,
            "warnings": list(self.warnings),
        }
        return self

    # ------------------------------------------------------------------ #
    async def is_logged_in(self) -> bool:
        """判断是否已登录：以接口 /api/sns/web/v2/user/me 的 data.guest 为准。

        实测坑：小红书会给**未登录游客**也下发 web_session Cookie（长度 38），
        所以「Cookie 里存在 web_session」不能当登录判据——会把游客误判成已登录、
        跳过扫码，随后主页资料抓不全（小红书号为空）。
        接口返回 {"guest": true, "user_id": ...} 才是权威的游客信号。
        接口不可用（网络抖动）时退化为 Cookie 判据并标记 login_check=cookie_fallback，
        避免把用户永久卡在登录页。
        """
        try:
            ck = await self.cookies()
        except Exception:
            ck = {}
        if not ck:
            self.login_check = "unknown"
            return False
        try:
            from core.xhs_client import me_guest_flag
            guest = await asyncio.to_thread(me_guest_flag, ck)
        except Exception:
            guest = None
        if guest is None:
            has_sess = any(str(k) == "web_session" and len(str(v or "")) >= 10 for k, v in ck.items())
            self.login_check = "cookie_fallback"
            return has_sess
        self.login_check = "api"
        return guest is False

    async def _login_box_visible(self) -> bool:
        for sel in [".login-container", "div.login-container", ".login-box", "[class*='login-container']"]:
            try:
                el = self.page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _qr_ready(self) -> bool:
        """二维码是否已经渲染出来。"""
        for sel in [".qrcode img", ".login-container canvas", "img[src^='data:image']"]:
            try:
                el = self.page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def open_login_page(self):
        """打开小红书并确认真的跳过去了。

        返回最终落点 URL；打不开时抛出带排查建议的错误。
        专门解决「窗口起来了但停在空白页 / 无法跳转」这类静默失败。
        """
        last = None
        for _ in range(2):
            try:
                await self.page.goto(
                    app_config.LOGIN_URL,
                    wait_until="domcontentloaded",
                    timeout=app_config.LOGIN_NAV_TIMEOUT_MS,
                )
            except Exception as e:
                last = e
                await asyncio.sleep(2)
                continue
            await asyncio.sleep(3)
            url = self.page.url or ""
            if url.startswith("about:") or url.startswith("chrome-error") or "xiaohongshu.com" not in url:
                last = RuntimeError("页面停在 %s" % (url or "空地址"))
                await asyncio.sleep(2)
                continue
            return url
        raise RuntimeError(
            "无法打开小红书登录页（%s）。常见原因：本机网络/DNS 访问不了 xiaohongshu.com，"
            "或系统代理没生效。请先用普通浏览器打开 https://www.xiaohongshu.com 确认能访问。"
            % (str(last).splitlines()[0][:200] if last else "未知错误")
        )

    async def wait_login(self, on_wait=None):
        """打开小红书并等待用户扫码登录。on_wait(剩余秒数) 用于把倒计时透出到界面。"""
        url = await self.open_login_page()
        self.diag["login_url"] = url
        try:
            self.diag["title"] = (await self.page.title())[:80]
        except Exception:
            pass
        try:
            await self.page.bring_to_front()
        except Exception:
            pass

        if await self.is_logged_in():
            self.diag["qr_visible"] = False
            return True

        # 登录弹窗通常随页面自动出现；只有它没出现时才去点「登录」按钮，
        # 否则点击可能反而把已经打开的弹窗切掉。
        if not await self._login_box_visible():
            for sel in ["button:has-text('登录')", "text=登录", "#login-btn",
                        ".login-btn", "span:has-text('登录')"]:
                try:
                    el = self.page.locator(sel).first
                    if await el.count() > 0 and await el.is_visible():
                        await el.click(timeout=5000)
                        break
                except Exception:
                    continue
            await asyncio.sleep(1.5)

        # 等二维码渲染，并把结果记进 diag（界面可直接看到「二维码：已显示」）
        qr = False
        for _ in range(max(1, int(app_config.LOGIN_QR_WAIT_SEC))):
            if await self._qr_ready():
                qr = True
                break
            await asyncio.sleep(1)
        self.diag["qr_visible"] = qr
        self.diag["login_box_visible"] = await self._login_box_visible()
        if not qr:
            self.warnings.append(
                "没检测到二维码元素：窗口已打开，可直接在窗口里点「登录」手动扫码，"
                "登录成功后本工具会自动继续。"
            )

        deadline = asyncio.get_event_loop().time() + app_config.LOGIN_TIMEOUT_SEC
        refresh_tried = 0
        while True:
            now = asyncio.get_event_loop().time()
            remain = deadline - now
            if remain <= 0:
                raise TimeoutError(
                    "等待扫码登录超时（%ds）。当前页面=%s，二维码可见=%s，登录弹窗可见=%s。"
                    % (app_config.LOGIN_TIMEOUT_SEC, self.page.url, qr,
                       self.diag.get("login_box_visible"))
                )
            if await self.is_logged_in():
                return True
            # 二维码有效期短，过期后需要点「刷新」重新生成
            try:
                exp = self.page.locator("text=二维码已失效")
                if await exp.count() > 0 and await exp.first.is_visible() and refresh_tried < 3:
                    refresh_tried += 1
                    for sel in [".login-container text=刷新", "text=刷新", "text=点击刷新"]:
                        try:
                            btn = self.page.locator(sel).first
                            if await btn.count() > 0:
                                await btn.click(timeout=3000)
                                break
                        except Exception:
                            continue
                    self.diag["qr_refreshed"] = refresh_tried
            except Exception:
                pass
            if on_wait:
                try:
                    on_wait(max(0, int(remain)))
                except Exception:
                    pass
            await asyncio.sleep(2)

    async def fetch_profile(self, user_id: str, xsec_token: str = "") -> dict:
        """用浏览器（真实登录态）打开博主主页，抓昵称/小红书号/简介。

        作为「HTTP 解析」的兜底：浏览器走的是已登录会话，能拿到 requests 拿不到的字段。
        """
        from core.xhs_client import parse_creator, extract_red_id_from_text
        url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
        if xsec_token:
            url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
        except Exception:
            return {}
        await asyncio.sleep(app_config.PROFILE_WAIT_SEC)

        try:
            upd = await self.page.evaluate(
                "() => (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user && "
                "window.__INITIAL_STATE__.user.userPageData) || {}"
            )
        except Exception:
            upd = {}
        info = parse_creator(upd or {})

        if not info.get("red_id") or not info.get("nickname"):
            try:
                txt = await self.page.inner_text("body")
            except Exception:
                txt = ""
            if not info.get("red_id"):
                rid = extract_red_id_from_text(txt)
                if rid:
                    info["red_id"] = rid
                    info["_red_id_src"] = "dom_text"
            if not info.get("nickname"):
                try:
                    title = await self.page.title() or ""
                    nm = title.split("-")[0].split("_")[0].strip()
                    if nm and "小红书" not in nm:
                        info["nickname"] = nm
                        info["_nickname_src"] = "dom_title"
                except Exception:
                    pass
        info["_src"] = "browser"
        return info

    async def cookies(self) -> dict:
        jar = await self.context.cookies()
        return {c["name"]: c["value"] for c in jar if c.get("name")}

    async def save_state(self):
        try:
            await self.context.storage_state(path=app_config.STORAGE_STATE)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    async def harvest_creators(self, max_count: int, entry_url: str = None):
        """打开主页推荐（或指定入口页），滚动加载，采集去重后的作者（user_id + xsec_token + 昵称）。"""
        # 入口页导航：搜索页 / 部分频道页偶发长时间不返回（风控或 JS 挑战），
        # 用 commit + 容错重试，即使导航超时也继续尝试从已渲染的 DOM 里提取作者。
        url = entry_url or app_config.LOGIN_URL
        for attempt in range(2):
            try:
                await self.page.goto(url, wait_until="commit",
                                     timeout=app_config.ENTRY_GOTO_TIMEOUT_MS)
                break
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(2)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(app_config.FEED_SCROLL_WAIT_SEC)

        seen = {}
        stagnant = 0
        for _ in range(60):
            try:
                cards = await asyncio.wait_for(
                    self.page.eval_on_selector_all(
                        'a[href*="/user/profile/"]',
                        """els => els.map(e => ({
                            href: e.getAttribute('href') || '',
                            name: (e.innerText || '').trim().slice(0, 40)
                        }))""",
                    ),
                    timeout=10,
                )
            except Exception:
                cards = []
            before = len(seen)
            for c in cards:
                href = c.get("href", "")
                try:
                    q = parse_qs(urlparse(href).query)
                    uid = urlparse(href).path.rstrip("/").split("/")[-1]
                except Exception:
                    continue
                if not uid:
                    continue
                if uid not in seen:
                    seen[uid] = {
                        "user_id": uid,
                        "xsec_token": (q.get("xsec_token") or [""])[0],
                        "xsec_source": (q.get("xsec_source") or ["pc_feed"])[0],
                        "nickname_raw": c.get("name", ""),
                    }
                if len(seen) >= max_count:
                    break
            if len(seen) >= max_count:
                break
            stagnant = stagnant + 1 if len(seen) == before else 0
            if stagnant >= 6:            # 连续多次滚动没有新增，认为加载不动了
                break
            try:
                await asyncio.wait_for(self.page.mouse.wheel(0, 2400), timeout=6)
            except Exception:
                pass
            await asyncio.sleep(app_config.FEED_SCROLL_WAIT_SEC)
        return list(seen.values())[:max_count]

    async def harvest_creators_by_channel(self, channel_id: str, max_count: int = 20):
        """从「行业频道」推荐流采集作者（游客态即可用，内容贴合行业）。

        频道 ID 见 app_config.INDUSTRY_CHANNELS，入口形如
        https://www.xiaohongshu.com/explore?channel_id=homefeed.travel_v3
        """
        if not channel_id:
            return []
        got = await self.harvest_creators(max_count, entry_url=app_config.CHANNEL_URL % channel_id)
        for c in got:
            c["source"] = "channel"
            c["channel_id"] = channel_id
        return got

    async def harvest_creators_by_keyword(self, keyword: str, max_count: int = 20):
        """按关键词打开搜索结果页，采集候选博主（搜索接口被风控时的兜底）。

        复用 harvest_creators 的 DOM 提取 / 滚动 / 去重逻辑，只换入口 URL。
        搜索结果页的笔记卡片同样带 a[href*="/user/profile/"]（含 xsec_token）。
        """
        from urllib.parse import quote
        url = ("https://www.xiaohongshu.com/search_result?keyword=%s"
               "&source=web_search_result_notes&type=51" % quote(keyword))
        got = await self.harvest_creators(max_count, entry_url=url)
        for c in got:
            c["source_keyword"] = keyword
            c["source"] = "search_dom"
        return got

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            if self._pw:
                await self._pw.stop()
