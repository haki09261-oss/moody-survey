# tests/test_dedup.py
from app.config import settings
from app.models import Submission
from app.dedup import is_duplicate, score_submission
from app.timeutil import now_cn


def _add_submission(db, survey_id, fingerprint, ip, status="new"):
    sub = Submission(
        survey_id=survey_id, redeem_code=f"WJ-{fingerprint[:6]}", channel="sms",
        answers_json={}, fingerprint=fingerprint, ip=ip, status=status,
        created_at=now_cn(),
    )
    db.add(sub)
    db.commit()
    return sub


def test_is_duplicate_true_for_same_fingerprint(db_session):
    _add_submission(db_session, 1, "fp-A", "1.1.1.1")
    assert is_duplicate(db_session, 1, "fp-A") is True


def test_is_duplicate_ignores_rejected(db_session):
    _add_submission(db_session, 1, "fp-A", "1.1.1.1", status="rejected")
    assert is_duplicate(db_session, 1, "fp-A") is False


def test_is_duplicate_false_other_survey(db_session):
    _add_submission(db_session, 1, "fp-A", "1.1.1.1")
    assert is_duplicate(db_session, 2, "fp-A") is False


def test_score_clean_submission_is_zero(db_session):
    score, flags = score_submission(
        db_session, survey_id=1, fingerprint="fp", ip="9.9.9.9",
        elapsed_ms=20000, answers={"q1": "A"}, token_device_count=1, cfg=settings,
    )
    assert score == 0
    assert flags == []


def test_score_flags_too_fast(db_session):
    score, flags = score_submission(
        db_session, survey_id=1, fingerprint="fp", ip="9.9.9.9",
        elapsed_ms=1000, answers={"q1": "A"}, token_device_count=1, cfg=settings,
    )
    assert "too_fast" in flags
    assert score >= 40


def test_score_flags_token_multi_device(db_session):
    score, flags = score_submission(
        db_session, survey_id=1, fingerprint="fp", ip="9.9.9.9",
        elapsed_ms=20000, answers={"q1": "A"}, token_device_count=5, cfg=settings,
    )
    assert "token_multi_device" in flags


def test_score_flags_ip_flood(db_session):
    for i in range(settings.ip_max + 1):
        _add_submission(db_session, 1, f"fp-{i}", "5.5.5.5")
    score, flags = score_submission(
        db_session, survey_id=1, fingerprint="fp-new", ip="5.5.5.5",
        elapsed_ms=20000, answers={"q1": "A"}, token_device_count=1, cfg=settings,
    )
    assert "ip_flood" in flags
