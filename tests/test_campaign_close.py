from datetime import datetime

import pytest

from app.distribution import create_distribution
from app.migrations import ensure_moody_activity_window
from app.models import Distribution, Submission, Survey
from scripts.seed_moody import upsert_moody


@pytest.fixture
def campaign(db_session):
    # Reproduce deployment over the old September 30 configuration.
    db_session.add(Survey(
        slug="moody", title="old", schema_json=[],
        ends_at=datetime(2026, 9, 30, 23, 59, 59),
    ))
    db_session.commit()
    ensure_moody_activity_window(db_session.get_bind())
    return upsert_moody(db_session)


@pytest.mark.parametrize("now,expected", [
    (datetime(2026, 9, 5, 13, 59, 59), "none"),
    (datetime(2026, 9, 5, 14, 0, 0, 999999), "none"),
    (datetime(2026, 9, 5, 14, 0, 1), "ended"),
    (datetime(2026, 9, 7, 12), "ended"),
])
def test_deployed_campaign_closes_at_requested_time(client, campaign, monkeypatch, now, expected):
    monkeypatch.setattr("app.routers.survey.now_cn", lambda: now)
    response = client.get("/api/s/moody")
    assert response.status_code == 200
    assert response.json()["token_status"] == expected
    assert campaign.ends_at == datetime(2026, 9, 5, 14)


def test_closed_campaign_rejects_claim_cached_token_and_submission(client, db_session, campaign, monkeypatch):
    dist = create_distribution(db_session, campaign.id, "tmall", ttl_hours=72)
    monkeypatch.setattr("app.routers.survey.now_cn", lambda: datetime(2026, 9, 7, 12))
    count = db_session.query(Distribution).count()
    for query in ("?fp=new-device", f"?fp=old-device&t={dist.token}"):
        body = client.get("/api/s/moody" + query).json()
        assert body["token_status"] == "ended"
        assert body["schema"] == []
    assert db_session.query(Distribution).count() == count
    for token in (None, "unknown-token", dist.token):
        response = client.post("/s/moody/submit", json={
            "fingerprint": "old-device", "token": token, "answers": {},
        })
        assert response.status_code == 409
        assert response.json()["detail"] == "ended"
    assert db_session.query(Submission).count() == 0


@pytest.mark.parametrize("status,tier", [("in_progress", 1), ("new", 1), ("new", 2), ("redeemed", 2)])
def test_close_stops_partial_answers_but_preserves_completed_codes(
    client, db_session, campaign, monkeypatch, status, tier,
):
    dist = create_distribution(db_session, campaign.id, "tmall", ttl_hours=72)
    sub = Submission(
        survey_id=campaign.id, token=dist.token, fingerprint="existing-device",
        channel="tmall", redeem_code="WJ-CLOSE1", status=status, tier_reached=tier,
        answers_json={"q3": "两种都戴，戴美瞳更多"}, degree=525,
    )
    db_session.add(sub)
    db_session.commit()
    monkeypatch.setattr("app.routers.survey.now_cn", lambda: datetime(2026, 9, 7, 12))
    body = client.get(f"/api/s/moody?t={dist.token}&fp=existing-device").json()
    assert body["can_resume_tier2"] is False
    assert body["schema"] == []
    assert body["token_status"] == ("ended" if status == "in_progress" else "submitted_self")
    assert bool(body["display_code"]) is (status != "in_progress")
    retry = client.post("/s/moody/submit", json={
        "fingerprint": "existing-device", "token": dist.token, "answers": {},
    })
    assert retry.status_code == (409 if status == "in_progress" else 200)
    if status == "in_progress":
        assert retry.json()["detail"] == "ended"
    else:
        assert retry.json()["display_code"] == body["display_code"]
    upgrade = client.post("/s/moody/upgrade", json={
        "fingerprint": "existing-device", "answers": {"q_degree": "575"},
    })
    assert upgrade.status_code == 409
    assert upgrade.json()["detail"] == "ended"
    db_session.refresh(sub)
    assert sub.status == status
    assert sub.tier_reached == tier
    assert sub.degree == 525
    assert sub.answers_json == {"q3": "两种都戴，戴美瞳更多"}
