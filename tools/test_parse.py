# -*- coding: utf-8 -*-
"""离线单测：小红书主页字段解析（不联网）。验证 multi-path + 文本兜底。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.xhs_client import parse_creator, extract_red_id_from_text  # noqa: E402

ok = 0
fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  [PASS] {name}: {got!r}")
    else:
        fail += 1
        print(f"  [FAIL] {name}: got={got!r} want={want!r}")


print("== parse_creator ==")
# 1) 标准路径
c = parse_creator({"basicInfo": {"nickname": "星星妈妈", "redId": "xh123", "desc": "母婴好物"}})
check("nickname", c["nickname"], "星星妈妈")
check("redId->red_id", c["red_id"], "xh123")
check("desc", c["desc"], "母婴好物")

# 2) 新版驼峰/下划线变体
c = parse_creator({"basicInfo": {"nickName": "A", "red_id": "abc"}})
check("nickName", c["nickname"], "A")
check("red_id", c["red_id"], "abc")

# 3) 字段被包在更深层（改版兜底）
c = parse_creator({"x": {"y": {"basicInfo": {"redID": "xyz"}}}})
check("deep redID", c["red_id"], "xyz")

# 4) 空对象 / None
for empty in ({}, {"basicInfo": {}}, {"basicInfo": None}, None):
    c = parse_creator(empty)
    check(f"empty {empty}", (c["nickname"], c["red_id"], c["desc"]), ("", "", ""))

# 5) 空字符串不算命中
c = parse_creator({"basicInfo": {"redId": "   ", "nickname": ""}})
check("blank ignored", (c["nickname"], c["red_id"]), ("", ""))

print("== extract_red_id_from_text ==")
check("半角冒号", extract_red_id_from_text("主页 小红书号：abc_123 关注"), "abc_123")
check("全角冒号", extract_red_id_from_text("小红书号:xyz-9"), "xyz-9")
check("同行多信息", extract_red_id_from_text("昵称\n小红书号：demo12345\nIP属地：北京"), "demo12345")
check("无字段", extract_red_id_from_text("感谢关注 每天更新"), "")
check("空文本", extract_red_id_from_text(""), "")

print(f"\n结果: PASS={ok} FAIL={fail}")
sys.exit(1 if fail else 0)
