# -*- coding: utf-8 -*-
"""AI_URLS 与 SITE_PROFILES 一致性守护测试

确保 core/constants.py 里的每个站点入口在 core/site_profiles.py
里都有对应的专用 profile（或已注释说明原因），防止再出现"入口有、
selector 没有"的静默失效问题。
"""
import pytest
from urllib.parse import urlparse
from core.constants import AI_URLS
from core.site_profiles import SITE_PROFILES


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def test_ai_urls_have_matching_profiles():
    """AI_URLS 里的每个站点都必须在 SITE_PROFILES 里有专用 profile。"""
    profile_hosts = {h.removeprefix("www.") for h in SITE_PROFILES if h != "_default"}
    missing = [
        (name, url, _host(url))
        for name, url in AI_URLS.items()
        if _host(url) not in profile_hosts
    ]
    assert not missing, (
        "以下站点在 AI_URLS 里有入口，但 SITE_PROFILES 没有对应 profile，"
        "选中后会走 _default 兜底 selector，极可能失效：\n"
        + "\n".join(f"  {name} → {url} (host={host})" for name, url, host in missing)
    )


def test_no_http_server_base():
    """授权服务器必须用 HTTPS，不能用 HTTP 明文。"""
    import license_guard
    assert license_guard.SERVER_BASE.startswith("https://"), (
        f"SERVER_BASE 仍在用 HTTP 明文: {license_guard.SERVER_BASE}"
    )


@pytest.mark.xfail(
    reason="3a6ebe1 有意临时默认 DEV_MODE=1(测试阶段跳过激活验证),"
           "上线前需改回 0 — 本守护是发布检查项:届时应转为 XPASS 并移除本标记",
    strict=False)
def test_dev_mode_default_off():
    """DEV_MODE 默认必须为 False（不设环境变量时）。发布门禁,非日常 CI 门禁。"""
    import importlib, os, sys
    # 确保没有 NOVEL_AI_DEV_MODE 环境变量时 DEV_MODE 为 False
    env_backup = os.environ.pop("NOVEL_AI_DEV_MODE", None)
    try:
        # 重新 import 一次（清缓存）
        if "license_guard" in sys.modules:
            del sys.modules["license_guard"]
        import license_guard as lg
        assert lg.DEV_MODE is False, (
            "未设置 NOVEL_AI_DEV_MODE 时 DEV_MODE 应为 False，"
            "当前为 True，会绕过所有授权验证"
        )
    finally:
        if env_backup is not None:
            os.environ["NOVEL_AI_DEV_MODE"] = env_backup
        if "license_guard" in sys.modules:
            del sys.modules["license_guard"]
