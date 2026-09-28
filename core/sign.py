# -*- coding: utf-8 -*-
"""
风控核心 #1：小红书 Web 签名（纯算法，无需浏览器）。

来源：MediaCrawler / media_platform/xhs/playwright_sign.py 与 xhs_sign.py。
这两处本质上都是调用 `xhshow` 这个算法库来生成：
  - x-s / x-t / x-s-common  (请求签名/时间戳/公共参数)
  - x-b3-traceid           (链路追踪)
  - a1 / webId             (设备标识，决定风控画像，务必与登录浏览器保持一致)

这里做的是「只保留签名」的轻量化封装。
"""
from xhshow import Xhshow

_signer = Xhshow()


def gen_a1() -> str:
    """生成设备 a1（首次用浏览器登录时也可从浏览器 cookie 里取真实值）。"""
    return _signer.generate_a1()


def gen_web_id(a1: str) -> str:
    return _signer.generate_web_id(a1)


def gen_b3_trace_id() -> str:
    return _signer.get_b3_trace_id()


def gen_search_id() -> str:
    return _signer.get_search_id()


def gen_search_request_id() -> str:
    return _signer.get_search_request_id()


def sign_get(uri: str, cookies, params=None) -> dict:
    """对 GET 请求签名，返回可直接并入 headers 的签名字段。"""
    return _signer.sign_headers_get(uri=uri, cookies=cookies, params=params)


def sign_post(uri: str, cookies, payload=None) -> dict:
    """对 POST 请求签名，返回可直接并入 headers 的签名字段。"""
    return _signer.sign_headers_post(uri=uri, cookies=cookies, payload=payload)
