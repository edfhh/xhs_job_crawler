# -*- coding: utf-8 -*-
"""
全局配置：路径 / 速率 / 抓取数量 / 浏览器。

风控相关说明：
  - MediaCrawler 默认的请求/翻页间隔基准约 2s（config.base_config.CRAWLER_MAX_SLEEP_SEC = 2）。
  - 按需求「在原有基础上慢一倍」，这里 RATE_MULTIPLIER = 2.0，即实际间隔 4~8s（带随机抖动）。
  - 全部为本地运行、无 IP 池，默认走「持久化上下文 + 反指纹」以降低封号概率。
"""
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")

# 登录态 & 浏览器持久化目录（复用它可避免每次重复扫码/重复登录触发风控）
USER_DATA_DIR = os.path.join(DATA_DIR, "browser_user_data")
STORAGE_STATE = os.path.join(DATA_DIR, "xhs_state.json")
RESULT_JSON = os.path.join(DATA_DIR, "creators.json")

os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 抓取量 ====================
DEFAULT_MAX_CREATORS = 10          # 默认抓 10 个博主，网页输入框可调
MAX_CREATORS_HARD_LIMIT = 300      # 保险上限，防止误填过大的值

# ==================== 采集模式 ====================
# guest=游客免登录（默认）：实测免登录也能从博主主页 SSR HTML 里拿到
#   昵称/小红书号/简介/IP属地，字段并不比登录少；风险集中在「IP」而非「账号」，
#   匿名流量更易触发「安全限制」拦截页，故单次上限更小、节奏更慢。
# login=扫码登录：资料更稳（走接口），但风险落在账号本身（限流/封号）。
DEFAULT_MODE = "guest"             # 可用环境变量 XHS_MODE=login/guest 覆盖
DEFAULT_MODE = os.environ.get("XHS_MODE", DEFAULT_MODE).strip() or "guest"

# ==================== 速率（防封：慢一倍）====================
RATE_MULTIPLIER = 2.0              # 「慢一倍」= ×2
BASE_SLEEP_SEC = 2.0               # MediaCrawler 原有基准
MIN_SLEEP_SEC = BASE_SLEEP_SEC * RATE_MULTIPLIER        # 4.0s
MAX_SLEEP_SEC = MIN_SLEEP_SEC * 2.0                     # 8.0s（随机抖动上限）

# 命中风控（页面无「小红书号」）后的退避区间，退避后重试一次
RETRY_BACKOFF_SEC = (8.0, 15.0)

LONG_PAUSE_EVERY = 5               # 每抓 N 个博主后长休息一次
LONG_PAUSE_SEC = 20.0              # 长休息时长

# 打开推荐流后，滚动加载时可选的“翻页”等待（同样 ×2）
FEED_SCROLL_WAIT_SEC = 3.0

# ==================== 浏览器 ====================
# 需要人工扫码登录，必须有头；无图形界面的服务器可用 XHS_HEADLESS=1 强制无头
HEADLESS = os.environ.get("XHS_HEADLESS", "").lower() in ("1", "true", "yes")
ENABLE_CDP_MODE = False            # True=尝试接管本地 Chrome(CDP)；默认用 Playwright 持久化上下文
CDP_DEBUG_PORT = 9222

# 浏览器渠道：
#   ""        = Playwright 自带 chromium（默认。省事、与登录态目录同源、行为可预期）
#   "chrome"  = 本机安装的 Google Chrome（用环境变量开启：XHS_CHANNEL=chrome）
#
# ⚠️ 为什么要默认用自带 chromium：
#   Chrome 和 chromium 的 user_data_dir 互不兼容。若先用 chromium 建了 profile，
#   再用 channel="chrome" 去开同一个目录，Chrome 会拒绝接管该 profile，
#   表现就是「窗口起来了，但停在空白页、无法跳转、点不动」。
#   因此这里默认不自带渠道；选 chrome 时会自动改用独立的 profile 目录（见 profile_dir()）。
BROWSER_CHANNEL = os.environ.get("XHS_CHANNEL", "").strip()

LOGIN_URL = "https://www.xiaohongshu.com/explore"
LOGIN_TIMEOUT_SEC = 180            # 等待扫码登录的最长秒数
LOGIN_NAV_TIMEOUT_MS = 45000       # 单次页面跳转超时（网络慢时可调大）
LOGIN_QR_WAIT_SEC = 20             # 等待二维码渲染出来的上限
PROFILE_WAIT_SEC = 2.5             # 浏览器兜底打开博主主页后的等待秒数
GUEST_MAX_CREATORS = 20            # 游客(免登录)模式单次上限：压小以免匿名流量触发 IP 级风控

# 有头窗口启动参数：--start-maximized 让窗口一出来就是最大化，
# 避免被压在其它窗口下面（看起来像「没打开 / 点不开」）。
LAUNCH_ARGS = [
    "--start-maximized",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=Translate,BackForwardCache",
]


def profile_dir():
    """当前渠道对应的登录态目录。

    chrome 与 chromium 必须分开存，否则会开出一个空白、无法跳转的窗口。
    """
    if BROWSER_CHANNEL:
        return "%s_%s" % (USER_DATA_DIR, BROWSER_CHANNEL)
    return USER_DATA_DIR

# ==================== 主页推荐流 ====================
# homefeed_recommend = 主页「推荐」；也可换 homefeed.career_v3（职场频道）
FEED_CHANNEL = "homefeed_recommend"
FEED_PREFETCH_NOTES = 80           # 从推荐流预取笔记条数上限（用于提取作者）

# ==================== Web 服务 ====================
WEB_HOST = os.environ.get("XHS_HOST", "127.0.0.1")   # 需要局域网访问时设 XHS_HOST=0.0.0.0
WEB_PORT = int(os.environ.get("XHS_PORT", "8777"))   # 端口被占用时设 XHS_PORT=xxxx


# ==================== 行业关键词（「先筛选行业」模式） ====================
# 思路：先在小红书按行业关键词「搜笔记」→ 从笔记里拿作者 → 再进作者主页抓资料。
# 相比随机刷推荐流，命中「目标从业者」的概率高得多（推荐流是泛娱乐内容）。
# 每个行业配多个搜索词，爬虫逐个搜、结果按 user_id 去重。
INDUSTRY_PRESETS = {
    "旅游": ["旅游攻略", "旅行vlog", "citywalk", "自由行"],
    "摄影": ["摄影", "人像摄影", "约拍", "摄影师日常"],
    "美食": ["美食探店", "美食博主", "家常菜", "烘焙"],
    "健身": ["健身", "撸铁", "健身教练", "减脂餐"],
    "美妆": ["美妆", "化妆教程", "护肤分享", "彩妆"],
    "穿搭": ["穿搭", "每日穿搭", "穿搭博主", "ootd"],
    "母婴": ["母婴", "育儿经验", "宝妈日常", "辅食"],
    "宠物": ["宠物", "养猫日常", "铲屎官", "狗狗"],
    "职场": ["职场干货", "职场", "打工人", "面试技巧"],
    "教育": ["考研", "学习方法", "教师资格", "考公"],
    "数码": ["数码测评", "手机测评", "电脑装机", "数码好物"],
    "家居": ["家居好物", "装修", "家居收纳", "出租屋改造"],
    "汽车": ["汽车测评", "开车日常", "二手车", "新能源车"],
    "游戏": ["游戏解说", "手游", "主机游戏", "游戏日常"],
    "音乐": ["翻唱", "音乐人", "吉他弹唱", "钢琴"],
    "舞蹈": ["舞蹈教学", "街舞", "爵士舞", "舞蹈日常"],
    "手工": ["手工diy", "手作", "钩针", "手账"],
    "读书": ["读书笔记", "书单推荐", "阅读", "文学"],
}
INDUSTRY_MAX_KEYWORDS = 6         # 单次任务最多用几个搜索词（预设展开 + 自定义，防止关键词过多导致跑太久）

# 行业 → 小红书「行业频道」ID（来源：网页端官方 JS 配置，已逐个实测可访问）。
# 频道流是按行业组织的推荐流：游客态就能采集，且内容贴合行业，
# 相比随机推荐流，「目标从业者」的命中率高得多。
# 未配频道的行业 / 自定义关键词 → 回退到关键词搜索（搜索需要登录态）。
INDUSTRY_CHANNELS = {
    "旅游": "homefeed.travel_v3",
    "旅行": "homefeed.travel_v3",
    "美食": "homefeed.food_v3",
    "穿搭": "homefeed.fashion_v3",
    "时尚": "homefeed.fashion_v3",
    "美妆": "homefeed.cosmetics_v3",
    "彩妆": "homefeed.cosmetics_v3",
    "影视": "homefeed.movie_and_tv_v3",
    "职场": "homefeed.career_v3",
    "情感": "homefeed.love_v3",
    "家居": "homefeed.household_product_v3",
    "游戏": "homefeed.gaming_v3",
    "宠物": "homefeed.pet",
    "健身": "homefeed.fitness_v3",
}
CHANNEL_URL = "https://www.xiaohongshu.com/explore?channel_id=%s"
ENTRY_GOTO_TIMEOUT_MS = 20000     # 入口页导航超时；搜索页偶发长时间不返回，靠容错继续
INDUSTRY_SEARCH_PAGE_SIZE = 20    # 每个关键词请求的笔记条数
INDUSTRY_CANDIDATE_MULTIPLIER = 2 # 候选博主取「目标数量」的几倍（后面会按去重+抓取成功率损耗）
