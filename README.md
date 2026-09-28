# 小红书博主职业采集（xhs_job_crawler）

一个**本地运行**的轻量工具：从「主页推荐」流里采集博主昵称与简介，
并用规则引擎推测其职业。只保留「风控绕过 + 抓取 + 职业推断」这条链路，其余平台、代理池、
数据库、评论/搜索等功能全部移除。

支持两种采集模式，**默认游客模式（免登录）**：

| 模式 | 是否需要登录 | 能拿到的字段 | 主要风险 |
| --- | --- | --- | --- |
| **guest（默认）** | 否 | 昵称 / 小红书号 / 简介 / IP属地（实测均可拿到） | **IP 级风控**（匿名流量更易被拦成「安全限制」页） |
| login | 需要扫码 | 同上（走签名接口，更稳） | **账号级风控**（限流、异常登录） |

> 实测详情见下文「免登录（游客）模式实测结论」。

## 来源与改造

| 组件 | 来源 | 改造点 |
| --- | --- | --- |
| 签名绕过 | [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的 `playwright_sign.py` / `xhs_sign.py` | 只保留对 `xhshow` 的封装（`core/sign.py`） |
| 反指纹 / 登录 | MediaCrawler 的 `ENABLE_CDP_MODE` + `libs/stealth.min.js` + `login.py` | 精简为持久化上下文 + stealth 注入 + 扫码登录（`core/browser.py`） |
| 主页抓取 | MediaCrawler 的 `client.py` / `extractor.py` | 只保留 `GET /user/profile/{uid}` + `__INITIAL_STATE__` 解析（`core/xhs_client.py`） |
| 职业预测 | [twitter_profile_predictor](https://github.com/TimFaverjon/twitter_profile_predictor) | 原项目面向法语 Twitter 简介；这里换成中文词典并对「昵称+简介」打分（`predictor/`） |

## 风控要点（为什么这样设计）

1. **接口签名**：所有对 `edith.xiaohongshu.com` 的请求都由 `xhshow` 生成 `x-s / x-t / x-s-common / x-b3-traceid`，绕过签名校验。
2. **浏览器指纹**：Playwright 持久化上下文 `user_data_dir` 复用登录态；注入 `stealth.min.js`；启动参数带 `--disable-blink-features=AutomationControlled`，规避 `navigator.webdriver` 等检测。
3. **行为风控**：请求间隔在 MediaCrawler 原有基准（2s）上**慢一倍**（4~8s 随机），每 5 个博主长休息 20s。
4. **无 IP 池**：全程本机单 IP，靠「慢 + 复用登录态」降低风险。**默认抓 10 人**，页面输入框可调。

## 目录结构

```
xhs_job_crawler/
├── app_config.py          # 全局配置（速率×2、抓取上限、浏览器、Web 端口）
├── run.py                 # 一键启动：起 Web 服务并自动打开页面
├── core/
│   ├── sign.py            # xhshow 签名封装
│   ├── xhs_client.py      # 签名请求 + 主页解析（昵称/小红书号/简介）
│   ├── browser.py         # 反检测浏览器 + 扫码登录 + 推荐流作者采集
│   ├── crawler.py         # 抓取编排（登录→采集→逐个抓主页→预测→限流）
│   └── stealth.min.js     # 反指纹脚本
├── predictor/
│   ├── occupation.py      # 中文职业预测引擎
│   └── professions_zh.json# 中文职业词典（职业/类别/关键词，124 个职业）
├── tools/
│   ├── predict_cli.py     # 离线测试入口（不联网、不用浏览器）
│   ├── test_user_cases.py # 真实样例回归（无需登录）
│   └── web_selftest.sh    # Web 接口自测（起服务→打四个接口→关服务）
├── data/
│   ├── sample_creators.tsv# 样例数据
│   ├── edge_cases.tsv     # 边界/易错样例（回归用）
│   └── user_cases.tsv     # 用户真实样例（回归用）
└── web/
    ├── server.py          # FastAPI：/api/start /api/stop /api/status /api/demo /api/export
    └── index.html         # 极简页面
```

## 先离线验证职业预测（无需登录 / 无需浏览器）

只想先验证「职业推断」效果时，直接用命令行测试，**不需要网络、也不需要 Playwright**：

```bash
# 1) 内置样例演示
python tools/predict_cli.py

# 2) 用你自己的数据：每行「昵称|简介」或「昵称<TAB>简介」
python tools/predict_cli.py "咖啡师小鹿|手冲咖啡 拉花" "老周说法|执业12年律师"

# 3) 从文件读取
python tools/predict_cli.py -f data/sample_creators.tsv

# 4) 从剪贴板/标准输入逐行粘贴（Ctrl-D 结束）
python tools/predict_cli.py -
```

输出示例：

```
昵称             推测职业         类别           置信度  命中依据
阿沁的日常          程序员          IT/互联网       高      开发工程师、前端开发、程序员  [score=12.0]
Amy在湾区         全职妈妈         家庭/生活        高      全职妈妈、亲子、妈妈  [score=8.0]
小甜乖乖          未识别           未知           无      -  [score=0]
```

> 命中依据 = 触发的关键词，score = 加权得分（越长/越具体的词权重越高）。
> 若某条判错，直接往 `predictor/professions_zh.json` 的对应职业 `keywords` 里增删词即可，无需改代码。

## 无简介 / 无意义内容怎么处理（重要）

引擎**只依据「昵称 + 简介」里出现的证据词**判断，**没有证据就不猜**，并给出置信度：

| 场景 | 结果 | 置信度 |
| --- | --- | --- |
| 简介为空，昵称也无关键词（如「小甜乖乖」） | 未识别 | 无 |
| 简介全是套话（"感谢关注 每天更新"）且昵称无信息 | 未识别 | 无 |
| 纯乱码 / 无意义文本（如「了改_sleep baccano」） | 未识别 | 无 |
| 简介为空，但昵称含职业词（如「小琪影视」） | 按昵称给出（如 摄像/剪辑） | **低**（仅昵称弱信号） |
| 简介含明确职业词（如「分享母婴好物｜育儿知识」） | 母婴/育儿博主 | 高/中 |

判定规则：仅昵称命中 → 一律「低」；有简介命中时按 score 分档（<2 低、<5 中、≥5 高）。
导出结果里「置信度」+「命中依据」两列，可让你快速筛掉低可信项、并复核是否误判。

## 免登录（游客）模式实测结论（2024 版 Web）

结论：**不登录也能拿到和登录基本一样的资料**，字段并不少。

实测链路与证据：

1. 用真实浏览器（Playwright 持久化上下文）打开推荐页并**滚动几下**，让服务端下发
   `acw_tc` / `websectiga` / `sec_poison_id` / `a1` / `web_session` 等匿名 Cookie；
2. 把这套 Cookie 交给 `requests`，GET `https://www.xiaohongshu.com/user/profile/<uid>`；
3. 返回 **174 KB 的完整 SSR HTML**（不是登录墙），里面直接有：
   - `<div class="user-name">昵称</div>`
   - `<span class="user-redId">小红书号：123456789</span>`
   - `<span class="user-IP"> IP属地：示例省</span>`
   - `<div class="user-desc">简介</div>`
   - 以及 `window.__INITIAL_STATE__ → userPageData.basicInfo{nickname,redId,desc,ipLocation}`

   实测输出（游客、未登录）：`nickname=示例博主, red_id=123456789, desc=还没有简介, ip_location=示例省`。

⚠️ **关键前提**：必须先用真实浏览器逛一遍页面再取数。
只用 `requests` 裸请求（或浏览器只开 4 秒不滚动）时，同一 URL 只返回 **36 KB 的剥离页**，
里面**没有**「小红书号」——这正是「免登录拿不到小红书号」这种错觉的来源。

⚠️ **风险从「账号」转移到「IP」**：匿名流量更容易被拦。
实测出现过推荐流采集到昵称 `安全限制` 的拦截页。脚本已内置：
- 若 HTTP 200 但页面里没有「小红书号」→ 判定疑似风控 → **退避 8~15 秒自动重试一次**；
- 导出的「备注」列会写「疑似被 IP 级风控拦成精简页…」，便于识别。

因此免登录模式的使用建议：**单次 ≤ 20（界面默认 10），跑完隔几分钟再跑；不要并发**。
若连续多次都是风控页，说明当前 IP 已被临时限制，**停手等半小时**，或改用登录模式。

## 登录模式（扫码）排查：窗口起来了却跳不过去 / 点不开

登录模式用 Playwright 的有头浏览器打开 `https://www.xiaohongshu.com/explore`，
**二维码弹窗是自动出现的**，扫码即登录（等待上限 180 秒；二维码过期会自动点「刷新」，最多 3 次）。

若遇到「浏览器窗口起来了，但停在空白页 / 无法跳转 / 点不动」，按顺序排查：

1. **不要混用浏览器渠道（最常见原因）**
   Chrome 与 chromium 的 `user_data_dir` 互不兼容。用 chromium 建好的登录态目录再交给 Chrome 打开，
   Chrome 会拒绝接管，症状正是「窗口出来但空白、地址栏不跳转」。
   本工具默认只用 Playwright 自带 chromium，并按渠道分开存登录态：
   - 默认：`data/browser_user_data`
   - 指定 Chrome：`XHS_CHANNEL=chrome` → `data/browser_user_data_chrome`（两套登录态互不影响）
2. **先关掉旧的浏览器窗口**
   若 `data/browser_user_data*/SingletonLock` 还在（上一个实例没退干净），新窗口会空白。
   程序启动时会检测，并把这条写进界面上的「启动提示」。
3. **窗口被压在后台**
   启动时已加 `--start-maximized` 且调用 `bring_to_front()`；但若被其它窗口完全遮住，
   看起来仍像「没打开」。切一下窗口即可——程序不依赖你点击，二维码弹窗自动出现。
4. **网络到不了小红书**
   程序会校验落点是否真的是 `xiaohongshu.com`，否则直接报错，并提示先用普通浏览器确认网络/代理。
5. **看失败原因，不要干等**
   失败时界面会显示一行：
   `登录失败：<原因> | 浏览器=<渠道> | 页面=<当前URL> | 二维码可见=<True/False> | 启动提示=<...>`

一次性自检（约 30 秒，不进等待循环）：

```bash
DISPLAY=:0.0 .venv/bin/python tools/diag_login3.py
```

正常应输出：渠道 `chromium(自带)`、页面 `https://www.xiaohongshu.com/explore`、
`登录弹窗可见: True`、`二维码已渲染: True`。

## 运行（本地）—— 打开可视化页面实测

### 第 1 步：装依赖（务必用虚拟环境）

```bash
cd xhs_job_crawler
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium                          # 首次需下载浏览器内核
```

> 直接 `pip install -r requirements.txt` 在 Kali/新版 Debian 上会报
> `error: externally-managed-environment`（PEP 668），这是系统保护机制，**不是缺包**。
> 建虚拟环境后再装即可；也可临时用 `pip install --break-system-packages`，但不推荐。

### 第 2 步：起服务

```bash
.venv/bin/python run.py        # 或先 source .venv/bin/activate 再 python run.py
```

> **常见报错**：`python run.py` 报 `ModuleNotFoundError: No module named 'xhshow'`，
> 原因几乎都是用了系统 Python 而不是项目的 `.venv`（依赖装在 venv 里）。
> 换成本节命令即可，无需重装依赖。

看到 `* 控制台: http://127.0.0.1:8777/` 即启动成功，浏览器会自动弹出该页面（没弹出就手动访问）。

> 无图形界面 / 服务器上可加虚拟显示：`xvfb-run -a python run.py`。

### 第 3 步：页面操作

打开 `http://127.0.0.1:8777/` 后：

1. **先点「演示数据」** —— 不需要登录、不联网，表格立刻填上 5 条示例，
   用来确认列顺序（昵称 / 小红书号 / 推测职业 / 置信度 / 备注）和导出效果是否符合预期；
2. 选采集模式（默认 **游客模式（免登录，推荐）**）并设定抓取数量
   （默认 10；游客模式单次上限 20，登录模式上限 300），点 **开始**：
   - **游客模式**：不会让你扫码，脚本自己开浏览器逛推荐流（种 Cookie）后直接采集；
   - **登录模式**：自动弹出浏览器跳转小红书，用手机 App **扫码登录**（页面会显示剩余秒数）；
3. 采集过程中表格实时刷新，列含义：

   | 列 | 含义 |
   | --- | --- |
   | 昵称 | 博主昵称 |
   | **小红书号** | 博主 ID（紧挨昵称，空值显示 `-`） |
   | IP属地 | 如「上海」，取自主页 SSR 页（未见则显示 `-`） |
   | 推测职业 | 规则引擎结论，无法判断时显示「未识别」 |
   | 置信度 | 高/中/低/无（颜色区分，仅昵称命中一律「低」） |
   | 备注 | 小红书号的来源，或为空时的原因（见下节） |

4. 点 **停止** 可随时中止；点 **一键导出 (CSV)** 或 **导出 Excel** 保存结果。
   导出文件列：昵称 / 小红书号 / 推测职业 / 职业大类 / 置信度 / 命中依据 / 简介 / **备注** / 用户ID。

### 行业筛选（可选，推荐）：先选行业，命中率更高

默认「不选行业」＝老行为（随机推荐流）。在页面上点选行业卡片（可多选：旅游 / 美食 / 摄影 / 健身 …），
或填一个自定义关键词，脚本就会**带着关键词去找人**，而不是随机撞人。

关键词分两条路走：

| 关键词类型 | 走哪条路 | 游客态可用？ | 说明 |
| --- | --- | --- | --- |
| 命中内置行业频道（旅游/美食/健身/美妆/穿搭/宠物/职场/家居/游戏/影视/情感 等） | **行业频道流** `explore?channel_id=…` | ✅ 可用 | 内容就是该行业的笔记，取作者命中率最高；实测 **4 秒取到 10 位作者** |
| 其余行业与自定义关键词（摄影/母婴/教育/数码/汽车/音乐/舞蹈/手工/读书…） | **关键词搜索** `/api/sns/web/v1/search/notes` | ❌ 需登录 | 游客态接口恒返回 `-104 您当前登录的账号没有权限访问`；此时会**直接跳过**并在「阶段」里说明，不再白等搜索页 |

兜底顺序：**行业频道 → 关键词搜索 → 随机推荐流**。每一步失败都会在页面「阶段」里写明原因，不静默失败。

内置「行业 → 频道」映射表（见 `app_config.py: INDUSTRY_CHANNELS`）：

| 行业 | 频道 ID | 行业 | 频道 ID |
| --- | --- | --- | --- |
| 旅游 / 旅行 | `homefeed.travel_v3` | 职场 | `homefeed.career_v3` |
| 美食 | `homefeed.food_v3` | 健身 | `homefeed.fitness_v3` |
| 穿搭 / 时尚 | `homefeed.fashion_v3` | 家居 / 装修 | `homefeed.household_product_v3` |
| 美妆 / 彩妆 | `homefeed.cosmetics_v3` | 游戏 | `homefeed.gaming_v3` |
| 影视 | `homefeed.movie_and_tv_v3` | 宠物 | `homefeed.pet` |
| 情感 | `homefeed.love_v3` | 推荐（随机） | `homefeed_recommend` |

> ⚠️ 这些 ID 是从小红书前端 JS 里提取后**逐个实测**确认的（**不是猜的**）。写错的 ID 不会报错，
> 而是**静默回退到推荐流**——猜 ID 会让「行业筛选」悄悄失效，所以包里内置的是实测表。
> 想加行业/换频道，只改 `INDUSTRY_CHANNELS` 即可，采集逻辑不用动。
>
> 同一个行业的多个搜索词（如 旅游 → 旅游攻略/旅行vlog/citywalk/自由行）指向同一个频道，
> 只会逛一次，不会重复采集。

结果表里「**来源行业·关键词**」列会标明每条数据来自哪个行业/关键词（频道来源标记为 `channel`），
方便你判断筛选是否真的生效。

**推荐用法**：游客模式下优先「点选行业」（走频道，当前最有效）；自定义关键词搜索建议先扫码登录再跑。

实测记录（游客态、`industries=["旅游"]`、数量=2）：

- 展开关键词 → 旅游攻略 / 旅行vlog / citywalk / 自由行（`INDUSTRY_MAX_KEYWORDS=6` 内自动展开）；
- 首词命中频道 `homefeed.travel_v3`，4 秒取到 10 位候选作者；其余同频道的词自动跳过（不再重复逛）；
- 全程 **54 秒**、正好 2 条结果，来源列 `旅游攻略(channel)`，推测职业为**摄影师 / 海钓船长 / 户外探险**等旅游强相关；
- 仅当真的没有频道可用时才走搜索，且游客态（-104）会立即跳过而不去等搜索页，避免每条关键词白等 ~22 秒。

### 小红书号为空怎么办

小红书号有**三层兜底**，且会在「备注」列说明原因，不会静默丢字段：

1. 主页接口 JSON 多路径解析（`redId` / `red_id` / `redID` …，字段被包在深层也能取到）；
2. 主页 HTML 文本正则（`小红书号：xxx`，兼容半角/全角冒号）；
3. 浏览器打开主页（真实登录态）读 `__INITIAL_STATE__` + 页面文本 / 标题。

对应「备注」含义：

| 备注 | 含义 | 处理 |
| --- | --- | --- |
| 小红书号来源：主页HTML(SSR) | 免登录 SSR 页解析得到（游客模式常态） | 正常 |
| 小红书号来源：主页接口 / 主页HTML / 页面文本 / 浏览器登录态 | 取到了 | 正常 |
| 该账号未设置小红书号 | 该博主确实没设 ID | 正常，非 bug |
| 疑似被 IP 级风控拦成精简页（页面无「小红书号」） | HTTP 200 但拿到的是 36KB 剥离/「安全限制」页 | 降低频率，稍后重试；必要时等半小时或改用登录模式 |
| 未取到主页资料（可能未登录/被风控…） | 抓取被拦 | 稍后重试或重新扫码登录；或调大 `RATE_MULTIPLIER` |

> **登录判定已改为接口判定**：以 `GET /api/sns/web/v2/user/me` 的 `data.guest` 为准。
> 实测小红书会给**未登录游客**也下发 `web_session` Cookie（长度 38），
> 所以「Cookie 里有 web_session」**不能**当登录判据——早期版本据此判断会把游客误判成
> 已登录、跳过扫码，随后主页资料抓不全，出现「昵称有、小红书号空」的现象，现已修复。
> 接口不可用（网络抖动）时降级为 Cookie 判据，并把 `login_check` 标记为 `cookie_fallback`。

### 第 4 步（可选）：自动自测

不打开浏览器也能把四个接口跑一遍：

```bash
sh tools/web_selftest.sh      # 结果写入 data/_web_test.txt
```

另外还有两组**完全离线、无需网络/浏览器**的单元自检，改完代码建议先跑：

```bash
python tools/test_industry.py   # 行业筛选 / 频道解析 / 关键词展开 共 27 项
python tools/test_parse.py      # 主页字段解析 / 小红书号多路径 共 16 项
```

## 说明与限制

- 运行环境为本地、无 IP 池；若频繁触发风控，请调大 `app_config.py` 里的 `RATE_MULTIPLIER`。
- 职业推断基于关键词规则，命中的关键词会记录在导出文件的「命中依据」列，便于人工核对。
- 小红书接口字段可能随版本变化；若推荐流接口不可用，会自动回退到**浏览器 DOM 采集**作者。
- **未装 Playwright 时**：`python run.py` 仍能正常起服务、页面可打开，但点「开始」会提示
  `未安装 playwright。请先执行：pip install playwright && playwright install chromium`。
  此时可用「演示数据」先验证界面与导出。

## 换机器独立运行（本包可整体搬走）

本项目**不依赖任何外部服务或原会话环境**，所有路径都由 `app_config.py` 的 `PROJECT_DIR`（即文件自身位置）推导，
所以整个目录复制到任意机器/任意路径都能跑。

```bash
# 1) 拷到新机器（解压后）
tar xzf xhs_job_crawler_pkg.tar.gz && cd xhs_job_crawler

# 2) 装依赖（自动建 .venv + 下 chromium 内核，只需一次）
./install.sh

# 3) 启动
./start.sh                      # → http://127.0.0.1:8777/
```

**环境要求**

| 项 | 要求 | 说明 |
|----|------|------|
| Python | 3.10+（推荐 3.11 / 3.12） | 开发环境用的是 3.14，较老的发行版请装 3.11 |
| 系统库 | Linux 需 `libnss3` 等 | 缺了就跑 `playwright install-deps chromium` |
| 图形界面 | 登录（扫码）模式需要 | 纯游客模式可 `XHS_HEADLESS=1` 无头跑 |
| 网络 | 能访问 `xiaohongshu.com` | 需要出网；有代理请在系统层面配好 |

**可调环境变量**

```bash
XHS_PORT=8899 ./start.sh                    # 换端口（默认 8777）
XHS_HOST=0.0.0.0 ./start.sh                 # 允许局域网访问（默认仅本机）
XHS_HEADLESS=1 ./start.sh                   # 强制无头（仅游客模式）
XHS_CHANNEL=chrome ./start.sh               # 用本机 Google Chrome
```

**包里没有的东西（有意排除）**

- `.venv/`：虚拟环境与具体机器绑定，**不可移植**，必须在新机器上用 `./install.sh` 重建。
- `data/browser_user_data*/`、`data/xhs_state.json`：登录态/Cookie，**属于凭据，不随包分发**；
  新机器首次运行请自行扫码登录一次（会自动生成）。
- `__pycache__/`、调试抓包与导出结果文件。

