# tests/test_track.py
import pytest

from app.models import Survey, Event


@pytest.fixture
def survey(db_session):
    s = Survey(slug="spring", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    return s


def test_track_records_events(client, db_session, survey):
    resp = client.post("/s/spring/track", json={
        "session_id": "sess-1", "fingerprint": "fp-1", "channel": "sms",
        "events": [
            {"name": "page_view", "props": {"submitted_tier": 0}, "client_ts": 111},
            {"name": "answer", "props": {"question_id": "q1", "value": "满意"}, "client_ts": 222},
        ],
    })
    assert resp.status_code == 200
    rows = db_session.query(Event).filter_by(session_id="sess-1").order_by(Event.id).all()
    assert len(rows) == 2
    assert rows[0].event_type == "页面浏览"  # 落库即中文
    assert rows[0].survey_id == survey.id
    assert rows[0].channel == "sms"
    assert rows[1].question_id == "q1"
    assert rows[1].option_value == "满意"
    assert rows[1].fingerprint == "fp-1"


def test_track_unknown_survey_still_ok(client, db_session):
    resp = client.post("/s/nope/track", json={
        "session_id": "s2", "events": [{"name": "page_view"}]})
    assert resp.status_code == 200  # 埋点不因问卷不存在而失败


def test_track_caps_event_count(client, db_session, survey):
    events = [{"name": "answer", "props": {"i": i}} for i in range(250)]
    resp = client.post("/s/spring/track", json={"session_id": "big", "events": events})
    assert resp.status_code == 200
    n = db_session.query(Event).filter_by(session_id="big").count()
    assert n <= 100  # 单次上报封顶，防滥用


def test_track_stores_question_title_snapshot(client, db_session):
    s = Survey(slug="ttl1", title="t", status="active", schema_json=[
        {"id": "q1", "type": "single", "title": "您的满意度？", "options": ["满意"]}])
    db_session.add(s)
    db_session.commit()
    resp = client.post("/s/ttl1/track", json={
        "session_id": "ttl-s1", "events": [
            {"name": "answer", "props": {"question_id": "q1", "value": "满意"}},
            {"name": "page_view", "props": {}},
        ]})
    assert resp.status_code == 200
    rows = db_session.query(Event).filter_by(session_id="ttl-s1").order_by(Event.id).all()
    assert rows[0].question_id == "q1"
    assert rows[0].question_title == "您的满意度？"  # 题目内容快照
    assert rows[1].question_title is None


def test_page_leave_upserts_single_row_per_session(client, db_session):
    s = Survey(slug="lv1", title="t", status="active", schema_json=[])
    db_session.add(s)
    db_session.commit()
    # 第一次离开
    client.post("/s/lv1/track", json={"session_id": "lv-s1", "events": [
        {"name": "page_leave", "props": {"question_id": "q2", "dwell_ms": 12300}}]})
    # 回来后再离开两次 → 仍只有一条,取最新值
    client.post("/s/lv1/track", json={"session_id": "lv-s1", "events": [
        {"name": "page_leave", "props": {"question_id": "q5", "dwell_ms": 548200}}]})
    client.post("/s/lv1/track", json={"session_id": "lv-s1", "events": [
        {"name": "page_leave", "props": {"question_id": "q5", "dwell_ms": 1139100}}]})
    rows = db_session.query(Event).filter_by(session_id="lv-s1", event_type="页面离开").all()
    assert len(rows) == 1                      # 一个会话一条
    assert rows[0].dwell_seconds == 1139.1     # 最终累计停留
    assert rows[0].question_id == "q5"         # 最后停留的题
