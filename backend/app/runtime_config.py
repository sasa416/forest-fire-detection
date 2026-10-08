#!/usr/bin/env python3
"""运行时可调配置（DB 覆盖 .env / config.py）

背景：管理员在「系统设置」页改的值存在 `system_configs` 表里，
但过去没有任何代码读它 —— 保存成功只是写库，检测行为完全不变，
页面看起来就是"没用"。

本模块把 DB 配置接进推理与告警链路，优先级：

    system_configs(DB，管理员实时改)  >  .env  >  config.py 默认值

所有取值都有兜底：DB 不可用 / 键缺失 / 类型非法 → 退回 settings 默认值，
绝不让一张坏配置把检测打挂。
"""

import time
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

# 复用同一个 sqlite 文件；check_same_thread=False 允许在线程池里读
_engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)
_Session = sessionmaker(bind=_engine)

# 5 秒缓存：单张图检测会多次取值，避免反复查库；也保证改完几乎立刻生效
_TTL_SECONDS = 5.0
_cache: Dict[str, Any] = {}
_cache_at: float = 0.0


def _load_all() -> Dict[str, str]:
    """读取全部系统配置（带 TTL 缓存）"""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache and (now - _cache_at) < _TTL_SECONDS:
        return _cache
    try:
        db = _Session()
        try:
            rows = db.execute(text("SELECT key, value FROM system_configs")).fetchall()
            _cache = {str(k): ("" if v is None else str(v)) for k, v in rows}
            _cache_at = now
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        # 表还没建 / 库被占用：用空配置继续跑，退回 settings 默认值
        logger.debug(f"运行时配置读取失败，回退默认值: {exc}")
        _cache = {}
        _cache_at = now
    return _cache


def invalidate() -> None:
    """清空缓存。管理端保存配置后调用，让改动立即生效。"""
    global _cache_at
    _cache_at = 0.0


def raw(key: str) -> Optional[str]:
    """取原始字符串值，不存在返回 None"""
    return _load_all().get(key)


def get_float(key: str, default: float) -> float:
    try:
        v = raw(key)
        return float(v) if v not in (None, "") else float(default)
    except (TypeError, ValueError):
        logger.warning(f"配置 {key} 不是合法数值，回退 {default}")
        return float(default)


def get_int(key: str, default: int) -> int:
    try:
        v = raw(key)
        return int(float(v)) if v not in (None, "") else int(default)
    except (TypeError, ValueError):
        logger.warning(f"配置 {key} 不是合法整数，回退 {default}")
        return int(default)


def get_bool(key: str, default: bool) -> bool:
    v = raw(key)
    if v is None or v == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on", "是")


def get_list(key: str, default):
    """逗号分隔字符串 → 列表；空值回退默认"""
    v = raw(key)
    if not v:
        return list(default)
    items = [x.strip() for x in v.replace("，", ",").split(",")]
    items = [x for x in items if x]
    return items or list(default)


# ── 语义化读取器：检测链路调用这些，不要直接写 key 字符串 ──────────────

def default_confidence() -> float:
    return get_float("default_confidence", settings.DEFAULT_CONFIDENCE)


def default_iou() -> float:
    return get_float("default_iou", settings.DEFAULT_IOU_THRESHOLD)


def default_image_size() -> int:
    """单尺度推理尺寸（多尺度融合关闭时生效）"""
    return get_int("default_image_size", settings.DEFAULT_IMAGE_SIZE)


def default_model() -> str:
    return raw("default_model") or settings.DEFAULT_MODEL


def alert_enabled() -> bool:
    return get_bool("alert_enabled", settings.ALERT_ENABLED)


def alert_rules() -> Dict[str, Any]:
    """告警规则：以 settings.ALERT_RULES 为底，DB 逐项覆盖"""
    base = dict(settings.ALERT_RULES)
    base["fire_count_threshold"] = get_int(
        "alert_fire_threshold", base.get("fire_count_threshold", 1))
    base["smoke_count_threshold"] = get_int(
        "alert_smoke_threshold", base.get("smoke_count_threshold", 1))
    base["confidence_threshold"] = get_float(
        "alert_confidence_threshold", base.get("confidence_threshold", 0.75))
    base["alert_cooldown"] = get_int("alert_cooldown", base.get("alert_cooldown", 30))
    base["alert_channels"] = get_list("alert_channels", settings.ALERT_CHANNELS)
    return base
