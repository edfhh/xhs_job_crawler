# -*- coding: utf-8 -*-
"""
极简 Web 服务：只提供 开始 / 停止 / 状态 / 导出 四个接口 + 一个极简页面。
"""
import asyncio
import csv
import io
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

import app_config
from core.crawler import CrawlTask
from predictor.occupation import predict_occupation

app = FastAPI(title="XHS 博主职业采集")
_INDEX = os.path.join(os.path.dirname(__file__), "index.html")

_state = {"task": CrawlTask(app_config.DEFAULT_MAX_CREATORS), "handle": None}


def _index_html():
    import json
    with open(_INDEX, encoding="utf-8") as f:
        html = f.read()
    # 把「行业预设」注入页面，前端无需再加接口；注入失败时页面用内置兜底列表
    presets = json.dumps(app_config.INDUSTRY_PRESETS, ensure_ascii=False)
    return html.replace("/*__INDUSTRY_PRESETS__*/{}", presets)


@app.get("/")
def index():
    return HTMLResponse(_index_html())


@app.post("/api/start")
async def api_start(body: dict | None = None):
    handle = _state["handle"]
    if handle and not handle.done():
        return JSONResponse({"ok": False, "msg": "已有任务在运行，请先停止"}, status_code=409)
    count = app_config.DEFAULT_MAX_CREATORS
    if body and body.get("count"):
        try:
            count = int(body["count"])
        except Exception:
            count = app_config.DEFAULT_MAX_CREATORS
    mode = getattr(app_config, "DEFAULT_MODE", "guest")
    if body and str(body.get("mode", "")) in ("login", "guest"):
        mode = str(body.get("mode"))
    # 行业筛选：接收「预设行业名」与「自定义关键词」的混合列表（也兼容逗号分隔字符串）
    industries = []
    if body:
        raw = body.get("industries")
        if isinstance(raw, str):
            raw = raw.replace("，", ",").replace("、", ",").replace(" ", ",").split(",")
        if isinstance(raw, (list, tuple)):
            industries = [str(x).strip() for x in raw if str(x).strip()]
    task = CrawlTask(count, mode=mode, industries=industries)
    _state["task"] = task
    _state["handle"] = asyncio.create_task(task.run())
    return {"ok": True, "count": task.max_creators, "mode": task.mode,
            "industries": task.industries}


@app.post("/api/stop")
def api_stop():
    _state["task"].stop()
    return {"ok": True}


# 演示数据：不联网、不登录，仅用于预览表格与导出效果
_DEMO = [
    ("5f1a2b3c0000000000000001", "小甜乖乖", "", ""),
    ("5f1a2b3c0000000000000002", "星星妈妈有点闲～",
     "两个孩子的妈妈｜分享母婴好物｜育儿知识",
     "1234567890"),
    ("5f1a2b3c0000000000000003", "小琪影视", "感谢关注 感谢喜欢 每天持续更新", "qyx2020"),
    ("5f1a2b3c0000000000000004", "阿沁的日常", "前端开发工程师｜分享代码与生活", "aqin_daily"),
    ("5f1a2b3c0000000000000005", "了改_sleep baccano", "", ""),
]


@app.post("/api/demo")
def api_demo():
    """注入演示数据（非真实抓取），便于先验证页面显示与导出格式。"""
    task = _state["task"]
    if task.state == "running":
        return JSONResponse({"ok": False, "msg": "任务运行中，请先停止"}, status_code=409)
    rows = []
    for uid, nick, desc, red_id in _DEMO:
        occ = predict_occupation(nick, desc)
        rows.append({
            "user_id": uid, "nickname": nick, "red_id": red_id, "desc": desc,
            "occupation": occ["occupation"], "category": occ["category"],
            "confidence": occ["confidence"], "evidence": "、".join(occ["evidence"]),
            "red_id_src": "demo",
            "note": "演示数据" if red_id else "该账号未设置小红书号",
        })
    task.results = rows
    task.state = "done"
    task.phase = "演示数据（非真实抓取，仅供预览）"
    return {"ok": True, "count": len(rows)}


@app.get("/api/status")
def api_status():
    return _state["task"].snapshot()


@app.get("/api/export")
def api_export(fmt: str = "csv"):
    rows = _state["task"].results
    header = ["昵称", "来源行业/关键词", "小红书号", "IP属地", "推测职业", "职业大类", "置信度", "命中依据", "简介", "备注", "用户ID"]

    def row_of(r):
        return [r.get("nickname", ""), r.get("industry", ""), r.get("red_id", ""), r.get("ip_location", ""),
                r.get("occupation", ""),
                r.get("category", ""), r.get("confidence", ""), r.get("evidence", ""),
                r.get("desc", ""), r.get("note", ""), r.get("user_id", "")]

    if fmt == "xlsx":
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "博主职业"
            ws.append(header)
            for r in rows:
                ws.append(row_of(r))
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=creators.xlsx"},
            )
        except Exception:
            pass  # 回退到 CSV

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM，Excel 打开不乱码
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(row_of(r))
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=creators.csv"},
    )
