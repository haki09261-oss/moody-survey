# tests/test_submit.py
import re

import pytest

from app.models import Survey, Submission
from app.distribution import create_distribution

REDEEM_RE = re.compile(r"^WJ-[0-9A-HJKMNP-TV-Z]{6}$")


@pytest.fixture
def survey(db_session):
    s = Survey(slug="spring", title="春季问卷", schema_json=[
        {"id": "q1", "type": "single", "title": "满意吗", "options": ["满意", "一般"]}
    ])
    db_session.add(s)
    db_session.commit()
    return s


def _payload(**over):
    base = {"fingerprint": "fp-1", "answers": {"q1": "满意"}, "elapsed_ms": 20000, "channel": "sms"}
    base.update(over)
    return base


def _token(db_session, survey, **over):
    return create_distribution(db_session, survey.id, "sms", ttl_hours=72, **over).token


def test_submit_returns_redeem_code(client, db_session, survey):
    resp = client.post("/s/spring/submit", json=_payload(token=_token(db_session, survey)))
    assert resp.status_code == 200
    data = resp.json()
    assert REDEEM_RE.match(data["redeem_code"])
    assert data["status"] == "new"


def test_submit_persists_submission(client, db_session, survey):
    client.post("/s/spring/submit", json=_payload(token=_token(db_session, survey)))
    sub = db_session.query(Submission).filter_by(survey_id=survey.id).one()
    assert sub.channel == "sms"
    assert sub.answers_json == {"q1": "满意"}
    assert sub.fingerprint == "fp-1"


def test_submit_persists_device_info(client, db_session, survey):
    device = {"platform": "iPhone", "screen": "390x844", "timezone": "Asia/Shanghai"}
    client.post("/s/spring/submit", json=_payload(device=device, token=_token(db_session, survey)))
    sub = db_session.query(Submission).filter_by(survey_id=survey.id).one()
    assert sub.device_json == device
    assert sub.ua is not None  # UA 由服务端 header 记录


def test_submit_duplicate_fingerprint_blocked(client, db_session, survey):
    client.post("/s/spring/submit", json=_payload(token=_token(db_session, survey)))
    resp = client.post("/s/spring/submit", json=_payload(token=_token(db_session, survey)))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "already_submitted"


def test_submit_too_fast_is_flagged(client, db_session, survey):
    resp = client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-fast", elapsed_ms=500, token=_token(db_session, survey)))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "invalid_submission"
    assert db_session.query(Submission).filter_by(fingerprint="fp-fast").one().status == "flagged"


def test_submit_other_device_ineligible(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    a = client.post("/s/spring/submit", json=_payload(fingerprint="fp-A", token=dist.token))
    assert a.status_code == 200
    resp = client.post("/s/spring/submit", json=_payload(fingerprint="fp-B", token=dist.token))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ineligible"


def test_submit_valid_token_marks_used(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    resp = client.post("/s/spring/submit", json=_payload(token=dist.token))
    assert resp.status_code == 200
    # used 列已删：是否已提交由 wj_submissions.token 判定
    assert db_session.query(Submission).filter_by(token=dist.token).count() == 1


def test_submit_sets_tier_reached_1(client, db_session, survey):
    resp = client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-tier", token=_token(db_session, survey)))
    assert resp.status_code == 200
    assert resp.json()["tier"] == 1
    sub = db_session.query(Submission).filter_by(fingerprint="fp-tier").one()
    assert sub.tier_reached == 1


def test_upgrade_merges_answers_and_keeps_code(client, db_session, survey):
    sub_resp = client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-up", token=_token(db_session, survey)))
    code = sub_resp.json()["redeem_code"]

    up = client.post("/s/spring/upgrade", json={
        "fingerprint": "fp-up", "answers": {"q2": "非常忠实"},
    })
    assert up.status_code == 200
    body = up.json()
    assert body["redeem_code"] == code  # 码不变
    assert body["tier"] == 2

    sub = db_session.query(Submission).filter_by(fingerprint="fp-up").one()
    assert sub.tier_reached == 2
    assert sub.answers_json == {"q1": "满意", "q2": "非常忠实"}  # 合并


def test_upgrade_without_submission_returns_404(client, survey):
    resp = client.post("/s/spring/upgrade", json={
        "fingerprint": "fp-none", "answers": {"q2": "x"},
    })
    assert resp.status_code == 404
    assert resp.json()["detail"] == "no_submission"


def test_upgrade_is_idempotent(client, db_session, survey):
    client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-idem", token=_token(db_session, survey)))
    first = client.post("/s/spring/upgrade", json={
        "fingerprint": "fp-idem", "answers": {"q2": "a"}})
    second = client.post("/s/spring/upgrade", json={
        "fingerprint": "fp-idem", "answers": {"q2": "b"}})
    assert second.status_code == 200
    assert second.json()["redeem_code"] == first.json()["redeem_code"]
    assert second.json()["tier"] == 2

    sub = db_session.query(Submission).filter_by(fingerprint="fp-idem").one()
    assert sub.answers_json.get("q2") == "a"  # 第二次 upgrade 不应覆盖已合并的 tier-2 答案


def test_submit_stores_session_id(client, db_session, survey):
    client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-sess", session_id="sess-xyz", token=_token(db_session, survey)))
    sub = db_session.query(Submission).filter_by(fingerprint="fp-sess").one()
    assert sub.session_id == "sess-xyz"


def test_submit_degree_and_display_code(client, db_session, survey):
    resp = client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-deg", answers={"q1": "满意", "q_degree": "475度"},
        token=_token(db_session, survey)))
    data = resp.json()
    sub = db_session.query(Submission).filter_by(fingerprint="fp-deg").one()
    assert sub.degree == 475
    assert data["display_code"] == f"{sub.redeem_code}02-475"


def test_upgrade_display_code_is_10(client, db_session, survey):
    client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-up10", answers={"q1": "满意", "q_degree": "300"},
        token=_token(db_session, survey)))
    up = client.post("/s/spring/upgrade", json={"fingerprint": "fp-up10", "answers": {"q2": "x"}})
    d = up.json()
    assert d["tier"] == 2
    assert d["display_code"].endswith("10-300")


def test_upgrade_sets_degree_from_answers(client, db_session, survey):
    # 度数弹窗在「继续作答」路径里于 tier2 提交时才填，需 upgrade 写入 degree
    client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-upd", answers={"q1": "满意"}, token=_token(db_session, survey)))
    up = client.post("/s/spring/upgrade", json={
        "fingerprint": "fp-upd", "answers": {"q2": "x", "q_degree": "525"}})
    assert up.json()["display_code"].endswith("10-525")
    sub = db_session.query(Submission).filter_by(fingerprint="fp-upd").one()
    assert sub.degree == 525


def test_submit_same_token_idempotent(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    first = client.post("/s/spring/submit", json=_payload(fingerprint="fp-A", token=dist.token))
    second = client.post("/s/spring/submit", json=_payload(fingerprint="fp-A", token=dist.token))
    assert second.status_code == 200
    assert second.json()["redeem_code"] == first.json()["redeem_code"]
    assert db_session.query(Submission).filter_by(token=dist.token).count() == 1


def test_submit_rejected_after_ends_at(client, db_session):
    from datetime import datetime, timedelta
    s = Survey(slug="ended", title="t", status="active", schema_json=[
        {"id": "q1", "type": "single", "title": "q", "options": ["a"]}],
        ends_at=datetime.utcnow() - timedelta(hours=1))
    db_session.add(s)
    db_session.commit()
    resp = client.post("/s/ended/submit", json={
        "fingerprint": "fp-x", "answers": {"q1": "a"}, "elapsed_ms": 15000, "channel": "sms",
        "token": "whatever"})  # ends_at 闸在 token 校验之前
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ended"


def test_submit_without_token_rejected(client, survey):
    resp = client.post("/s/spring/submit", json=_payload())
    assert resp.status_code == 409
    assert resp.json()["detail"] == "token_required"


def test_submit_expired_token_rejected(client, db_session, survey):
    from datetime import datetime, timedelta
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=72)
    dist.expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    resp = client.post("/s/spring/submit", json=_payload(token=dist.token))
    assert resp.status_code == 409
    assert resp.json()["detail"] == "token_expired"


def test_submit_expired_token_after_submission_idempotent(client, db_session, survey):
    # 已提交者即使 token 过期，重复提交仍幂等返回原码（先查提交再判过期）
    from datetime import datetime, timedelta
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=72)
    first = client.post("/s/spring/submit", json=_payload(fingerprint="fp-ie", token=dist.token))
    assert first.status_code == 200
    dist.expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    second = client.post("/s/spring/submit", json=_payload(fingerprint="fp-ie", token=dist.token))
    assert second.status_code == 200
    assert second.json()["redeem_code"] == first.json()["redeem_code"]


def test_upgrade_rejected_after_ends_at(client, db_session):
    from datetime import datetime, timedelta
    s = Survey(slug="endup", title="t", status="active", schema_json=[
        {"id": "q1", "type": "single", "title": "q", "options": ["a"]}])
    db_session.add(s)
    db_session.commit()
    dist = create_distribution(db_session, s.id, "sms", ttl_hours=72)
    assert client.post("/s/endup/submit", json=_payload(
        fingerprint="fp-eu", token=dist.token, answers={"q1": "a"})).status_code == 200
    s.ends_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    resp = client.post("/s/endup/upgrade", json={"fingerprint": "fp-eu", "answers": {"q2": "x"}})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "ended"


def test_submit_degree_above_1000_treated_as_zero(client, db_session, survey):
    resp = client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-deg-hi", token=_token(db_session, survey),
        answers={"q1": "满意", "q_degree": "1500"}))
    sub = db_session.query(Submission).filter_by(fingerprint="fp-deg-hi").one()
    assert sub.degree == 0
    assert resp.json()["display_code"].endswith("02-0")


def test_submit_degree_1000_boundary_valid(client, db_session, survey):
    resp = client.post("/s/spring/submit", json=_payload(
        fingerprint="fp-deg-1k", token=_token(db_session, survey),
        answers={"q1": "满意", "q_degree": "1000"}))
    assert resp.json()["display_code"].endswith("02-1000")
