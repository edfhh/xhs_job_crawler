# -*- coding: utf-8 -*-
"""针对用户提供真实样例的测试（含无简介 / 无意义文本）。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from predictor.occupation import predict_occupation  # noqa: E402

CASES = [
    ("小甜乖乖", ""),
    ("星星妈妈有点闲～", "两个孩子的妈妈｜分享母婴好物｜育儿知识"),
    ("小琪影视", "感谢关注 感谢喜欢💕\n每天持续更新…"),
    ("了改_sleep baccano", ""),
    ("", "了改_sleep baccano 了改 sleep baccano"),
    ("", "感谢关注 感谢喜欢 每天持续更新 点个赞吧"),
]

print(f"{'昵称':<18} {'推测职业':<14} {'类别':<12} {'置信度':<6} {'score':<7} 命中依据")
print("-" * 96)
for nick, desc in CASES:
    r = predict_occupation(nick, desc)
    ev = "、".join(r["evidence"]) or "-"
    print(f"{(nick or '(空)')[:18]:<18} {r['occupation']:<14} {r['category']:<12} {r.get('confidence',''):<6} {r['score']:<7} {ev}")
print("-" * 96)
print("共 %d 条" % len(CASES))
