# app/distribution.py
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.codes import token_from_times, derive_user_code
from app.config import settings
from app.models import Distribution
from app.timeutil import now_cn


def create_distribution(
    db: Session,
    survey_id: int,
    channel: str,
    ttl_hours: int = 72,
    fingerprint: str = "",
) -> Distribution:
    # 取整到秒：MySQL DATETIME 不存微秒，取整后 token 可直接用表内时间复算审计
    now = now_cn().replace(microsecond=0)
    expires = now + timedelta(hours=ttl_hours)
    # 唯一 id = md5(生成时间 + 设备信息 + 到期时间)；同刻碰撞用 salt 兜底。
    token = token_from_times(now, expires, fingerprint)
    salt = 0
    while db.query(Distribution).filter_by(token=token).first():
        salt += 1
        token = token_from_times(now, expires, fingerprint, str(salt))
    dist = Distribution(
        survey_id=survey_id,
        channel=channel,
        token=token,
        created_at=now,
        expires_at=expires,
    )
    db.add(dist)
    db.commit()
    db.refresh(dist)
    return dist


def validate_token(db: Session, token: str, now: datetime) -> Tuple[str, Optional[Distribution]]:
    # 改版：used 不再作为有效性判据；失效只看 expires_at（上游设为活动结束）。是否已提交由调用方按 token 查 submission 判断。
    dist = db.query(Distribution).filter_by(token=token).one_or_none()
    if dist is None:
        return "not_found", None
    if now >= dist.expires_at:
        return "expired", dist
    return "valid", dist


def claim_for_device(
    db: Session,
    survey_id: int,
    channel: str,
    fingerprint: str,
    ip: str,
    ttl_hours: int = 72,
    aid: Optional[str] = None,
) -> Optional[Distribution]:
    """通用链接首开领取 token。
    - 空指纹 → None（不绑定不发 token；正常前端总会带指纹）
    - tmall 渠道且带 aid：按 aid 查找/绑定，跳过同 IP 硬拦（私域批量发，NAT 同 IP 不误伤）
    - 否则走原口径：该设备已领过 → 幂等返回；该 IP 已被绑定 → None；新建并绑指纹+IP
    """
    if not fingerprint:
        return None

    # —— tmall 小程序口径：aid 为权威，不硬拦同 IP ——
    if channel == "tmall" and aid:
        existing = (
            db.query(Distribution)
            .filter_by(survey_id=survey_id, bound_aid=aid)
            .first()
        )
        if existing is not None:
            return existing
        dist = create_distribution(db, survey_id, channel, ttl_hours=ttl_hours, fingerprint=fingerprint)
        dist.bound_aid = aid
        dist.bound_fingerprint = fingerprint   # 仅留痕，不作硬校验
        dist.bound_ip = ip or None             # 仅留痕
        dist.user_code = derive_user_code(dist.token, fingerprint)
        try:
            db.commit()
            db.refresh(dist)
            return dist
        except IntegrityError:
            # 并发同 aid 撞唯一约束:回滚,返回另一个请求已建的那条(幂等,不重复发码)
            db.rollback()
            return db.query(Distribution).filter_by(survey_id=survey_id, bound_aid=aid).first()

    # —— 原口径（其余渠道 / tmall 无 aid）——
    existing = (
        db.query(Distribution)
        .filter_by(survey_id=survey_id, bound_fingerprint=fingerprint)
        .first()
    )
    if existing is not None:
        return existing
    # 同 IP 单设备硬拦（可开关）：生产经 SNI 透传层后拿不到真实客户端 IP（全员同 IP），
    # 该场景下用 SURVEY_IP_SINGLE_DEVICE=false 关闭硬拦，IP 仍照常记录留痕
    if ip and settings.ip_single_device:
        ip_taken = (
            db.query(Distribution)
            .filter(Distribution.survey_id == survey_id, Distribution.bound_ip == ip)
            .first()
        )
        if ip_taken is not None:
            return None
    dist = create_distribution(db, survey_id, channel, ttl_hours=ttl_hours, fingerprint=fingerprint)
    dist.bound_fingerprint = fingerprint
    dist.bound_ip = ip or None
    dist.user_code = derive_user_code(dist.token, fingerprint)
    db.commit()
    db.refresh(dist)
    return dist


def claim_or_check(db: Session, dist: Distribution, fingerprint: str) -> Tuple[str, Optional[str]]:
    """首开绑定 / 资格判定。返回 (eligibility, user_code)。
    - 未绑定 → 绑定本设备、生成 user_code → ("eligible", user_code)
    - 已绑定且指纹相符 → ("eligible", user_code)
    - 已绑定且指纹不符 → ("ineligible", None)
    - 无指纹 → 不绑定，放行（("eligible", 现有 user_code)）
    """
    # aid 绑定的 distribution（tmall 小程序口径）：aid 才是权威，指纹仅留痕，不硬校验
    if dist.bound_aid:
        return "eligible", dist.user_code
    if not fingerprint:
        return "eligible", dist.user_code
    if not dist.bound_fingerprint:
        dist.bound_fingerprint = fingerprint
        dist.user_code = derive_user_code(dist.token, fingerprint)
        db.commit()
        return "eligible", dist.user_code
    if dist.bound_fingerprint == fingerprint:
        return "eligible", dist.user_code
    return "ineligible", None
