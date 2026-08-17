# app/dedup.py
from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.models import Submission
from app.timeutil import now_cn


def _active_submissions(db: Session, survey_id: int, fingerprint: str):
    """该指纹在该问卷上所有未拒绝的提交查询（去重/层级/升级共用同一过滤口径）。"""
    return (
        db.query(Submission)
        .filter(Submission.survey_id == survey_id)
        .filter(Submission.fingerprint == fingerprint)
        .filter(Submission.status != "rejected")
    )


def is_duplicate(db: Session, survey_id: int, fingerprint: str) -> bool:
    if not fingerprint:
        return False
    return db.query(_active_submissions(db, survey_id, fingerprint).exists()).scalar()


def score_submission(
    db: Session,
    survey_id: int,
    fingerprint: str,
    ip: str,
    elapsed_ms: int,
    answers: dict,
    token_device_count: int,
    cfg,
    schema=None,
) -> Tuple[int, List[str]]:
    score = 0
    flags: List[str] = []

    # 1) 答题过快（单独即足以触发 flagged，权重 >= flag_threshold）
    if elapsed_ms < cfg.min_elapsed_ms:
        score += 50
        flags.append("too_fast")

    # 2) 同 IP 短时间高频
    if ip:
        window_start = now_cn() - timedelta(minutes=cfg.ip_window_minutes)
        ip_count = (
            db.query(Submission)
            .filter(Submission.survey_id == survey_id)
            .filter(Submission.ip == ip)
            .filter(Submission.created_at >= window_start)
            .count()
        )
        if ip_count >= cfg.ip_max:
            score += 30
            flags.append("ip_flood")

    # 3) 同 token 多设备打开（疑似转发）
    if token_device_count > cfg.token_max_devices:
        score += 30
        flags.append("token_multi_device")

    # 4) 答案全部相同（敷衍/乱填）
    values = [v for key, v in answers.items() if key != "q_degree" and v not in (None, "", [])]
    same_literal = len(values) >= 3 and len(set(map(str, values))) == 1
    by_id = {q.get("id"): q for q in (schema or [])}
    position_signatures = []
    for qid, raw in answers.items():
        question = by_id.get(qid)
        if not question or question.get("degree") or question.get("type") not in ("single", "multi"):
            continue
        selected = raw if isinstance(raw, list) else [raw]
        indices = []
        for value in selected:
            for index, option in enumerate(question.get("options") or []):
                if value == option or (option.startswith("其他") and str(value).startswith(option + "：")):
                    indices.append(index)
                    break
        if indices:
            position_signatures.append(tuple(sorted(indices)))
    same_positions = len(position_signatures) >= 5 and len(set(position_signatures)) == 1
    if same_literal or same_positions:
        score += 50
        flags.append("uniform_answers")

    return min(score, 100), flags


def submitted_tier(db: Session, survey_id: int, fingerprint: str) -> int:
    """返回该指纹在该问卷上已达到的最高层级：未提交=0，否则取 tier_reached。"""
    if not fingerprint:
        return 0
    sub = (
        _active_submissions(db, survey_id, fingerprint)
        .order_by(Submission.tier_reached.desc())
        .first()
    )
    return sub.tier_reached if sub else 0


def latest_submission(db: Session, survey_id: int, fingerprint: str):
    """该指纹在该问卷上最近一条未拒绝的提交（用于升级合并），无则 None。"""
    if not fingerprint:
        return None
    return (
        _active_submissions(db, survey_id, fingerprint)
        .order_by(Submission.id.desc())
        .first()
    )
