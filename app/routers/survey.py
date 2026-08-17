# app/routers/survey.py
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.codes import build_display_code, generate_redeem_code, parse_degree
from app.config import settings
from app.database import get_db
from app.dedup import is_duplicate, latest_submission, score_submission
from app.distribution import claim_for_device, claim_or_check
from app.event_types import PAGE_LEAVE, PAGE_VIEW, to_cn
from app.models import Distribution, Event, Submission, Survey
from app.schemas import (
    SubmitRequest,
    SubmitResponse,
    TrackRequest,
    UpgradeRequest,
    UpgradeResponse,
)
from app.timeutil import now_cn
from app.validation import validate_degree, validate_tier_answers

MAX_EVENTS_PER_REQUEST = 100

router = APIRouter()


def _uses_moody_reward_route(schema) -> bool:
    q3 = next((q for q in (schema or []) if q.get("id") == "q3"), None)
    options = set((q3 or {}).get("options") or [])
    return {
        "只戴美瞳", "两种都戴，戴美瞳更多", "两种都戴，戴透明片更多",
    }.issubset(options)


def _client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/api/s/{slug}")
def get_survey(
    slug: str,
    request: Request,
    t: Optional[str] = None,
    c: str = "unknown",
    fp: Optional[str] = None,
    aid: Optional[str] = None,
    db: Session = Depends(get_db),
):
    survey = db.query(Survey).filter_by(slug=slug, status="active").one_or_none()
    if survey is None:
        raise HTTPException(status_code=404, detail="survey not found")

    now = now_cn()
    # 兑奖链接按渠道取:命中 channel_product_urls[c] 则用之,否则回退默认 new_product_url
    product_url = (survey.channel_product_urls or {}).get(c) or survey.new_product_url
    base = {
        "slug": survey.slug,
        "title": survey.title,
        "schema": survey.schema_json,
        "reward_type": survey.reward_type,
        "new_product_url": product_url,
        "channel": c,
        "token_status": "none",
        "already_submitted": False,
        "submitted_tier": 0,
        "can_resume_tier2": False,
        "token": None,
        "user_code": None,
        "display_code": None,
    }

    ended = bool(survey.ends_at and now >= survey.ends_at)

    if t:
        dist = db.query(Distribution).filter_by(token=t).one_or_none()
        if dist is None:
            base["token_status"] = "ended" if ended else "not_found"
            base["schema"] = []
            return base
        # 先查提交：已提交者活动关闭或 72h 过期后仍能找回自己的兑换码。
        # 按 token 或指纹任一匹配——提交与 token 不挂钩的设备（历史无 token 口径）
        # 也必须直达兑奖码页，与 submit 端 is_duplicate 的指纹口径对称
        submitted_match = [Submission.token == t]
        if fp:
            submitted_match.append(Submission.fingerprint == fp)
        sub = (
            db.query(Submission)
            .filter(
                Submission.survey_id == survey.id,
                Submission.status != "rejected",
                or_(*submitted_match),
            )
            .order_by(Submission.id.desc())
            .first()
        )
        if sub is not None:
            if sub.status in ("flagged", "rejected"):
                base["token_status"] = "invalid_submission"
                base["already_submitted"] = True
                base["schema"] = []
                return base
            base["token_status"] = "submitted_self"
            base["already_submitted"] = True
            base["submitted_tier"] = sub.tier_reached
            base["can_resume_tier2"] = sub.tier_reached == 1 and (
                (sub.answers_json or {}).get("q3") in (
                    "两种都戴，戴美瞳更多", "两种都戴，戴透明片更多",
                )
            )
            base["display_code"] = build_display_code(sub.redeem_code, sub.tier_reached, sub.degree)
            return base
        if ended:
            base["token_status"] = "ended"
            base["schema"] = []
            return base
        # 未提交且超 72h → 问卷已关闭
        if now >= dist.expires_at:
            base["token_status"] = "expired"
            base["schema"] = []
            return base
        eligibility, user_code = claim_or_check(db, dist, fp or "")
        if eligibility == "ineligible":
            base["token_status"] = "ineligible"
            base["schema"] = []
            return base
        base["user_code"] = user_code
        base["token_status"] = "eligible"
        return base

    # 活动结束（ends_at 到点）→ 未提交用户不再领取或作答
    if ended:
        base["token_status"] = "ended"
        base["schema"] = []
        return base

    # 通用链接（无 token）：按设备指纹自动领取/找回 token，前端拿到后跳转
    if not fp:
        base["schema"] = []
        return base
    dist = claim_for_device(db, survey.id, c, fp, _client_ip(request), settings.token_ttl_hours, aid=aid)
    if dist is None:
        base["token_status"] = "ineligible"
        base["schema"] = []
        return base
    base["token_status"] = "claim"
    base["token"] = dist.token
    base["user_code"] = dist.user_code
    return base


def _unique_redeem_code(db: Session) -> str:
    for _ in range(10):
        code = generate_redeem_code()
        exists = db.query(Submission).filter_by(redeem_code=code).first()
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="failed to allocate redeem code")


@router.post("/s/{slug}/submit", response_model=SubmitResponse)
def submit(
    slug: str,
    payload: SubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    survey = db.query(Survey).filter_by(slug=slug, status="active").one_or_none()
    if survey is None:
        raise HTTPException(status_code=404, detail="survey not found")

    now = now_cn()
    ended = bool(survey.ends_at and now >= survey.ends_at)

    if not payload.token:
        if ended:
            raise HTTPException(status_code=409, detail="ended")
        raise HTTPException(status_code=409, detail="token_required")
    dist = db.query(Distribution).filter_by(token=payload.token).one_or_none()
    if dist is None:
        if ended:
            raise HTTPException(status_code=409, detail="ended")
        raise HTTPException(status_code=409, detail="token_not_found")
    # 先查提交：已提交者幂等返回原码（token 过期不影响）
    existing = (
        db.query(Submission)
        .filter(
            Submission.survey_id == survey.id,
            Submission.token == payload.token,
            Submission.status != "rejected",
        )
        .order_by(Submission.id.desc())
        .first()
    )
    if existing is not None:
        # 幂等只对绑定设备本人生效：他人持同一 token 不应拿走原码
        eligibility, _user_code = claim_or_check(db, dist, payload.fingerprint)
        if eligibility == "ineligible":
            raise HTTPException(status_code=409, detail="ineligible")
        if existing.status in ("flagged", "rejected"):
            raise HTTPException(status_code=422, detail="invalid_submission")
        return SubmitResponse(
            redeem_code=existing.redeem_code,
            status=existing.status,
            tier=existing.tier_reached,
            display_code=build_display_code(existing.redeem_code, existing.tier_reached, existing.degree),
        )
    if ended:
        raise HTTPException(status_code=409, detail="ended")
    if now >= dist.expires_at:
        raise HTTPException(status_code=409, detail="token_expired")
    eligibility, _user_code = claim_or_check(db, dist, payload.fingerprint)
    if eligibility == "ineligible":
        raise HTTPException(status_code=409, detail="ineligible")
    # 同 token 多设备打开数：从埋点(页面浏览)统计，distributions 不再冗余存打开轨迹
    token_device_count = (
        db.query(func.count(func.distinct(Event.fingerprint)))
        .filter(Event.token == payload.token, Event.event_type == PAGE_VIEW)
        .scalar()
    ) or 0

    if is_duplicate(db, survey.id, payload.fingerprint):
        raise HTTPException(status_code=409, detail="already_submitted")

    answers = payload.answers or {}
    validate_tier_answers(survey.schema_json or [], answers, tier=1)
    uses_reward_route = _uses_moody_reward_route(survey.schema_json)
    continues_to_full_survey = uses_reward_route and answers.get("q3") in (
        "两种都戴，戴美瞳更多", "两种都戴，戴透明片更多",
    )
    if not continues_to_full_survey:
        validate_degree(survey.schema_json or [], answers)

    score, flags = score_submission(
        db,
        survey_id=survey.id,
        fingerprint=payload.fingerprint,
        ip=_client_ip(request),
        elapsed_ms=payload.elapsed_ms,
        answers=payload.answers,
        token_device_count=token_device_count,
        cfg=settings,
        schema=survey.schema_json,
    )
    status_value = "in_progress" if continues_to_full_survey else (
        "flagged" if score >= settings.flag_threshold else "new"
    )

    device_snapshot = dict(payload.device or {}) or None
    if device_snapshot:
        device_snapshot.pop("ua", None)  # 与 ua 列重复，不双存

    sub = Submission(
        survey_id=survey.id,
        redeem_code=_unique_redeem_code(db),
        channel=payload.channel,
        token=payload.token,
        answers_json=payload.answers,
        ip=_client_ip(request),
        fingerprint=payload.fingerprint,
        session_id=payload.session_id,
        ua=request.headers.get("user-agent", ""),
        device_json=device_snapshot,
        elapsed_ms=payload.elapsed_ms,
        risk_score=score,
        risk_flags=flags,
        status=status_value,
        tier_reached=1,
        degree=parse_degree((payload.answers or {}).get("q_degree")),
        created_at=now_cn(),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    if sub.status == "flagged":
        raise HTTPException(status_code=422, detail="invalid_submission")
    return SubmitResponse(
        redeem_code=sub.redeem_code, status=sub.status, tier=sub.tier_reached,
        display_code=build_display_code(sub.redeem_code, sub.tier_reached, sub.degree),
    )


@router.post("/s/{slug}/upgrade", response_model=UpgradeResponse)
def upgrade(
    slug: str,
    payload: UpgradeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    survey = db.query(Survey).filter_by(slug=slug, status="active").one_or_none()
    if survey is None:
        raise HTTPException(status_code=404, detail="survey not found")

    now = now_cn()
    if survey.ends_at and now >= survey.ends_at:
        raise HTTPException(status_code=409, detail="ended")

    sub = latest_submission(db, survey.id, payload.fingerprint)
    if sub is None:
        raise HTTPException(status_code=404, detail="no_submission")
    if sub.status in ("flagged", "rejected"):
        raise HTTPException(status_code=422, detail="invalid_submission")

    if sub.tier_reached < 2:
        merged = dict(sub.answers_json or {})
        merged.update(payload.answers or {})
        if _uses_moody_reward_route(survey.schema_json) and merged.get("q3") not in (
            "两种都戴，戴美瞳更多", "两种都戴，戴透明片更多",
        ):
            raise HTTPException(status_code=409, detail="invalid_route")
        validate_tier_answers(survey.schema_json or [], merged, tier=2)
        validate_degree(survey.schema_json or [], merged)
        should_rescore = _uses_moody_reward_route(survey.schema_json) or payload.elapsed_ms > 0
        score, flags = sub.risk_score or 0, sub.risk_flags or []
        if should_rescore:
            token_device_count = (
                db.query(func.count(func.distinct(Event.fingerprint)))
                .filter(Event.token == sub.token, Event.event_type == PAGE_VIEW)
                .scalar()
            ) or 0
            score, flags = score_submission(
                db,
                survey_id=survey.id,
                fingerprint=payload.fingerprint,
                ip=_client_ip(request),
                elapsed_ms=payload.elapsed_ms,
                answers=merged,
                token_device_count=token_device_count,
                cfg=settings,
                schema=survey.schema_json,
            )
        sub.answers_json = merged
        sub.tier_reached = 2
        sub.elapsed_ms = payload.elapsed_ms
        sub.ip = _client_ip(request)
        sub.risk_score = score
        sub.risk_flags = flags
        sub.status = "flagged" if score >= settings.flag_threshold else "new"
        # 度数弹窗在「继续作答」路径里于 tier2 提交时才填，这里据 q_degree 更新 degree
        if "q_degree" in (payload.answers or {}):
            sub.degree = parse_degree(merged.get("q_degree"))
        if payload.session_id:
            sub.session_id = payload.session_id
        db.commit()
        db.refresh(sub)
        if sub.status == "flagged":
            raise HTTPException(status_code=422, detail="invalid_submission")

    return UpgradeResponse(
        redeem_code=sub.redeem_code, tier=sub.tier_reached,
        display_code=build_display_code(sub.redeem_code, sub.tier_reached, sub.degree),
    )


@router.post("/s/{slug}/track")
def track(
    slug: str,
    payload: TrackRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """通用行为埋点上报（批量）。埋点不应因问卷不存在而失败。"""
    survey = db.query(Survey).filter_by(slug=slug).one_or_none()
    survey_id = survey.id if survey else None
    # 题目内容快照：直接查表即可读，不必回查问卷结构
    title_by_qid = {q.get("id"): q.get("title") for q in ((survey.schema_json if survey else []) or [])}
    ip = _client_ip(request)
    now = now_cn()
    for e in payload.events[:MAX_EVENTS_PER_REQUEST]:
        props = e.props or {}
        raw_dwell = props.get("dwell_ms")
        dwell_seconds = round(raw_dwell / 1000, 1) if isinstance(raw_dwell, (int, float)) else None
        # 页面离开：一个会话只留一条，切走又回来再离开时就地刷新（停留=最终累计，题=最后停留）
        if to_cn(e.name) == PAGE_LEAVE and payload.session_id:
            existing_leave = (
                db.query(Event)
                .filter_by(session_id=payload.session_id, event_type=PAGE_LEAVE)
                .first()
            )
            if existing_leave is not None:
                existing_leave.dwell_seconds = dwell_seconds or existing_leave.dwell_seconds
                if props.get("question_id"):
                    existing_leave.question_id = props.get("question_id")
                    existing_leave.question_title = title_by_qid.get(props.get("question_id"))
                existing_leave.created_at = now
                continue
        value = props.get("value")
        # 多选答案拆成每选项一行；单选/填空一行；非答题事件 option 为空
        options = value if isinstance(value, list) else ([value] if value not in (None, "") else [None])
        for opt in options:
            db.add(Event(
                survey_id=survey_id,
                session_id=payload.session_id,
                fingerprint=payload.fingerprint,
                event_type=to_cn(e.name),  # 前端上报英文代码，落库统一中文
                question_id=props.get("question_id"),
                question_title=title_by_qid.get(props.get("question_id")),
                option_value=None if opt is None else str(opt),
                dwell_seconds=dwell_seconds,
                channel=payload.channel,
                token=payload.token,
                ip=ip,
                created_at=now,
            ))
    db.commit()
    return {"recorded": min(len(payload.events), MAX_EVENTS_PER_REQUEST)}


WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web")


@router.get("/s/{slug}")
def survey_page(slug: str):
    # no-cache：强制 WebView 每次回源校验，避免手机端拿到引用旧 v= 脚本的缓存 HTML
    return FileResponse(
        os.path.join(WEB_DIR, "survey.html"),
        headers={"Cache-Control": "no-cache"},
    )
