# -*- coding: utf-8 -*-
"""
职业预测引擎 —— 离线测试入口（不依赖网络 / 浏览器）。

用法：
    # 方式1：直接传参（昵称|简介）
    python tools/predict_cli.py "咖啡师小鹿|手冲咖啡 拉花 开了家小店" "阿May|三甲医院儿科医生"

    # 方式2：从文件读取（每行一条：昵称<TAB>简介 或 昵称|简介；# 开头为注释）
    python tools/predict_cli.py -f data/sample_creators.tsv

    # 方式3：从标准输入逐行粘贴（Ctrl-D 结束）
    python tools/predict_cli.py -
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from predictor.occupation import predict_occupation  # noqa: E402


def parse_line(line: str):
    line = line.rstrip("\n")
    if not line.strip() or line.lstrip().startswith("#"):
        return None
    if "\t" in line:
        nick, desc = line.split("\t", 1)
    elif "|" in line:
        nick, desc = line.split("|", 1)
    else:
        s = line.strip()
        # 没有分隔符时的容错：较长的行视为「只有简介」，较短的行视为「只有昵称」
        if len(s) > 16 or any(ch in s for ch in "，。！？；、,.!?"):
            nick, desc = "", s
        else:
            nick, desc = s, ""
    return nick.strip(), desc.strip()


def run(pairs):
    rows = []
    for nick, desc in pairs:
        r = predict_occupation(nick, desc)
        rows.append((nick, desc, r))
    if not rows:
        print("(没有可测试的数据)")
        return
    w = 14
    print(f"{'昵称':<{w}} {'推测职业':<12} {'类别':<12} {'置信度':<6} 命中依据")
    print("-" * 84)
    for nick, desc, r in rows:
        ev = "、".join(r["evidence"]) or "-"
        print(f"{nick[:w]:<{w}} {r['occupation']:<12} {r['category']:<12} {r.get('confidence',''):<6} {ev}  [score={r['score']}]")
    print("-" * 84)
    print(f"共 {len(rows)} 条。置信度：高/中/低/无；仅昵称命中(无简介)一律为「低」，绝不硬猜。")


def main():
    ap = argparse.ArgumentParser(description="职业预测离线测试")
    ap.add_argument("items", nargs="*", help="昵称|简介 形式的条目")
    ap.add_argument("-f", "--file", help="从文件读取（每行 昵称<TAB>简介）")
    ap.add_argument("-", dest="stdin", action="store_true", help="从标准输入读取")
    args = ap.parse_args()

    pairs = [p for p in (parse_line(x) for x in args.items) if p]

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            pairs += [p for p in (parse_line(ln) for ln in f) if p]

    if args.stdin or (not pairs and not sys.stdin.isatty()):
        pairs += [p for p in (parse_line(ln) for ln in sys.stdin) if p]

    if not pairs:
        # 无参数则用内置样例做演示
        print("[未提供数据，使用内置样例演示]\n")
        pairs = [
            ("", "95后前端开发 | 每天写代码 | 分享职场干货"),
            ("咖啡师小鹿", "手冲咖啡 | 拉花 | 开了一家小店"),
            ("", "三甲医院儿科医生，科普育儿知识"),
            ("", "全职妈妈 带娃日常 好物分享"),
            ("", "在读研究生，备考中"),
        ]
    run(pairs)


if __name__ == "__main__":
    main()
