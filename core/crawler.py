# -*- coding: utf-8 -*-
"""
抓取编排：登录 -> 采集推荐流作者 -> 逐个抓博主主页 -> 职业预测 -> 限流输出。

全程本地、无代理池；速率 = MediaCrawler 原有基准 ×2（见 app_config）。
"""
import asyncio
import json
import random
import time

import app_config
from core.xhs_client import XhsClient
from predictor.occupation import predict_occupation


class CrawlTask:
    """一次抓取任务的状态容器，供 Web 层查询/控制。"""

    def __init__(self, max_creators: int, mode: str = None, industries: list = None):
        # mode: login=扫码登录后采集（风险集中在「账号」，可能被限流/封号）
        #       guest=游客模式（免登录）。**实测**：免登录时博主主页返回完整 SSR HTML，
        #             昵称/小红书号/简介/IP属地 都能解析出来（字段并不比登录少），
        #             代价是风险从「账号」转移到「IP」——匿名流量更容易触发
        #             「安全限制」拦截页，故 guest 模式单次上限更小、节奏更慢。
        self.mode = mode if mode in ("login", "guest") else app_config.DEFAULT_MODE
        cap = app_config.GUEST_MAX_CREATORS if self.mode == "guest" else app_config.MAX_CREATORS_HARD_LIMIT
        self.max_creators = max(1, min(max_creators, cap))
        self.industries = self._normalize_industries(industries)
        self.state = "idle"            # idle|running|stopping|done|error|stopped
        self.phase = ""
        self.results = []
        self.error = None
        self.started_at = None
        self.finished_at = None
        self._stop_flag = False

    def stop(self):
        self._stop_flag = True
        if self.state == "running":
            self.state = "stopping"

    def snapshot(self):
        return {
            "state": self.state,
            "mode": self.mode,
            "phase": self.phase,
            "error": self.error,
            "target": self.max_creators,
            "collected": len(self.results),
            "results": self.results,
        }

    # ------------------------------------------------------------------ #
    # ------------------ 行业筛选（关键词搜索） ------------------ #
    def _normalize_industries(self, industries) -> list:
        """把前端传来的行业选择整理成「搜索关键词」列表。

        规则：
          - 元素命中 INDUSTRY_PRESETS 的行业名 → 展开成该行业的全部搜索词；
          - 否则当作自定义关键词原样使用（可直接填「露营」「咖啡探店」这类短语）；
          - 跨行业去重，并用 INDUSTRY_MAX_KEYWORDS 限流（关键词太多会跑很久且更易触发风控）。
        """
        out, seen = [], set()
        for raw in (industries or []):
            name = str(raw).strip()
            if not name:
                continue
            words = app_config.INDUSTRY_PRESETS.get(name) or [name]
            for w in words:
                w = str(w).strip()
                if not w or w in seen:
                    continue
                seen.add(w)
                out.append(w)
                if len(out) >= app_config.INDUSTRY_MAX_KEYWORDS:
                    return out
        return out

    @staticmethod
    def _channel_of(kw):
        """关键词 → 行业频道 ID。

        用户选的是行业名（旅游/美食…），而 industry 里是「展开后的搜索词」
        （旅游 → 旅游攻略、旅行vlog…），所以这里两种都要认：
          · 直接命中行业名；
          · 命中某个行业预设里的任一搜索词，则用该行业的频道。
        都没命中（纯自定义关键词，如「露营」）→ 返回空，走关键词搜索。
        """
        if not kw:
            return ""
        kw = str(kw).strip()
        if kw in app_config.INDUSTRY_CHANNELS:
            return app_config.INDUSTRY_CHANNELS[kw]
        for ind, words in app_config.INDUSTRY_PRESETS.items():
            if kw in (words or []):
                cid = app_config.INDUSTRY_CHANNELS.get(ind)
                if cid:
                    return cid
        return ""

    async def _discover_by_industry(self, br, client) -> list:
        """按行业定向取候选博主，每个关键词走两条路（跨关键词去重）：

        1) 行业频道流：/explore?channel_id=xxx —— 内容按行业组织，游客态即可用；
           app_config.INDUSTRY_CHANNELS 里的 14 个频道 ID 均来自网页端官方 JS 并逐个实测，
           内容与行业对得上，从业者命中率最高。
        2) 关键词搜索：接口 POST /api/sns/web/v1/search/notes（需登录态），失败再退到
           搜索页 DOM 兜底。注意：游客态接口会返回 -104「当前登录的账号没有权限访问」。
        相比随机推荐流，这两条路拿到的候选都更贴近目标行业，「推测职业」命中率更高。
        """
        want = max(self.max_creators * app_config.INDUSTRY_CANDIDATE_MULTIPLIER,
                   self.max_creators + 5)
        per_kw = max(5, want // max(1, len(self.industries)) + 1)

        creators, seen = [], set()
        used_channels = set()
        for i, kw in enumerate(self.industries, 1):
            if self._stop_flag or len(creators) >= want:
                break
            got = []
            cid = self._channel_of(kw)
            if cid and cid in used_channels:
                continue        # 同行业的其它展开词＝同一个频道，已经不重不漏地采过了
            if cid:
                # 1) 行业频道流：游客态即可用，内容贴合该行业，从业者命中率最高
                used_channels.add(cid)
                self.phase = "行业 %d/%d：正在浏览「%s」行业频道..." % (i, len(self.industries), kw)
                try:
                    got = await br.harvest_creators_by_channel(cid, per_kw)
                except Exception as e:
                    self.phase = "「%s」频道访问失败(%s)，改用关键词搜索..." % (kw, str(e)[:50])
                    got = []
            if not got:
                # 2) 关键词搜索（需要登录态；游客态接口会返回 -104「账号没有权限访问」）
                self.phase = "行业搜索 %d/%d：关键词「%s」..." % (i, len(self.industries), kw)
                try:
                    items = await asyncio.to_thread(
                        client.search_notes, kw, 1, app_config.INDUSTRY_SEARCH_PAGE_SIZE)
                    got = XhsClient.creators_from_search_items(items, kw)
                    if not got:
                        raise RuntimeError("搜索接口返回 0 条笔记")
                except Exception as e:
                    _msg = str(e)
                    if "-104" in _msg or "没有权限" in _msg:
                        # 游客态（未登录）：搜索页同样会被登录墙挡住，没必要再白等 30 秒
                        self.phase = "关键词「%s」需登录才能搜索（-104 无权限），跳过..." % kw
                    else:
                        self.phase = ("关键词「%s」接口搜索失败(%s)，回退浏览器搜索页..."
                                      % (kw, _msg[:60]))
                        try:
                            got = await br.harvest_creators_by_keyword(kw, per_kw)
                        except Exception as e2:
                            self.phase = "关键词「%s」浏览器搜索也失败：%s" % (kw, str(e2)[:60])
                            got = []
            for c in got:
                uid = c.get("user_id")
                if uid and uid not in seen:
                    seen.add(uid)
                    c.setdefault("source_keyword", kw)
                    creators.append(c)
            if len(creators) >= want:
                break
            await asyncio.sleep(random.uniform(1.5, 3.0))
        return creators[:want]

    async def run(self):
        self.state = "running"
        self.started_at = time.time()
        br = None
        try:
            try:
                from core.browser import XhsBrowser  # 惰性导入：无 playwright 时也能启动 Web 服务
            except ImportError as e:
                raise RuntimeError(
                    "缺少浏览器依赖 Playwright，无法开始采集。请先执行：\n"
                    "  pip install -r requirements.txt\n"
                    "  playwright install chromium\n"
                    f"原始错误：{e}"
                )
            br = XhsBrowser()

            self.phase = "正在启动浏览器..."
            await br.start()

            if self.mode == "guest":
                # 游客模式：不强制登录，直接采集公开页面。
                # 实测（Web 版）：免登录时 /user/profile/<uid> 返回完整 SSR HTML，
                #   昵称 / 小红书号 / 简介 / IP属地 全部可解析（core.xhs_client.parse_creator_from_html）。
                # 前提：必须先用真实浏览器把推荐流逛一遍，种下 acw_tc / websectiga / sec_poison_id
                #   等 WAF Cookie；否则同一 URL 只回 36KB 剥离页（无「小红书号」）。harvest_creators
                #   本身就会逛+滚动，因此下面的 cookies() 天然带完整匿名会话。
                # 若 user_data_dir 里本来就有登录态会自动沿用（更稳）。这里刻意不 save_state，
                # 以免把已有的登录态覆盖成游客态。
                self.phase = "游客模式：跳过登录，直接采集公开页面（免登录可拿全字段）..."
            else:
                self.phase = "请在浏览器中扫码登录（最长等待 %ds）..." % app_config.LOGIN_TIMEOUT_SEC

                def _tick(remain):
                    self.phase = f"等待扫码登录…剩余 {remain}s（请在浏览器中扫码）"

                try:
                    await br.wait_login(on_wait=_tick)
                except Exception as e:
                    # 把「用的哪个浏览器 / 当前页面 / 二维码是否可见 / 启动告警」一起报出来，
                    # 避免用户只看到一句超时、完全不知道卡在哪一步。
                    self.phase = "登录失败：%s | 浏览器=%s | 页面=%s | 二维码可见=%s | 启动提示=%s" % (
                        str(e).splitlines()[0][:200],
                        br.diag.get("channel"),
                        br.diag.get("login_url") or br.diag.get("title"),
                        br.diag.get("qr_visible"),
                        "；".join(br.warnings) if br.warnings else "无",
                    )
                    raise
                await br.save_state()

            cookies = await br.cookies()
            client = XhsClient(cookies)

            if self.industries:
                # ===== 先筛选行业：行业频道流 / 关键词搜索 → 取作者 → 再抓主页 =====
                creators = await self._discover_by_industry(br, client)
                if not creators:
                    # 行业路全灭（常见原因：该行业没配频道 + 游客态搜索被 -104 拒绝）。
                    # 与其直接失败，不如退回随机推荐流，至少能出结果，并把原因写进阶段文案。
                    self.phase = ("行业筛选没取到博主（该行业暂无频道，关键词搜索又需要登录态），"
                                  "已回退到随机推荐流；想按关键词精确搜索请改用「登录模式」...")
                    creators = await br.harvest_creators(self.max_creators)
                    if not creators:
                        raise RuntimeError(
                            "未能按行业「%s」采到博主：该行业暂无可用频道，关键词搜索需要登录态"
                            "（游客态接口返回 -104 无权限），随机推荐流也没取到内容。"
                            "建议：① 改用有频道的行业（旅游/美食/穿搭/美妆/职场/情感/影视/"
                            "家居/游戏/宠物/健身）；② 或先登录再重试。"
                            % "、".join(self.industries))
            else:
                # ===== 原行为：随机刷推荐流 =====
                self.phase = ("游客模式：正在采集推荐流中的博主..." if self.mode == "guest"
                              else "登录成功，正在采集主页推荐流中的博主...")
                creators = await br.harvest_creators(self.max_creators)
                if not creators:
                    hint = ("游客模式下推荐流常被登录墙遮挡，建议改用登录模式，或先手动在浏览器里登录一次"
                            if self.mode == "guest" else "请确认已登录且推荐页有内容")
                    raise RuntimeError("未能从推荐流采集到博主，" + hint)

            self.phase = f"开始抓取 {len(creators)} 个博主资料..."
            for idx, c in enumerate(creators, 1):
                if self._stop_flag:
                    self.state = "stopped"
                    break
                if len(self.results) >= self.max_creators:
                    break       # 已采够用户设定的数量（行业路会多准备候选，这里截断）
                uid = c["user_id"]
                try:
                    info = await asyncio.to_thread(client.get_creator_info, uid)
                except Exception as e:
                    info = {"nickname": c.get("nickname_raw", ""), "red_id": "", "desc": "", "_err": str(e)}

                # 风控识别：HTTP 200 但页面里没有「小红书号」→ 大概率被拦成精简/「安全限制」页
                # （匿名流量更易触发）。退避一段时间后重试一次，多数情况下可恢复。
                _dbg0 = info.get("_debug") or {}
                if _dbg0.get("http") == 200 and not _dbg0.get("page_says_redid"):
                    self.phase = f"[{idx}/{len(creators)}] 疑似被风控，退避重试..."
                    await asyncio.sleep(random.uniform(*app_config.RETRY_BACKOFF_SEC))
                    try:
                        info = await asyncio.to_thread(client.get_creator_info, uid)
                    except Exception as e:
                        info = {"nickname": c.get("nickname_raw", ""), "red_id": "", "desc": "", "_err": str(e)}

                # HTTP 拿不到关键字段（昵称/小红书号）时，用浏览器（真实登录态）兜底补抓
                if not info.get("red_id") or not info.get("nickname"):
                    self.phase = f"[{idx}/{len(creators)}] 字段缺失，改用浏览器补抓..."
                    try:
                        fb = await br.fetch_profile(uid, c.get("xsec_token", ""))
                    except Exception:
                        fb = None
                    if fb:
                        for k in ("nickname", "red_id", "desc", "profession"):
                            if not info.get(k) and fb.get(k):
                                info[k] = fb[k]
                                if k == "red_id":
                                    info["_red_id_src"] = fb.get("_red_id_src", "browser_state")

                nickname = info.get("nickname") or c.get("nickname_raw") or uid
                desc = info.get("desc", "")
                red_id = info.get("red_id", "")
                # 显式职业字段优先：主页直接写了「职业」字段时直接采用（高置信），
                # 否则才交给规则引擎推测（两级策略：精确路线 + 召回路线）。
                explicit_prof = (info.get("profession") or "").strip()
                if explicit_prof:
                    occ = {"occupation": explicit_prof, "category": "主页显式字段",
                           "confidence": "高", "evidence": ["主页显式职业字段"], "score": 0.0}
                else:
                    occ = predict_occupation(nickname, desc)

                # 备注：区分「抓取失败」与「账号本身没设小红书号」，避免误以为程序有 bug
                red_id_src = info.get("_red_id_src", "")
                if info.get("_err"):
                    note = "抓取异常：" + str(info["_err"])[:60]
                elif red_id:
                    note = "小红书号来源：" + {
                        "api": "主页接口", "html_text": "主页HTML", "dom_text": "页面文本",
                        "browser_state": "浏览器登录态", "html_ssr": "主页HTML(SSR)",
                    }.get(red_id_src, "已获取")
                else:
                    dbg = info.get("_debug") or {}
                    if dbg and (dbg.get("html_len", 0) < 60000 or not dbg.get("page_says_redid")):
                        note = ("疑似被 IP 级风控拦成精简页（页面无「小红书号」），"
                                "建议降低频率/稍后重试"
                                + ("；也可改用登录模式" if self.mode == "guest" else ""))
                    elif dbg and not dbg.get("has_user_page_data"):
                        note = "未取到主页资料（可能未登录/被风控，建议稍后重试或重新扫码登录）"
                    else:
                        note = "该账号未设置小红书号"

                self.results.append({
                    "user_id": uid,
                    "nickname": nickname,
                    "industry": c.get("source_keyword", "") or ("随机推荐流" if not self.industries else "、".join(self.industries)),
                    "industry_source": c.get("source", "feed"),   # search_api / search_dom / feed
                    "red_id": red_id,          # 小红书号
                    "desc": desc,              # 简介（保留以便核对）
                    "ip_location": info.get("ip_location", ""),  # IP属地（免登录 SSR 页即可拿到）
                    "occupation": occ["occupation"],
                    "category": occ["category"],
                    "confidence": occ["confidence"],
                    "evidence": "、".join(occ["evidence"]),
                    "red_id_src": red_id_src,
                    "note": note,
                    "mode": self.mode,
                })
                self.phase = f"已抓取 {idx}/{len(creators)}：{nickname} -> {occ['occupation']}（{occ['confidence']}）"

                if idx < len(creators):
                    if idx % app_config.LONG_PAUSE_EVERY == 0:
                        self.phase += f"（长休息 {app_config.LONG_PAUSE_SEC:.0f}s）"
                        await asyncio.sleep(app_config.LONG_PAUSE_SEC)
                    else:
                        await asyncio.sleep(random.uniform(app_config.MIN_SLEEP_SEC, app_config.MAX_SLEEP_SEC))

            if self.state not in ("stopped",):
                self.state = "done"
            self.phase = "完成"
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "executable doesn't exist" in low or "please run the following command" in low:
                msg += "\n提示：浏览器内核未安装，请执行  playwright install chromium"
            self.error = msg
            self.state = "error"
            self.phase = f"出错：{msg}"
        finally:
            try:
                await br.close()
            except Exception:
                pass
            self.finished_at = time.time()
            self._dump()

    def _dump(self):
        try:
            with open(app_config.RESULT_JSON, "w", encoding="utf-8") as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
