# -*- coding: utf-8 -*-
"""自检：行业筛选（不联网、不启浏览器）。

    python tools/test_industry.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app_config
from core.crawler import CrawlTask
from core.xhs_client import XhsClient

FAIL = []


def eq(got, want, label):
    ok = got == want
    if not ok:
        FAIL.append("%s: got=%r want=%r" % (label, got, want))
    print(("  OK   " if ok else "  FAIL ") + label + " -> " + repr(got))


print("[1] 行业预设展开 / 自定义关键词")
eq(CrawlTask(5, industries=[]).industries, [], "不选行业 → 空（走原随机推荐流）")
eq(CrawlTask(5, industries=["旅游"]).industries,
   app_config.INDUSTRY_PRESETS["旅游"], "选「旅游」→ 展开成预设搜索词")
eq(CrawlTask(5, industries=["露营"]).industries, ["露营"], "自定义「露营」→ 原样使用")
eq(CrawlTask(5, industries=["旅游", "露营"]).industries,
   app_config.INDUSTRY_PRESETS["旅游"] + ["露营"], "预设 + 自定义 混合")
eq(CrawlTask(5, industries=["旅游", "旅游"]).industries,
   app_config.INDUSTRY_PRESETS["旅游"], "重复行业 → 去重")
eq(CrawlTask(5, industries=["  ", ""]).industries, [], "空白项 → 忽略")
many = CrawlTask(5, industries=["摄影", "美妆", "健身", "美食", "宠物"])
eq(len(many.industries) <= app_config.INDUSTRY_MAX_KEYWORDS, True,
   "关键词总数受限（<=%d），实际=%d" % (app_config.INDUSTRY_MAX_KEYWORDS, len(many.industries)))

print("[2] 搜索结果 → 候选博主（过滤非笔记项 + 按作者去重）")
items = [
    {"model_type": "note", "xsec_token": "tk1",
     "note_card": {"display_title": "云南攻略",
                   "user": {"user_id": "u1", "nickname": "阿May"}}},
    {"model_type": "note", "xsec_token": "tk2",
     "note_card": {"display_title": "同一个作者的另一篇",
                   "user": {"user_id": "u1", "nickname": "阿May"}}},
    {"model_type": "hot_query", "note_card": {}},                  # 非笔记项 → 丢弃
    {"model_type": "note", "note_card": {"user": {}}},             # 无 user_id → 丢弃
    {"model_type": "note", "xsec_token": "tk3",
     "note_card": {"display_title": "露营装备清单",
                   "user": {"user_id": "u2", "nickname": "老周"}}},
]
cands = XhsClient.creators_from_search_items(items, "旅游")
eq([c["user_id"] for c in cands], ["u1", "u2"], "同一作者只保留一次")
eq(cands[0]["nickname_raw"], "阿May", "昵称提取")
eq(cands[0]["source_keyword"], "旅游", "带上来源关键词（导出为「来源行业」列）")
eq(cands[0]["xsec_token"], "tk1", "带上 xsec_token（后面抓主页要用）")
eq(cands[0]["source"], "search_api", "标记来源为接口搜索")

print()
print("[3] 关键词 → 行业频道解析（_channel_of）")
eq(CrawlTask._channel_of("旅游"), "homefeed.travel_v3", "行业名 旅游 → travel_v3")
eq(CrawlTask._channel_of("旅游攻略"), "homefeed.travel_v3", "预设展开词 旅游攻略 → travel_v3")
eq(CrawlTask._channel_of("旅行vlog"), "homefeed.travel_v3", "预设展开词 旅行vlog → travel_v3")
eq(CrawlTask._channel_of("美食探店"), "homefeed.food_v3", "预设展开词 美食探店 → food_v3")
eq(CrawlTask._channel_of("装修"), "homefeed.household_product_v3",
   "家居预设词 装修 → household_product_v3")
eq(CrawlTask._channel_of("宠物"), "homefeed.pet", "行业名 宠物 → pet")
eq(CrawlTask._channel_of("露营"), "", "纯自定义词 露营 → 空（走关键词搜索）")
eq(CrawlTask._channel_of("摄影"), "", "暂无频道的行业 摄影 → 空（走关键词搜索）")
eq(CrawlTask._channel_of(""), "", "空词 → 空")
eq(CrawlTask._channel_of(None), "", "None → 空")
eq(len(app_config.INDUSTRY_CHANNELS) >= 10, True,
   "频道表非空（%d 个行业名/别名）" % len(app_config.INDUSTRY_CHANNELS))
bad = sorted({v for v in app_config.INDUSTRY_CHANNELS.values() if not v.startswith("homefeed")})
eq(bad, [], "频道 ID 前缀均为 homefeed（防手抖）")
eq(app_config.CHANNEL_URL % "homefeed.travel_v3",
   "https://www.xiaohongshu.com/explore?channel_id=homefeed.travel_v3", "频道 URL 拼接")

print()
if FAIL:
    print("FAILED %d 项：" % len(FAIL))
    for f in FAIL:
        print("  - " + f)
    sys.exit(1)
print("全部通过 ✅")
