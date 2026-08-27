# app/timeutil.py
"""全站统一时间口径:北京时间(UTC+8)。

历史上存的是 UTC,现改为直接存北京时间——库里 created_at/expires_at/starts_at/ends_at
均为北京时间的 naive datetime。所有"当前时间"一律用 now_cn(),不再用 datetime.utcnow()。
存量 UTC 数据由 migrations.ensure_cn_time_shift 一次性 +8 小时校正。
"""
from datetime import datetime, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))


def now_cn() -> datetime:
    """当前北京时间(naive,UTC+8)。"""
    return datetime.now(CN_TZ).replace(tzinfo=None)
