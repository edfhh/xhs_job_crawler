# -*- coding: utf-8 -*-
"""
中文职业预测引擎。

适配自 TimFaverjon/twitter_profile_predictor 的 bios_analyzer：
原项目用「关键词/短语 -> 职业 -> PCS 分组」的规则表对法语简介做加权命中打分，
这里把规则表换成中文（predictor/professions_zh.json），输入改为「昵称 + 简介」。
"""
import json
import os
import re
import unicodedata

_DICT_PATH = os.path.join(os.path.dirname(__file__), "professions_zh.json")

_professions = []
try:
    with open(_DICT_PATH, encoding="utf-8") as f:
        _professions = json.load(f).get("professions", [])
except Exception:
    _professions = []


def _normalize(text: str) -> str:
    if not text:
        return ""
    # 全角 -> 半角，去零宽字符
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return text.lower()


def _kw_hit(k: str, text: str) -> bool:
    """关键词命中判断。纯 ASCII 字母关键词要求词边界：前后不能是英文字母，
    避免「pe」误中「peace」、「pm」误中「spm」这类 substring 误判。
    中文关键词保持子串匹配。"""
    if not k:
        return False
    idx = text.find(k)
    while idx != -1:
        if k.isascii() and k.isalpha():
            before = text[idx - 1] if idx > 0 else ""
            after = text[idx + len(k)] if idx + len(k) < len(text) else ""
            if not (before.isascii() and before.isalpha()) \
                    and not (after.isascii() and after.isalpha()):
                return True
        else:
            return True
        idx = text.find(k, idx + 1)
    return False


def predict_occupation(nickname: str = "", desc: str = "") -> dict:
    """返回 {occupation, category, evidence:[...], score}。

    打分：简介权重 1.0，昵称权重 0.5；关键词越长（越具体）权重越高。
    命中的关键词作为 evidence，便于人工核对（避免「瞎猜」）。
    """
    nick = _normalize(nickname)
    bio = _normalize(desc)

    best = {"occupation": "未识别", "category": "未知", "evidence": [], "score": 0.0}

    for prof in _professions:
        score = 0.0
        hits = []
        from_bio = False
        for kw in prof.get("keywords", []):
            k = _normalize(kw)
            if not k:
                continue
            in_bio = _kw_hit(k, bio)
            in_nick = _kw_hit(k, nick)
            if in_bio or in_nick:
                w = len(k) * (1.0 if in_bio else 0.5)
                score += w
                hits.append((kw, w))
                if in_bio:
                    from_bio = True
        if score > best["score"]:
            hits.sort(key=lambda x: x[1], reverse=True)
            best = {
                "occupation": prof["profession"],
                "category": prof.get("category", "未知"),
                "evidence": [h[0] for h in hits[:5]],
                "score": round(score, 2),
                "_from_bio": from_bio,
            }

    best["confidence"] = _confidence(best["score"], best.pop("_from_bio", False))
    return best


def _confidence(score: float, from_bio: bool) -> str:
    """置信度：无命中=无；仅靠昵称的弱信号一律为低；否则按得分分档。"""
    if score <= 0:
        return "无"
    if not from_bio:
        return "低"          # 只有昵称里有词，简介为空/无信息
    if score < 2:
        return "低"
    if score < 5:
        return "中"
    return "高"


if __name__ == "__main__":
    samples = [
        ("", "95后前端开发 | 每天写代码 | 分享职场干货"),
        ("咖啡师小鹿", "手冲咖啡 | 拉花 | 开了一家小店"),
        ("", "三甲医院儿科医生，科普育儿知识"),
        ("", "全职妈妈 带娃日常 好物分享"),
        ("", "在读研究生，备考中"),
    ]
    for n, d in samples:
        print(n or "(无昵称)", "|", d[:24], "=>", predict_occupation(n, d))
