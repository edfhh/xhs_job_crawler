# 小红书博主职业采集器（xhs_job_crawler）项目报告

> 日期：2025-09-28 ｜ 范围：本地项目 `本地开发目录/xhs_job_crawler`
> 对外目标：小红书 Web（`https://www.xiaohongshu.com`），入口 `/explore` 与 `/user/profile/<uid>`
> 性质：授权范围内的非破坏性安全测试 + 工程交付

---

## 一、结论摘要（先说结果）

| # | 结论 | 级别 | 状态 |
|---|------|------|------|
| 1 | **免登录（游客态）即可越权读取博主主页全字段**：昵称、小红书号、简介、IP 属地 | High | 已复现 |
| 2 | 游客 Cookie 中同样存在 `web_session`，导致"以 Cookie 判登录"必然误判 | Medium | 已修复 |
| 3 | 登录模式（扫码）此前"窗口起来但空白/无法跳转" | 可用性缺陷 | 已修复并实测通过 |
| 4 | `window.__INITIAL_STATE__` 含 JS 字面量 `undefined`，整块 `json.loads` 必失败 | Low（工程） | 已修复 |
| 5 | 匿名流量易触发 IP 级风控（拦截页昵称显示"安全限制"） | Medium（环境） | 已缓解 |

**核心结论一句话**：小红书 Web 的博主主页 SSR HTML 在**游客态**下就返回完整身份信息（实测 174,851 字节、HTTP 200、非登录墙），
风险从"账号级"转移到"IP 级"——只要控制 IP 与请求节奏，无需任何账号即可批量获取博主身份数据。

---

## 二、项目是什么

一个小红书博主**职业推断**采集器：
用 Playwright 有头浏览器打开小红书，采集博主主页的公开字段（昵称 / 小红书号 / 简介 / IP 属地），
喂给 `predictor/` 规则引擎推断职业，最后导出 CSV，并在本地网页上操作与查看。

支持两种模式：
- **guest（游客/免登录）**：不用扫码，直接采集公开页面；
- **login（扫码登录）**：扫二维码登录后采集，字段更稳、不易被风控。

---

## 三、架构与目录

```
web/index.html  ──► web/server.py (FastAPI :8777) ──► core/crawler.py（编排/限速/去重/备注）
                                                        ├─ core/browser.py    Playwright 持久化上下文
                                                        ├─ core/xhs_client.py 签名接口 + SSR HTML 兜底解析
                                                        │   └─ core/sign.py   X-s / X-t 签名
                                                        └─ predictor/          职业推断规则引擎
run.py           启动入口
app_config.py    全部配置（浏览器/超时/上限/渠道）
tools/           自检脚本（verify_guest / diag_login* / test_parse）
data/            browser_user_data*（登录态）、导出数据
.venv/           虚拟环境（务必用它，系统 Python 有 PEP 668 + 缺 xhshow）
```

关键接口：
- `GET /api/sns/web/v2/user/me` → `{"code":0,"data":{"guest":true,"user_id":"..."}}`（判定游客态）
- `GET /user/profile/<uid>` → SSR HTML，内含 `window.__INITIAL_STATE__ → userPageData.basicInfo`
- 本地控制台：`/api/start`、`/api/stop`、`/api/status`、`/api/demo`、`/api/export`

---

## 四、发现详情

### 4.1 【High】免登录越权读取博主主页全字段

**路径**：`GET https://www.xiaohongshu.com/user/profile/<uid>`

**可复现步骤**
1. Playwright 持久化上下文打开 `/explore`，滚动 2~3 次（每次间隔约 1.5s），
   种下 `acw_tc` / `websectiga` / `sec_poison_id` / `a1` / `web_session` 等 WAF Cookie；
2. `context.cookies()` 取出全套**匿名** Cookie；
3. 带正常 UA / Referer GET 博主主页 → HTTP 200，返回 **174,851 字节**完整 SSR HTML（**不是登录墙**）；
4. 解析 `userPageData.basicInfo`：`nickname` / `redId` / `desc` / `ipLocation`；
   DOM 兜底 `.user-name` / `.user-redId` / `.user-IP` / `.user-desc`。

**实测证据**
```
nickname = 示例博主    red_id = 123456789
desc     = 还没有简介        ip_location = 示例省
me_guest_flag = True
GET /api/sns/web/v2/user/me → {'code':0,'data':{'guest':True,'user_id':'000000000000000000000000'}}
端到端：POST /api/start {"count":3,"mode":"guest"} → 3/3 拿到昵称+小红书号+真实简介
        备注列 = 小红书号来源：主页HTML(SSR)
```

**影响**：无需任何账号即可批量获取博主身份信息（昵称、小红书号、简介、IP 属地），
可进一步用于人肉画像、精准钓鱼或垃圾营销；风控成本由"账号"转移到"IP"。

**修复建议（服务端）**：主页 SSR 下发前做真正的登录态校验，游客态仅返回脱敏字段（隐藏小红书号 / IP 属地）；
对同一 IP 的 `/user/profile/*` 做频次限制与行为验证。

### 4.2 【Medium】游客也被下发 `web_session` → 登录判定误判

**现象**：游客态 Cookie 里同样有 `web_session`（len=38），旧逻辑"存在 web_session 即已登录"必然误判，
于是跳过扫码、字段抓不全（出现"昵称有、小红书号空"）。
**修复**：改为以 `GET /api/sns/web/v2/user/me` 的 `data.guest` 为准（`login_check=api`）。

### 4.3 【Low/工程】`__INITIAL_STATE__` 无法整体 `json.loads`

**原因**：该块是 JS 字面量，含 `undefined`。在 29,595 字符处、第 29,209 字节 `json.loads` 抛错。
**修复**：定位 `"userPageData":{` 后做括号配对提取子对象（`core.xhs_client._json_object_at`），再单独解析。

### 4.4 【可用性】登录模式"窗口起来但空白/无法跳转"—— 本次已修复

**根因（按可能性排序）**
1. **浏览器渠道与登录态目录混用**：Chrome 与 chromium 的 `user_data_dir` 互不兼容，
   用 chromium 建好的 profile 交给 Chrome 打开会被拒绝接管，症状正是"窗口空白、地址栏不跳转"。
   本机并无 Chrome（只有 `/usr/bin/chromium`），而配置里 `BROWSER_CHANNEL = "chrome"`。
2. 旧 `wait_login()` 用裸 `goto` 不校验落点（可能停在 `about:` / `chrome-error`），
   并主动去点「登录」按钮——而实测**二维码弹窗是 goto 后自动出现的，不需要点**。
3. 固定 `viewport={"width":1366,"height":900}` + 有头窗口易被压成小窗/被遮挡，观感上像"点不开"。
4. `SingletonLock` 残留（上一个实例未退干净）→ 新窗口空白。

**已落地修复**
- `app_config.py`：`BROWSER_CHANNEL` 默认改为空（用自带 chromium），支持 `XHS_CHANNEL=chrome` 显式指定；
  新增 `profile_dir()`（按渠道分目录）、`LOGIN_NAV_TIMEOUT_MS`、`LOGIN_QR_WAIT_SEC`、`LAUNCH_ARGS`（含 `--start-maximized`）。
- `core/browser.py`：`start()` 按渠道分目录 + `SingletonLock` 检测告警 + `viewport=None` + 渠道失败显式回退并记录原因；
  新增 `open_login_page()`（校验落点必须是 `xiaohongshu.com`，否则给出排查建议的明确报错）、
  `_login_box_visible()` / `_qr_ready()`；重写 `wait_login()`：
  **仅在弹窗不可见时**才点「登录」→ 等二维码渲染 → 轮询登录态 → 二维码过期自动点刷新（≤3 次）→ 超时抛出带诊断的错误。
- `core/crawler.py`：登录分支捕获异常并回报
  `登录失败：<原因> | 浏览器=<渠道> | 页面=<URL> | 二维码可见=<bool> | 启动提示=<...>`。

**实测验证（tool `tools/diag_login3.py`，约 30 秒）**
```
[1] 浏览器已启动   渠道: chromium(自带)   profile: data/browser_user_data   headless: False
[2] 页面已跳转     https://www.xiaohongshu.com/explore
    标题           小红书 - 你的生活兴趣社区
[3] 登录弹窗可见: True    二维码已渲染: True    已登录: False
结果：登录链路正常（窗口里应能看到二维码）。
```

### 4.5 【Medium/环境】IP 级风控

匿名流量易被拦（实测出现过昵称 `安全限制` 的拦截页）。脚本已内置：
HTTP 200 但无「小红书号」→ 判疑似风控 → 退避 8~15 秒重试一次；备注列会写明"疑似被 IP 级风控拦成精简页"。
**使用建议**：单次 ≤ 20（界面默认 10），跑完隔几分钟再跑，**不要并发**；连续风控则停手半小时或改用登录模式。

---

## 五、回归测试状态

| 检查项 | 结果 |
|--------|------|
| `py_compile`（app_config / run / core / web / predictor / tools） | 全部通过 |
| `tools/test_parse.py`（解析用例） | **PASS=16 FAIL=0** |
| `tools/diag_login3.py`（登录链路） | 跳转成功、二维码已渲染 |
| 游客态端到端（3 条） | 3/3 全字段，无风控 |

---

## 六、怎么跑（bash）

```bash
cd /path/to/xhs_job_crawler

# 1) 装依赖（务必用虚拟环境；系统 Python 有 PEP 668 且缺 xhshow）
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# 2) 起服务（有 X 显示时带上 DISPLAY，登录模式才看得到窗口）
DISPLAY=:0.0 .venv/bin/python run.py
# 浏览器打开 http://127.0.0.1:8777/

# 3) 只用 Chrome（本机装了 Google Chrome 时）
XHS_CHANNEL=chrome DISPLAY=:0.0 .venv/bin/python run.py

# 4) 一次性自检
DISPLAY=:0.0 .venv/bin/python tools/diag_login3.py     # 登录链路
.venv/bin/python tools/verify_guest.py                 # 游客态字段
.venv/bin/python tools/test_parse.py                   # 解析用例
```

## 七、说明与限制

- 仅用于授权范围内的安全测试与教学，请遵守目标站点服务条款与当地法律。
- 免登录越权读取属**服务端鉴权缺陷**，本项目的"免登录模式"正是该缺陷的可用性证明，不应对外滥用。
- 未使用任何真实账号；所有 Cookie 均为运行时获取的匿名游客态，未硬编码。
