# tests/test_survey_api.py
from datetime import datetime, timedelta

import pytest

from app.models import Survey, Distribution
from app.distribution import create_distribution
from app.routers.survey import _activity_ended
from app.timeutil import now_cn


@pytest.fixture
def survey(db_session):
    s = Survey(slug="spring", title="春季问卷", schema_json=[
        {"id": "q1", "type": "single", "title": "满意吗", "options": ["满意", "一般"]}
    ])
    db_session.add(s)
    db_session.commit()
    return s


def test_get_survey_json_without_fp_returns_no_schema(client, survey):
    resp = client.get("/api/s/spring")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "春季问卷"
    assert data["token_status"] == "none"
    assert data["schema"] == []


def test_get_survey_404(client):
    resp = client.get("/api/s/missing")
    assert resp.status_code == 404


def test_get_survey_with_valid_token_binds_device(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    resp = client.get(f"/api/s/spring?t={dist.token}&c=sms&fp=fp-1")
    assert resp.status_code == 200
    assert resp.json()["token_status"] == "eligible"
    db_session.refresh(dist)
    assert dist.bound_fingerprint == "fp-1"  # 打开轨迹由 wj_events 承担，不再冗余存 distributions


def test_get_survey_token_other_device_ineligible(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    a = client.get(f"/api/s/spring?t={dist.token}&c=sms&fp=fp-A")  # 设备 A 首开绑定
    assert a.json()["token_status"] == "eligible"
    resp = client.get(f"/api/s/spring?t={dist.token}&c=sms&fp=fp-B")  # 设备 B
    assert resp.json()["token_status"] == "ineligible"
    assert resp.json()["schema"] == []


def test_get_survey_token_returns_user_code(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    resp = client.get(f"/api/s/spring?t={dist.token}&c=sms&fp=fp-A")
    assert resp.json()["token_status"] == "eligible"
    assert resp.json()["user_code"]


def test_get_survey_submitted_self_shows_code(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    sub = client.post("/s/spring/submit", json={
        "fingerprint": "fp-A", "answers": {"q1": "满意"},
        "elapsed_ms": 15000, "channel": "sms", "token": dist.token})
    assert sub.status_code == 200
    reopen = client.get(f"/api/s/spring?t={dist.token}&c=sms&fp=fp-A")
    body = reopen.json()
    assert body["token_status"] == "submitted_self"
    assert body["display_code"] == sub.json()["display_code"]


def test_get_survey_ended_when_past_ends_at(client, db_session):
    s = Survey(slug="over", title="t", schema_json=[],
               ends_at=datetime.utcnow() - timedelta(hours=1))
    db_session.add(s)
    db_session.commit()
    resp = client.get("/api/s/over")
    assert resp.json()["token_status"] == "ended"
    assert resp.json()["schema"] == []


def test_activity_end_includes_the_configured_final_second():
    s = Survey(ends_at=datetime(2026, 8, 31, 9, 59, 59))
    assert _activity_ended(s, datetime(2026, 8, 31, 9, 59, 59, 999999)) is False
    assert _activity_ended(s, datetime(2026, 8, 31, 10, 0, 0)) is True


def test_get_survey_not_started_hides_schema(client, db_session):
    s = Survey(
        slug="future", title="t",
        schema_json=[{"id": "q1", "type": "single", "title": "q", "options": ["a"]}],
        starts_at=now_cn() + timedelta(hours=1),
    )
    db_session.add(s)
    db_session.commit()
    resp = client.get("/api/s/future?c=test&fp=future-device")
    assert resp.status_code == 200
    assert resp.json()["token_status"] == "not_started"
    assert resp.json()["schema"] == []


def test_get_survey_submitted_tier_zero_without_fp(client, survey):
    assert client.get("/api/s/spring").json()["submitted_tier"] == 0


def test_get_survey_returns_new_product_url(client, db_session):
    s = Survey(slug="np", title="t", schema_json=[],
               new_product_url="https://shop.example/new")
    db_session.add(s)
    db_session.commit()
    assert client.get("/api/s/np").json()["new_product_url"] == "https://shop.example/new"


def test_get_survey_new_product_url_defaults_none(client, survey):
    assert client.get("/api/s/spring").json()["new_product_url"] is None


def test_get_survey_returns_show_if(client, db_session):
    s = Survey(slug="branchy2", title="t", schema_json=[
        {"id": "q1", "type": "single", "title": "用过吗", "options": ["用过", "没用过"]},
        {"id": "q2", "type": "single", "title": "满意度", "options": ["满意"],
         "show_if": {"q": "q1", "in": ["用过"]}},
    ])
    db_session.add(s)
    db_session.commit()
    data = client.get("/api/s/branchy2?fp=fp-si").json()
    assert data["schema"][1]["show_if"] == {"q": "q1", "in": ["用过"]}


def test_get_survey_claim_issues_token(client, db_session, survey):
    resp = client.get("/api/s/spring?c=sms&fp=fp-claim",
                      headers={"x-forwarded-for": "10.0.0.1"})
    data = resp.json()
    assert data["token_status"] == "claim"
    assert data["token"] and data["user_code"]
    dist = db_session.query(Distribution).filter_by(token=data["token"]).one()
    assert dist.bound_fingerprint == "fp-claim"
    assert dist.bound_ip == "10.0.0.1"
    assert dist.channel == "sms"


def test_get_survey_claim_same_device_idempotent(client, survey):
    first = client.get("/api/s/spring?fp=fp-same",
                       headers={"x-forwarded-for": "10.0.0.2"}).json()
    again = client.get("/api/s/spring?fp=fp-same",
                       headers={"x-forwarded-for": "10.0.0.99"}).json()
    assert again["token"] == first["token"]  # 设备优先，换 IP 拿回同一 token


def test_get_survey_claim_same_ip_second_device_ineligible(client, survey):
    client.get("/api/s/spring?fp=fp-ip-a", headers={"x-forwarded-for": "10.0.0.3"})
    resp = client.get("/api/s/spring?fp=fp-ip-b",
                      headers={"x-forwarded-for": "10.0.0.3"}).json()
    assert resp["token_status"] == "ineligible"
    assert resp["schema"] == []


def test_get_survey_submitted_self_survives_token_expiry(client, db_session, survey):
    # 已提交 + 超 72h + 活动未结束 → 仍看兑奖码页（先查提交再判过期）
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=72)
    sub = client.post("/s/spring/submit", json={
        "fingerprint": "fp-exp", "answers": {"q1": "满意"},
        "elapsed_ms": 15000, "channel": "sms", "token": dist.token})
    assert sub.status_code == 200
    dist.expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    reopen = client.get(f"/api/s/spring?t={dist.token}&fp=fp-exp").json()
    assert reopen["token_status"] == "submitted_self"
    assert reopen["display_code"] == sub.json()["display_code"]


def test_get_survey_submitted_self_survives_survey_end(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=72)
    sub = client.post("/s/spring/submit", json={
        "fingerprint": "fp-ended", "answers": {"q1": "满意"},
        "elapsed_ms": 15000, "channel": "sms", "token": dist.token})
    assert sub.status_code == 200
    survey.ends_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    reopen = client.get(f"/api/s/spring?t={dist.token}&fp=fp-ended").json()
    assert reopen["token_status"] == "submitted_self"
    assert reopen["display_code"] == sub.json()["display_code"]


def test_submit_existing_submission_survives_survey_end(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=72)
    first = client.post("/s/spring/submit", json={
        "fingerprint": "fp-resubmit-ended", "answers": {"q1": "满意"},
        "elapsed_ms": 15000, "channel": "sms", "token": dist.token})
    assert first.status_code == 200
    survey.ends_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    again = client.post("/s/spring/submit", json={
        "fingerprint": "fp-resubmit-ended", "answers": {"q1": "满意"},
        "elapsed_ms": 15000, "channel": "sms", "token": dist.token})
    assert again.status_code == 200
    assert again.json()["display_code"] == first.json()["display_code"]


def test_get_survey_expired_unsubmitted_token(client, db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=72)
    dist.expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    resp = client.get(f"/api/s/spring?t={dist.token}&fp=fp-x").json()
    assert resp["token_status"] == "expired"
    assert resp["schema"] == []


def test_get_survey_submitted_fingerprint_with_other_token_shows_code(client, db_session, survey):
    # 提交记录与 token 不挂钩（如历史无 token 口径）时，同设备重开必须直达兑奖码页：
    # 已提交判定按 token 或指纹任一匹配，与 submit 端 is_duplicate 的指纹口径对称
    from app.models import Submission
    db_session.add(Submission(
        survey_id=survey.id, redeem_code="WJ-LEGACY", channel="sms",
        answers_json={"q1": "满意"}, status="new", tier_reached=1,
        fingerprint="fp-legacy"))
    db_session.commit()
    claim = client.get("/api/s/spring?fp=fp-legacy",
                       headers={"x-forwarded-for": "10.0.9.1"}).json()
    assert claim["token_status"] == "claim"
    follow = client.get(f"/api/s/spring?t={claim['token']}&fp=fp-legacy").json()
    assert follow["token_status"] == "submitted_self"
    assert follow["display_code"].startswith("WJ-LEGACY")
    assert follow["schema"] == [] or follow["already_submitted"] is True


def test_get_survey_expired_device_cannot_reclaim(client, db_session, survey):
    # 72h 过期未提交后，同设备再开通用链接 → 命中同一过期 token，不能重新领
    claim = client.get("/api/s/spring?fp=fp-dead",
                       headers={"x-forwarded-for": "10.0.0.4"}).json()
    dist = db_session.query(Distribution).filter_by(token=claim["token"]).one()
    dist.expires_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    again = client.get("/api/s/spring?fp=fp-dead",
                       headers={"x-forwarded-for": "10.0.0.4"}).json()
    assert again["token"] == claim["token"]  # claim 幂等返回过期 token
    follow = client.get(f"/api/s/spring?t={again['token']}&fp=fp-dead").json()
    assert follow["token_status"] == "expired"


def test_tmall_claim_with_aid_idempotent_over_api(client, survey):
    r1 = client.get("/api/s/spring?c=tmall&aid=mp_api&fp=fp1",
                    headers={"x-forwarded-for": "10.0.0.1"})
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["token_status"] == "claim"
    tok = d1["token"]
    # 同 aid 再次首开（无 token）→ 同一个 token
    r2 = client.get("/api/s/spring?c=tmall&aid=mp_api&fp=fp1",
                    headers={"x-forwarded-for": "10.0.0.1"})
    assert r2.json()["token"] == tok


def test_tmall_token_recheck_passes_with_drifted_fingerprint(client, survey):
    claim = client.get("/api/s/spring?c=tmall&aid=mp_api2&fp=fpX",
                       headers={"x-forwarded-for": "10.0.0.2"}).json()
    tok = claim["token"]
    # 带 token 复检，指纹漂移成 fpY → 仍 eligible（不被指纹硬校验拦下）
    recheck = client.get(f"/api/s/spring?t={tok}&c=tmall&aid=mp_api2&fp=fpY",
                         headers={"x-forwarded-for": "10.0.0.2"})
    assert recheck.json()["token_status"] == "eligible"
