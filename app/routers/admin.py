# app/routers/admin.py
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.codes import build_display_code
from app.database import get_db
from app.devices import describe_device
from app.event_types import ANSWER, CLICK_TYPES, PAGE_LEAVE, PAGE_VIEW, QUESTION_DWELL_TYPES, QUESTION_VIEW
from app.models import AdminUser, Distribution, Event, Submission, Survey
from app.schemas import BatchDeleteRequest, PurgeSubmissionRequest, RedeemRequest, SurveyCreate
from app.security import require_admin
from app.timeutil import now_cn

router = APIRouter(prefix="/admin")


@router.post("/surveys", status_code=201)
def create_survey(
    payload: SurveyCreate,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    if db.query(Survey).filter_by(slug=payload.slug).first():
        raise HTTPException(status_code=409, detail="slug exists")
    survey = Survey(
        slug=payload.slug, title=payload.title,
        schema_json=payload.schema_json, reward_type=payload.reward_type,
        new_product_url=payload.new_product_url,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )
    db.add(survey)
    db.commit()
    db.refresh(survey)
    return {"id": survey.id, "slug": survey.slug}


@router.get("/surveys")
def list_surveys(db: Session = Depends(get_db), user: AdminUser = Depends(require_admin)):
    rows = db.query(Survey).order_by(Survey.id.desc()).all()
    return {"items": [{
        "id": r.id, "slug": r.slug, "title": r.title, "status": r.status,
        "starts_at": r.starts_at, "ends_at": r.ends_at,
    } for r in rows]}


@router.get("/surveys/{survey_id}/stats")
def survey_stats(
    survey_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """问卷埋点统计：PV / UV / 平均停留 / 提交 / 转化 / 按钮点击 / 答题漏斗。"""
    base = db.query(Event).filter(Event.survey_id == survey_id)
    pv = base.filter(Event.event_type == PAGE_VIEW).count()
    uv = (db.query(func.count(func.distinct(Event.fingerprint)))
          .filter(Event.survey_id == survey_id, Event.event_type == PAGE_VIEW).scalar()) or 0

    dwells = [
        e.dwell_seconds * 1000
        for e in base.filter(Event.event_type == PAGE_LEAVE).all()
        if isinstance(e.dwell_seconds, (int, float))
    ]
    avg_dwell = round(sum(dwells) / len(dwells)) if dwells else 0

    submissions = db.query(Submission).filter_by(survey_id=survey_id).count()
    tier2 = db.query(Submission).filter(
        Submission.survey_id == survey_id, Submission.tier_reached >= 2).count()

    clicks = dict(
        db.query(Event.event_type, func.count())
        .filter(Event.survey_id == survey_id,
                Event.event_type.in_(CLICK_TYPES))
        .group_by(Event.event_type).all()
    )

    funnel = {}
    seen = {}  # (qid, kind) -> set(session)：多选拆行后按会话去重
    for e in base.filter(Event.event_type.in_([QUESTION_VIEW, ANSWER])).all():
        qid = e.question_id
        if not qid:
            continue
        kind = "views" if e.event_type == QUESTION_VIEW else "answers"
        f = funnel.setdefault(qid, {"question_id": qid, "views": 0, "answers": 0})
        bucket = seen.setdefault((qid, kind), set())
        if e.session_id not in bucket:
            bucket.add(e.session_id)
            f[kind] += 1

    return {
        "pv": pv, "uv": uv, "avg_dwell_ms": avg_dwell,
        "submissions": submissions, "tier2": tier2,
        "conversion": round(submissions / uv, 3) if uv else 0,
        "clicks": clicks,
        "funnel": list(funnel.values()),
    }


@router.get("/submissions")
def list_submissions(
    survey_id: Optional[int] = None,
    channel: Optional[str] = None,
    status: Optional[str] = None,
    code: Optional[str] = None,
    min_score: Optional[int] = None,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    q = db.query(Submission)
    if survey_id is not None:
        q = q.filter(Submission.survey_id == survey_id)
    if channel:
        q = q.filter(Submission.channel == channel)
    if status:
        q = q.filter(Submission.status == status)
    if code:
        match = re.search(r"WJ-[0-9A-Z]{6}", code.upper())
        q = q.filter(Submission.redeem_code == (match.group(0) if match else code.strip().upper()))
    if min_score is not None:
        q = q.filter(Submission.risk_score >= min_score)
    rows = q.order_by(Submission.id.desc()).limit(500).all()
    surveys = {
        survey.id: survey
        for survey in db.query(Survey).filter(
            Survey.id.in_({row.survey_id for row in rows})
        ).all()
    } if rows else {}
    audit_rows = (
        db.query(Event)
        .filter(
            Event.event_type == "后台核销",
            Event.question_id.in_([str(row.id) for row in rows]),
        )
        .order_by(Event.id.desc())
        .all()
    ) if rows else []
    redemption_audits = {}
    for audit in audit_rows:
        redemption_audits.setdefault(audit.question_id, audit)

    # 答卷本身不重复存参与标识；通过领取 token（优先）或同问卷设备指纹
    # 关联 Distribution。bound_aid 是小程序本地匿名设备码，不是淘宝账号。
    tokens = {row.token for row in rows if row.token}
    fingerprints = {
        (row.survey_id, row.fingerprint)
        for row in rows if row.fingerprint
    }
    dist_conditions = []
    if tokens:
        dist_conditions.append(Distribution.token.in_(tokens))
    if fingerprints:
        dist_conditions.extend(
            and_(
                Distribution.survey_id == survey_id_value,
                Distribution.bound_fingerprint == fingerprint,
            )
            for survey_id_value, fingerprint in fingerprints
        )
    distribution_rows = (
        db.query(Distribution)
        .filter(or_(*dist_conditions))
        .order_by(Distribution.id.desc())
        .all()
    ) if dist_conditions else []
    distributions_by_token = {
        distribution.token: distribution
        for distribution in distribution_rows if distribution.token
    }
    distributions_by_fingerprint = {}
    for distribution in distribution_rows:
        key = (distribution.survey_id, distribution.bound_fingerprint)
        if distribution.bound_fingerprint and key not in distributions_by_fingerprint:
            distributions_by_fingerprint[key] = distribution

    def participant_details(row: Submission):
        distribution = distributions_by_token.get(row.token)
        if distribution is None and row.fingerprint:
            distribution = distributions_by_fingerprint.get((row.survey_id, row.fingerprint))
        return {
            "participant_id": (
                distribution.bound_aid if distribution and distribution.bound_aid
                else row.fingerprint
            ),
            "participant_code": distribution.user_code if distribution else None,
            "identity_type": "anonymous_device",
        }

    def answer_details(row: Submission):
        survey = surveys.get(row.survey_id)
        schema = (survey.schema_json if survey else []) or []
        answers = row.answers_json or {}
        details = []
        for question in schema:
            question_id = question.get("id")
            if question_id not in answers:
                continue
            raw_value = answers.get(question_id)
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            details.append({
                "question": question.get("title") or question_id,
                "answer_labels": [str(value) for value in values if value not in (None, "")],
                "other_text": "",
            })
        return details

    return {"items": [
        {
            **participant_details(r),
            "id": r.id, "redeem_code": r.redeem_code,
            "display_code": build_display_code(r.redeem_code, r.tier_reached, r.degree),
            "degree": r.degree, "channel": r.channel,
            "risk_score": r.risk_score, "risk_flags": r.risk_flags,
            "status": r.status,
            "tier_reached": r.tier_reached,
            "ip": r.ip, "fingerprint": r.fingerprint,
            "session_id": r.session_id,
            "ua": r.ua, "device": r.device_json,
            "device_label": describe_device(r.ua, r.device_json),
            "elapsed_ms": r.elapsed_ms or 0,
            "answer_details": answer_details(r),
            "prize_name": (
                "M 系列 10 片装" if (r.tier_reached or 0) >= 2
                else "M 系列 2 片装" if r.tier_reached else ""
            ),
            "degree_label": f"{r.degree}度" if r.degree else "",
            "reward_status": (
                "redeemed" if r.status == "redeemed"
                else "issued" if r.status == "new"
                else "none"
            ),
            "redeemed_at": (
                redemption_audits[str(r.id)].created_at.isoformat()
                if str(r.id) in redemption_audits and redemption_audits[str(r.id)].created_at
                else None
            ),
            "redeemed_by": (
                redemption_audits[str(r.id)].question_title
                if str(r.id) in redemption_audits else ""
            ),
            "is_test": r.channel == "test",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]}


@router.get("/distributions")
def list_distributions(
    survey_id: Optional[int] = None,
    channel: Optional[str] = None,
    only_unsubmitted: bool = True,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """打开了链接(已领取 token)的设备记录。默认只列「打开了但没提交」的。
    判定口径与 /api/s 加载端一致:token 命中 或 指纹命中 任一即视为已提交。"""
    q = db.query(Distribution)
    if survey_id is not None:
        q = q.filter(Distribution.survey_id == survey_id)
    if channel:
        q = q.filter(Distribution.channel == channel)
    dists = q.order_by(Distribution.id.desc()).limit(1000).all()

    # 已提交集合(非 rejected):按 token 与指纹两个口径,与加载端对称
    sub_q = db.query(Submission).filter(Submission.status != "rejected")
    if survey_id is not None:
        sub_q = sub_q.filter(Submission.survey_id == survey_id)
    submitted_tokens, submitted_fps = set(), set()
    for s in sub_q.all():
        if s.token:
            submitted_tokens.add(s.token)
        if s.fingerprint:
            submitted_fps.add(s.fingerprint)

    now = now_cn()
    items = []
    for d in dists:
        submitted = d.token in submitted_tokens or (
            d.bound_fingerprint is not None and d.bound_fingerprint in submitted_fps
        )
        if only_unsubmitted and submitted:
            continue
        expired = bool(d.expires_at and now >= d.expires_at)
        items.append({
            "id": d.id,
            "survey_id": d.survey_id,
            "channel": d.channel,
            "token": d.token,
            "user_code": d.user_code,
            "fingerprint": d.bound_fingerprint,
            "aid": d.bound_aid,
            "ip": d.bound_ip,
            "submitted": submitted,
            "expired": expired,
            "opened_at": d.created_at.isoformat() if d.created_at else None,
            "expires_at": d.expires_at.isoformat() if d.expires_at else None,
        })
    return {"items": items}


@router.delete("/distributions/{dist_id}")
def delete_distribution(
    dist_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """删除一条「打开未提交」记录(distribution)。删后该设备 token/指纹/IP 绑定释放,可重新领码参与。"""
    d = db.get(Distribution, dist_id)
    if d is None:
        raise HTTPException(status_code=404, detail="distribution not found")
    db.delete(d)
    db.commit()
    return {"id": dist_id, "deleted": True}


@router.post("/distributions/batch-delete")
def batch_delete_distributions(
    payload: BatchDeleteRequest,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """批量删除「打开未提交」记录(distribution);不存在的 id 跳过,返回实际删除条数。
    删后这些设备 token/指纹/IP 绑定释放,可重新领码参与。"""
    deleted = (
        db.query(Distribution)
        .filter(Distribution.id.in_(payload.ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}


_TYPE_CN = {"single": "单选", "multi": "多选", "text": "填空"}


def _per_question_dwell(events):
    """每题停留：翻题/提交类事件携带"刚离开那道题"的停留秒数，按题累加（回看累计）。返回 {qid: ms}。"""
    per_q = {}
    for e in events:
        if e.event_type in QUESTION_DWELL_TYPES and e.question_id and isinstance(e.dwell_seconds, (int, float)):
            per_q[e.question_id] = per_q.get(e.question_id, 0) + int(e.dwell_seconds * 1000)
    return per_q


def _page_dwell(events):
    return max([int((e.dwell_seconds or 0) * 1000) for e in events if e.event_type == PAGE_LEAVE] + [0])


def _answers_from_events(events):
    """未提交会话：从回答问题事件还原每题最后一次选择。
    多选被拆成连续多行（同一次上报 id 连续）；取每题最后一段连续行作为最终选择。"""
    runs = {}  # qid -> (last_id, [options])
    for e in sorted(events, key=lambda x: x.id):
        if e.event_type != ANSWER or not e.question_id or e.option_value is None:
            continue
        last = runs.get(e.question_id)
        if last and e.id == last[0] + 1:
            last[1].append(e.option_value)
            runs[e.question_id] = (e.id, last[1])
        else:
            runs[e.question_id] = (e.id, [e.option_value])
    return {qid: (opts if len(opts) > 1 else opts[0]) for qid, (_, opts) in runs.items()}


@router.get("/submissions/{submission_id}/events")
def submission_events(
    submission_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """某份答卷的埋点详情：每题停留时长 + 所选选项 + 完整行为轨迹。"""
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    if not sub.session_id:
        return {"session_id": None, "dwell_ms": 0, "questions": [], "events": []}
    rows = (db.query(Event).filter(Event.session_id == sub.session_id)
            .order_by(Event.id).all())
    per_q = _per_question_dwell(rows)
    survey = db.get(Survey, sub.survey_id)
    schema = (survey.schema_json if survey else []) or []
    answers = sub.answers_json or {}
    questions = []
    for q in schema:
        qid = q.get("id")
        if qid in per_q or qid in answers:
            questions.append({
                "question_id": qid,
                "title": q.get("title"),
                "type": _TYPE_CN.get(q.get("type"), q.get("type")),
                "dwell_ms": per_q.get(qid, 0),
                "value": answers.get(qid),
            })
    return {
        "session_id": sub.session_id,
        "dwell_ms": _page_dwell(rows),
        "questions": questions,
        "events": [
            {"name": e.event_type, "question_id": e.question_id, "question_title": e.question_title,
             "option": e.option_value, "dwell_seconds": e.dwell_seconds,
             "created_at": e.created_at.isoformat() if e.created_at else None}
            for e in rows
        ],
    }


EVENT_ROW_COLUMNS = ["兑换码", "层级", "总停留(秒)", "问卷ID", "问卷名称", "问题类型", "问题ID",
                     "问题名称", "问题选择结果", "问题停留(秒)", "是否提交", "UV", "PV"]


def _compute_event_rows(db: Session, survey_id: int) -> dict:
    """埋点扁平表：每行 =（一份答卷 × 一道题 × 一个所选选项）；多选拆成多行。"""
    survey = db.get(Survey, survey_id)
    survey_name = survey.title if survey else ""
    schema = (survey.schema_json if survey else []) or []
    qmeta = {q.get("id"): q for q in schema}
    order = [q.get("id") for q in schema]

    pv = db.query(Event).filter(Event.survey_id == survey_id, Event.event_type == PAGE_VIEW).count()
    uv = (db.query(func.count(func.distinct(Event.fingerprint)))
          .filter(Event.survey_id == survey_id, Event.event_type == PAGE_VIEW).scalar()) or 0

    by_session = {}
    for e in (db.query(Event)
              .filter(Event.survey_id == survey_id, Event.session_id.isnot(None))
              .order_by(Event.id).all()):
        by_session.setdefault(e.session_id, []).append(e)
    submap = {s.session_id: s for s in
              db.query(Submission).filter(Submission.survey_id == survey_id,
                                          Submission.session_id.isnot(None)).all()}

    rows = []
    for session_id, evs in by_session.items():
        sub = submap.get(session_id)
        per_q = _per_question_dwell(evs)
        total_dwell = _page_dwell(evs)
        selections = (sub.answers_json or {}) if sub else _answers_from_events(evs)
        redeem = sub.redeem_code if sub else ""
        tier = sub.tier_reached if sub else ""
        submitted = "是" if sub else "否"
        for qid in order:
            if qid not in selections and qid not in per_q:
                continue
            q = qmeta.get(qid, {})
            val = selections.get(qid)
            opts = val if isinstance(val, list) else ([] if val in (None, "") else [val])
            if not opts:
                opts = [""]  # 看过但没选 → 保留一行体现停留
            for opt in opts:
                rows.append({
                    "session_id": session_id,
                    "redeem_code": redeem,
                    "tier_reached": tier,
                    "total_dwell_ms": total_dwell,
                    "survey_name": survey_name,
                    "q_type": _TYPE_CN.get(q.get("type"), q.get("type")),
                    "q_id": qid,
                    "q_title": q.get("title"),
                    "option": opt,
                    "q_dwell_ms": per_q.get(qid, 0),
                    "submitted": submitted,
                })
    return {"survey_id": survey_id, "survey_name": survey_name, "pv": pv, "uv": uv, "rows": rows}


@router.get("/surveys/{survey_id}/event-rows")
def survey_event_rows(
    survey_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    return _compute_event_rows(db, survey_id)


@router.get("/surveys/{survey_id}/question-stats")
def survey_question_stats(
    survey_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """每题聚合报表：浏览人数 / 平均停留 / 作答人数 / 选项分布（按 schema 顺序）。"""
    data = _compute_event_rows(db, survey_id)
    survey = db.get(Survey, survey_id)
    schema = (survey.schema_json if survey else []) or []
    submissions = (
        db.query(Submission)
        .filter(Submission.survey_id == survey_id, Submission.status != "rejected")
        .count()
    )

    per_q = {}
    for r in data["rows"]:
        a = per_q.setdefault(r["q_id"], {"dwell_by_session": {}})
        a["dwell_by_session"][r["session_id"]] = r["q_dwell_ms"]  # 每会话只计一次停留

    # 答案统计以正式提交表为准，埋点丢失不会造成分析结果少算；埋点仅负责浏览/停留数据。
    answer_stats = {}
    valid_submissions = (
        db.query(Submission)
        .filter(Submission.survey_id == survey_id, Submission.status != "rejected")
        .all()
    )
    for submission in valid_submissions:
        for qid, raw_value in (submission.answers_json or {}).items():
            if raw_value in (None, "", []):
                continue
            values = raw_value if isinstance(raw_value, list) else [raw_value]
            aggregate = answer_stats.setdefault(qid, {"answered": 0, "options": {}})
            aggregate["answered"] += 1
            for value in values:
                text = str(value)
                aggregate["options"][text] = aggregate["options"].get(text, 0) + 1

    questions = []
    for q in schema:
        qid = q.get("id")
        a = per_q.get(qid, {"dwell_by_session": {}})
        answers = answer_stats.get(qid, {"answered": 0, "options": {}})
        dwells = [v for v in a["dwell_by_session"].values() if v]
        answered = answers["answered"]
        questions.append({
            "q_id": qid,
            "q_title": q.get("title"),
            "q_type": _TYPE_CN.get(q.get("type"), q.get("type")),
            "viewers": len(a["dwell_by_session"]),
            "answered": answered,
            "avg_dwell_ms": round(sum(dwells) / len(dwells)) if dwells else 0,
            "options": [
                {"option": opt, "count": c, "pct": round(c * 100 / answered) if answered else 0}
                for opt, c in sorted(answers["options"].items(), key=lambda kv: -kv[1])
            ],
        })
    return {
        "survey_id": survey_id, "survey_name": data["survey_name"],
        "pv": data["pv"], "uv": data["uv"], "submissions": submissions,
        "questions": questions,
    }


@router.post("/submissions/{submission_id}/reject")
def reject_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    sub.status = "rejected"
    db.commit()
    return {"id": sub.id, "status": sub.status}


@router.post("/submissions/{submission_id}/redeem")
def redeem_submission(
    submission_id: int,
    payload: Optional[RedeemRequest] = None,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """核销兑换码。保留答卷用于分析，但状态不可再次核销。"""
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    if sub.status not in ("new", "redeemed"):
        raise HTTPException(status_code=409, detail="submission is not redeemable")
    if sub.status == "redeemed":
        return {"id": sub.id, "status": sub.status, "already_redeemed": True}
    sub.status = "redeemed"
    db.add(Event(
        survey_id=sub.survey_id,
        session_id=sub.session_id,
        fingerprint=sub.fingerprint,
        event_type="后台核销",
        question_id=str(sub.id),
        question_title=payload.staff_name if payload else user.username,
        option_value=payload.note if payload else None,
        channel=sub.channel,
        created_at=now_cn(),
    ))
    db.commit()
    return {"id": sub.id, "status": sub.status, "already_redeemed": False}


def _release_participations(db: Session, subs) -> None:
    """删除提交时级联释放分发绑定（token + 指纹双口径），设备/IP 立即可重新参与。"""
    conds = []
    for sub in subs:
        if sub.token:
            conds.append(Distribution.token == sub.token)
        if sub.fingerprint:
            conds.append(and_(Distribution.survey_id == sub.survey_id,
                              Distribution.bound_fingerprint == sub.fingerprint))
    if conds:
        db.query(Distribution).filter(or_(*conds)).delete(synchronize_session=False)


def _purge_submission_events(db: Session, sub: Submission) -> int:
    """精确清除本次答卷相关埋点，避免测试数据继续污染 PV/UV/停留统计。"""
    conds = [
        and_(Event.event_type == "后台核销", Event.question_id == str(sub.id)),
    ]
    if sub.session_id:
        conds.append(and_(
            Event.survey_id == sub.survey_id,
            Event.session_id == sub.session_id,
        ))
    if sub.token:
        conds.append(and_(
            Event.survey_id == sub.survey_id,
            Event.token == sub.token,
        ))
    return (
        db.query(Event)
        .filter(or_(*conds))
        .delete(synchronize_session=False)
    )


def _require_ops_for_delete(user: AdminUser) -> None:
    if user.role != "ops":
        raise HTTPException(status_code=403, detail="only ops can delete submissions")


@router.post("/submissions/{submission_id}/purge")
def purge_submission(
    submission_id: int,
    payload: PurgeSubmissionRequest,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    """后台受控清理单条测试答卷；保留一条不含答案/身份信息的管理员操作审计。"""
    _require_ops_for_delete(user)
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")

    accepted_codes = {
        sub.redeem_code.upper(),
        build_display_code(sub.redeem_code, sub.tier_reached, sub.degree).upper(),
    }
    if payload.confirm_code.strip().upper() not in accepted_codes:
        raise HTTPException(status_code=409, detail="confirm code does not match")
    if sub.status == "redeemed" and not payload.force_redeemed:
        raise HTTPException(status_code=409, detail="redeemed submission requires explicit confirmation")
    reason = payload.reason.strip()
    if len(reason) < 2:
        raise HTTPException(status_code=422, detail="delete reason is required")

    snapshot = {
        "submission_id": sub.id,
        "survey_id": sub.survey_id,
        "redeem_code": sub.redeem_code,
        "status": sub.status,
        "channel": sub.channel,
        "purge_events": payload.purge_events,
        "release_participation": payload.release_participation,
        "reason": reason,
    }
    deleted_events = _purge_submission_events(db, sub) if payload.purge_events else 0
    if payload.release_participation:
        _release_participations(db, [sub])
    db.delete(sub)
    db.flush()
    db.add(Event(
        survey_id=snapshot["survey_id"],
        event_type="后台删除答卷",
        question_id=str(snapshot["submission_id"]),
        question_title=user.username,
        option_value=json.dumps(snapshot, ensure_ascii=False),
        channel=snapshot["channel"],
        created_at=now_cn(),
    ))
    db.commit()
    return {
        "id": submission_id,
        "deleted": True,
        "deleted_events": deleted_events,
        "participation_released": payload.release_participation,
    }


@router.delete("/submissions/{submission_id}", deprecated=True)
def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    _require_ops_for_delete(user)
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="submission not found")
    _purge_submission_events(db, sub)
    _release_participations(db, [sub])
    db.delete(sub)
    db.commit()
    return {"id": submission_id, "deleted": True}


@router.post("/submissions/batch-delete", deprecated=True)
def batch_delete_submissions(
    payload: BatchDeleteRequest,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_admin),
):
    _require_ops_for_delete(user)
    """批量彻底删除提交记录（连带释放设备/IP 绑定）；不存在的 id 跳过，返回实际删除条数。"""
    subs = db.query(Submission).filter(Submission.id.in_(payload.ids)).all()
    for sub in subs:
        _purge_submission_events(db, sub)
    _release_participations(db, subs)
    deleted = (
        db.query(Submission)
        .filter(Submission.id.in_(payload.ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": deleted}
