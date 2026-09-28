# -*- coding: utf-8 -*-
"""
风控核心 #2 + 数据抓取：轻量小红书 Web 客户端。

保留可用的「签名请求 + 主页解析」能力，去掉 MediaCrawler 里的多平台、代理池、
DB 存储、评论/搜索等一切无关逻辑。只做三件事：
  1) get_home_recommend()  取主页推荐流里的笔记作者(user)
  2) get_creator_info()    取博主主页：昵称 / 小红书号 / 简介
  3) get_note_by_id()      取单条笔记（含作者），作为推荐流的兜底手段
"""
import json
import re
import random
import time

import requests

from . import sign

EDITH = "https://edith.xiaohongshu.com"
WEB = "https://www.xiaohongshu.com"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _base_headers(referer=f"{WEB}/"):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/json;charset=UTF-8",
        "origin": WEB,
        "referer": referer,
        "user-agent": UA,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
    }


def cookie_str(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


def extract_initial_state(html: str) -> dict:
    """从主页 HTML 中解析 window.__INITIAL_STATE__。

    参考 MediaCrawler/media_platform/xhs/extractor.py。
    """
    m = re.search(r"<script>window\.__INITIAL_STATE__=(\{.*?\})</script>", html, re.S)
    if not m:
        return {}
    raw = m.group(1).replace("undefined", "null")
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _first_str(d: dict, keys) -> str:
    for k in keys:
        v = (d or {}).get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _deep_get(obj, keys) -> str:
    """在嵌套 dict/list 中广度优先查找第一个命中的 key（应对新版小红书字段路径变化）。"""
    from collections import deque
    q = deque([obj])
    while q:
        cur = q.popleft()
        if isinstance(cur, dict):
            for k in keys:
                v = cur.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(cur, list):
            for v in cur:
                if isinstance(v, (dict, list)):
                    q.append(v)
    return ""


_RED_ID_KEYS = ["redId", "red_id", "redID", "redid", "redidStr"]

# 主页资料里可能出现的「显式职业」字段候选：命中即视为官方标称职业，
# 优先于规则引擎推测（置信度更高，如「职业：医生」这类主页直接写的字段）。
_PROFESSION_KEYS = ["profession", "occupation", "career", "job", "professional"]

# 主页 DOM 文本里的「小红书号：xxx」兜底（比 JSON 路径更抗改版）
_RED_ID_TEXT_RE = re.compile(r"小红书号\s*[:：]\s*([A-Za-z0-9_\-.]+)")


def extract_red_id_from_text(text: str) -> str:
    """从页面纯文本中提取小红书号，找不到返回空串。"""
    if not text:
        return ""
    m = _RED_ID_TEXT_RE.search(text)
    return m.group(1).strip() if m else ""


def _json_object_at(text: str, key: str):
    """在 text 中定位 `"key":{` 并从该 `{` 起做括号配对，返回解析后的 dict（失败返回 None）。

    存在原因：主页 `window.__INITIAL_STATE__` 是 JS 字面量，含 `undefined` 等非法 token，
    整块 json.loads 会失败（实测 29595 字符里第 29209 字节处崩）；但我们只关心
    `userPageData` 这一小块，它自身是合法 JSON，定向配对即可稳定取出。
    """
    if not text:
        return None
    idx = text.find('"%s":' % key)
    while idx != -1:
        start = text.find("{", idx)
        if start == -1:
            return None
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start:i + 1]
                    for cand in (chunk, chunk.replace("undefined", "null")):
                        try:
                            return json.loads(cand)
                        except Exception:
                            pass
                    break
        idx = text.find('"%s":' % key, idx + 1)
    return None


def parse_creator_from_html(html: str) -> dict:
    """从博主主页 HTML 解析资料（**免登录 SSR 页面同样带完整数据**）。

    实测免登录页面结构（2024 版 Web）：
      <div class="user-name">昵称</div>
      <span class="user-redId">小红书号：123456789</span>
      <span class="user-IP"> IP属地：示例省</span>
      <div class="user-desc" ...>简介</div>
      且 window.__INITIAL_STATE__ -> userPageData.basicInfo
        含 nickname / redId / desc / ipLocation。
    健壮性：JSON 优先，DOM class 兜底，任一命中即返回。
    """
    out = {"nickname": "", "red_id": "", "desc": "", "ip_location": "", "profession": ""}
    upd = _json_object_at(html, "userPageData")
    if isinstance(upd, dict):
        bi = upd.get("basicInfo") or {}
        out["nickname"] = _first_str(bi, ["nickname", "nickName"])
        out["red_id"] = _first_str(bi, _RED_ID_KEYS)
        out["desc"] = _first_str(bi, ["desc", "description"])
        out["ip_location"] = _first_str(bi, ["ipLocation", "ip_location"])
        out["profession"] = _first_str(bi, _PROFESSION_KEYS)

    if not out["red_id"]:
        m = re.search(r'user-redId[^>]*>\s*小红书号\s*[:：]\s*([^<\s]+)', html)
        if m:
            out["red_id"] = m.group(1).strip()
    if not out["nickname"]:
        m = re.search(r'<div class="user-name"[^>]*>(.*?)</div>', html, re.S)
        if m:
            out["nickname"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    if not out["desc"]:
        m = re.search(r'<div class="user-desc"[^>]*>(.*?)</div>', html, re.S)
        if m:
            out["desc"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    if not out["ip_location"]:
        m = re.search(r'user-IP[^>]*>\s*IP属地\s*[:：]\s*([^<]+)<', html)
        if m:
            out["ip_location"] = m.group(1).strip()
    return out


def parse_creator(user_page_data: dict) -> dict:
    """从 userPageData 抽取字段；路径做多级容错，避免改版后整列变空。"""
    data = user_page_data or {}
    bi = data.get("basicInfo") or {}
    return {
        "nickname": _first_str(bi, ["nickname", "nickName"]) or _deep_get(data, ["nickname", "nickName"]),
        "red_id": _first_str(bi, _RED_ID_KEYS) or _deep_get(data, _RED_ID_KEYS),
        "desc": _first_str(bi, ["desc", "description"]) or _deep_get(data, ["desc", "description"]),
        "gender": bi.get("gender"),
        "ip_location": _first_str(bi, ["ipLocation", "ip_location"]),
        "profession": _first_str(bi, _PROFESSION_KEYS) or _deep_get(data, _PROFESSION_KEYS),
    }


class XhsClient:
    def __init__(self, cookies: dict, timeout: int = 20):
        self.cookies = dict(cookies or {})
        self.timeout = timeout
        self.sess = requests.Session()
        self.sess.headers.update(_base_headers())

    # ------------------------------------------------------------------ #
    def _do_signed_post(self, uri: str, payload: dict) -> dict:
        headers = _base_headers()
        headers.update(sign.sign_post(uri, self.cookies, payload))
        headers["cookie"] = cookie_str(self.cookies)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        r = self.sess.post(EDITH + uri, headers=headers, data=body, timeout=self.timeout)
        return self._as_json(r)

    def _do_signed_get(self, uri: str, params: dict) -> dict:
        headers = _base_headers()
        headers.update(sign.sign_get(uri, self.cookies, params))
        headers["cookie"] = cookie_str(self.cookies)
        r = self.sess.get(EDITH + uri, headers=headers, params=params, timeout=self.timeout)
        return self._as_json(r)

    @staticmethod
    def _as_json(r: requests.Response) -> dict:
        try:
            return r.json()
        except Exception:
            return {"_http_status": r.status_code, "_text": r.text[:300]}

    # ------------------------------------------------------------------ #
    def get_home_recommend(self, num: int = 20, cursor_score: str = "", channel="homefeed_recommend"):
        """主页推荐流。返回 (items, next_cursor)。

        payload 结构对齐小红书 Web 端 /api/sns/web/v1/homefeed。
        注意：该接口字段可能随版本变化，失败时 crawler 会自动回退到浏览器 DOM 采作者。
        """
        uri = "/api/sns/web/v1/homefeed"
        payload = {
            "cursor_score": cursor_score,
            "num": num,
            "refresh_type": 1 if not cursor_score else 3,
            "note_index": 0,
            "unread_begin_note_id": "",
            "unread_end_note_id": "",
            "unread_note_count": 0,
            "category": channel,
            "search_key": "",
            "need_num": num,
            "image_formats": ["jpg", "webp", "avif"],
            "need_filter_image": False,
        }
        data = self._do_signed_post(uri, payload)
        d = data.get("data") or {}
        items = d.get("items") or []
        next_cursor = d.get("cursor_score") or d.get("cursor") or ""
        return items, next_cursor

    def get_note_by_id(self, note_id: str, xsec_token: str = "", xsec_source: str = "pc_feed"):
        uri = "/api/sns/web/v1/feed"
        payload = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": "1"},
            "xsec_source": xsec_source,
            "xsec_token": xsec_token,
        }
        data = self._do_signed_post(uri, payload)
        d = data.get("data") or {}
        items = d.get("items") or []
        return items[0] if items else {}

    # ==================== 关键词搜索（「先筛选行业」模式） ====================
    def search_notes(self, keyword: str, page: int = 1, page_size: int = 20) -> list:
        """按关键词搜索笔记，返回 items 列表。

        对应 Web 端搜索接口 /api/sns/web/v1/search/notes。
        注意：该接口比推荐流更吃登录态，未登录时可能返回空/被风控；
        调用方（CrawlTask）会在失败时自动回退到浏览器 DOM 搜索。
        """
        uri = "/api/sns/web/v1/search/notes"
        payload = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "search_id": "%d%03d" % (int(time.time() * 1000), random.randint(0, 999)),
            "sort": "general",
            "note_type": 0,
            "ext_flags": [],
            "image_formats": ["jpg", "webp", "avif"],
        }
        data = self._do_signed_post(uri, payload)
        d = data.get("data") or {}
        items = d.get("items") or []
        return items

    @staticmethod
    def creators_from_search_items(items, keyword: str = "") -> list:
        """把搜索 items 转成候选博主列表（过滤非笔记项 + 按 user_id 去重）。

        字段与 harvest_creators() 保持一致（user_id / nickname_raw / xsec_token），
        这样 crawler 后续流程（进主页抓资料 → 职业预测）无需改动。
        """
        out, seen = [], set()
        for it in items:
            model_type = it.get("model_type") or ""
            if model_type and model_type != "note":
                continue
            nc = it.get("note_card") or {}
            user = nc.get("user") or {}
            uid = user.get("user_id") or ""
            if not uid or uid in seen:
                continue
            seen.add(uid)
            out.append({
                "user_id": uid,
                "nickname_raw": user.get("nickname") or user.get("nick_name") or "",
                "xsec_token": user.get("xsec_token") or it.get("xsec_token") or "",
                "xsec_source": "pc_search",
                "source_keyword": keyword,
                "source": "search_api",
                "note_title": (nc.get("display_title") or "").strip(),
            })
        return out

    def get_creator_info(self, user_id: str) -> dict:
        """GET 博主主页 HTML 并解析。此处与 MediaCrawler 一致：不签名，仅带 Cookie。

        附带 `_debug`（HTTP 状态 / 是否解析到 state / 页面是否含「小红书号」），
        用于区分「账号本身未设置小红书号」与「未登录或被风控导致抓取失败」。
        """
        headers = _base_headers(referer=f"{WEB}/")
        headers["cookie"] = cookie_str(self.cookies)
        headers["accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        r = self.sess.get(f"{WEB}/user/profile/{user_id}", headers=headers, timeout=self.timeout)
        html = r.text or ""
        state = extract_initial_state(html)
        upd = (state.get("user") or {}).get("userPageData") or {}
        info = parse_creator(upd)

        # 兜底：免登录 SSR 页面同样带完整资料，用「定向 JSON + DOM class」补齐缺失字段
        ssr = parse_creator_from_html(html)
        for k in ("nickname", "red_id", "desc", "ip_location"):
            if not info.get(k) and ssr.get(k):
                info[k] = ssr[k]
        if info.get("red_id") and not info.get("_red_id_src"):
            info["_red_id_src"] = "html_ssr"
        if not info.get("red_id"):
            # 最后兜底：直接从 HTML 文本里抓「小红书号：xxx」
            rid = extract_red_id_from_text(html)
            if rid:
                info["red_id"] = rid
                info["_red_id_src"] = "html_text"
        info["_debug"] = {
            "http": r.status_code,
            "has_state": bool(state),
            "has_user_page_data": bool(upd),
            "html_len": len(html),
            "page_says_redid": "小红书号" in html,
            "ssr_fields": {k: bool(v) for k, v in ssr.items()},
        }
        return info


def me_guest_flag(cookies: dict, timeout: int = 15):
    """判断 Cookie 对应会话是否已登录。

    返回 True=游客未登录，False=已登录，None=接口不可用/语义未知。

    背景（实测）：小红书会给未登录游客也下发 web_session Cookie，
    因此 Cookie 不能作为登录判据；可靠判据是
    GET /api/sns/web/v2/user/me 的 data.guest（游客为 true）。
    """
    try:
        data = XhsClient(cookies, timeout=timeout)._do_signed_get("/api/sns/web/v2/user/me", {})
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    d = data.get("data")
    if isinstance(d, dict) and "guest" in d:
        return bool(d.get("guest"))
    if data.get("code") in (-101, -100) or data.get("success") is False:
        return True
    return None


def rand_sleep_range(min_s, max_s):
    import time
    time.sleep(random.uniform(min_s, max_s))
