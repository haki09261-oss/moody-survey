# tests/test_admin.py
import pytest

from app.models import AdminUser, Distribution, Event, Survey, Submission
from app.security import hash_password


@pytest.fixture
def admin(db_session):
    u = AdminUser(username="ops1", password_hash=hash_password("pw"), role="ops")
    db_session.add(u)
    db_session.commit()
    return ("ops1", "pw")


def test_create_survey(client, admin):
    resp = client.post("/admin/surveys", auth=admin, json={
        "slug": "s1", "title": "问卷1",
        "schema_json": [{"id": "q1", "type": "text", "title": "建议"}],
    })
    assert resp.status_code == 201
    assert resp.json()["slug"] == "s1"


def test_create_survey_persists_new_product_url(client, db_session, admin):
    resp = client.post("/admin/surveys", auth=admin, json={
        "slug": "np1", "title": "t", "schema_json": [],
        "new_product_url": "https://shop.example/x"})
    assert resp.status_code == 201
    s = db_session.query(Survey).filter_by(slug="np1").one()
    assert s.new_product_url == "https://shop.example/x"


def test_create_survey_requires_auth(client):
    resp = client.post("/admin/surveys", json={"slug": "s1", "title": "t", "schema_json": []})
    assert resp.status_code == 401


def test_list_submissions_filter_by_status(client, db_session, admin):
    s = Survey(slug="s1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    db_session.add_all([
        Submission(survey_id=s.id, redeem_code="WJ-AAAAAA", channel="sms", answers_json={}, status="new"),
        Submission(survey_id=s.id, redeem_code="WJ-BBBBBB", channel="sms", answers_json={}, status="flagged",
                   ip="1.2.3.4", ua="UA-test", device_json={"platform": "iPhone"}),
    ])
    db_session.commit()
    resp = client.get(f"/admin/submissions?survey_id={s.id}&status=flagged", auth=admin)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["redeem_code"] == "WJ-BBBBBB"
    assert items[0]["ip"] == "1.2.3.4"
    assert items[0]["ua"] == "UA-test"
    assert items[0]["device"] == {"platform": "iPhone"}


def test_reject_submission(client, db_session, admin):
    s = Survey(slug="s1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    sub = Submission(survey_id=s.id, redeem_code="WJ-CCCCCC", channel="sms", answers_json={}, status="new")
    db_session.add(sub)
    db_session.commit()
    resp = client.post(f"/admin/submissions/{sub.id}/reject", auth=admin)
    assert resp.status_code == 200
    db_session.refresh(sub)
    assert sub.status == "rejected"


def test_delete_submission(client, db_session, admin):
    s = Survey(slug="s1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    sub = Submission(survey_id=s.id, redeem_code="WJ-DDDDDD", channel="sms", answers_json={}, status="new")
    db_session.add(sub)
    db_session.commit()
    sub_id = sub.id

    resp = client.delete(f"/admin/submissions/{sub_id}", auth=admin)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    assert db_session.get(Submission, sub_id) is None


def test_delete_submission_requires_auth(client, db_session):
    resp = client.delete("/admin/submissions/1")
    assert resp.status_code == 401


def test_list_submissions_includes_tier(client, db_session, admin):
    s = Survey(slug="s2", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    db_session.add(Submission(survey_id=s.id, redeem_code="WJ-TIER01", channel="sms",
                              answers_json={}, status="new", tier_reached=2))
    db_session.commit()
    resp = client.get(f"/admin/submissions?survey_id={s.id}", auth=admin)
    assert resp.status_code == 200
    assert resp.json()["items"][0]["tier_reached"] == 2


def test_create_survey_preserves_show_if(client, db_session, admin):
    schema = [
        {"id": "q1", "type": "single", "title": "用过吗", "options": ["用过", "没用过"], "tier": 1},
        {"id": "q2", "type": "single", "title": "满意度", "options": ["满意", "一般"], "tier": 1,
         "show_if": {"q": "q1", "in": ["用过"]}},
    ]
    resp = client.post("/admin/surveys", auth=admin, json={
        "slug": "branchy", "title": "t", "schema_json": schema})
    assert resp.status_code == 201
    s = db_session.query(Survey).filter_by(slug="branchy").one()
    assert s.schema_json[1]["show_if"] == {"q": "q1", "in": ["用过"]}


def test_survey_stats(client, db_session, admin):
    s = Survey(slug="st", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    db_session.add_all([
        Event(survey_id=s.id, event_type="页面浏览", fingerprint="a", session_id="1"),
        Event(survey_id=s.id, event_type="页面浏览", fingerprint="a", session_id="2"),
        Event(survey_id=s.id, event_type="页面浏览", fingerprint="b", session_id="3"),
        Event(survey_id=s.id, event_type="页面离开", dwell_seconds=1.0),
        Event(survey_id=s.id, event_type="页面离开", dwell_seconds=3.0),
        Event(survey_id=s.id, event_type="下一题", question_id="q1", dwell_seconds=2.0),
        Event(survey_id=s.id, event_type="浏览问题", question_id="q1", session_id="1"),
        Event(survey_id=s.id, event_type="回答问题", question_id="q1", option_value="A", session_id="1"),
    ])
    db_session.add(Submission(survey_id=s.id, redeem_code="WJ-ST0001", channel="x",
                              answers_json={}, status="new", tier_reached=1))
    db_session.commit()
    r = client.get(f"/admin/surveys/{s.id}/stats", auth=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["pv"] == 3
    assert d["uv"] == 2
    assert d["avg_dwell_ms"] == 2000
    assert d["submissions"] == 1
    assert d["clicks"]["下一题"] == 1
    funnel = {f["question_id"]: f for f in d["funnel"]}
    assert funnel["q1"]["views"] == 1 and funnel["q1"]["answers"] == 1


def test_submission_events_endpoint(client, db_session, admin):
    s = Survey(slug="se", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    sub = Submission(survey_id=s.id, redeem_code="WJ-SE0001", channel="x",
                     answers_json={}, status="new", session_id="sess-9")
    db_session.add(sub)
    db_session.add_all([
        Event(survey_id=s.id, session_id="sess-9", event_type="页面浏览"),
        Event(survey_id=s.id, session_id="sess-9", event_type="下一题", question_id="q1", dwell_seconds=1.5),
        Event(survey_id=s.id, session_id="sess-9", event_type="页面离开", dwell_seconds=4.2),
        Event(survey_id=s.id, session_id="other", event_type="页面浏览"),  # 不应混入
    ])
    db_session.commit()
    r = client.get(f"/admin/submissions/{sub.id}/events", auth=admin)
    assert r.status_code == 200
    d = r.json()
    assert d["session_id"] == "sess-9"
    assert d["dwell_ms"] == 4200
    assert [e["name"] for e in d["events"]] == ["页面浏览", "下一题", "页面离开"]


def test_submission_events_per_question_detail(client, db_session, admin):
    s = Survey(slug="se2", title="t", schema_json=[
        {"id": "q1", "type": "single", "title": "Q1"},
        {"id": "q2", "type": "multi", "title": "Q2"},
    ])
    db_session.add(s)
    db_session.commit()
    sub = Submission(survey_id=s.id, redeem_code="WJ-SE0002", channel="x",
                     answers_json={"q1": "A", "q2": ["X", "Y"]}, status="new", session_id="ss")
    db_session.add(sub)
    db_session.add_all([
        Event(survey_id=s.id, session_id="ss", event_type="下一题", question_id="q1", dwell_seconds=3.0),
        Event(survey_id=s.id, session_id="ss", event_type="提交问卷", question_id="q2", dwell_seconds=5.0),
        Event(survey_id=s.id, session_id="ss", event_type="页面离开", dwell_seconds=9.0),
    ])
    db_session.commit()
    r = client.get(f"/admin/submissions/{sub.id}/events", auth=admin)
    d = r.json()
    qs = {q["question_id"]: q for q in d["questions"]}
    assert qs["q1"]["dwell_ms"] == 3000   # 下一题事件携带的停留
    assert qs["q2"]["dwell_ms"] == 5000   # 提交问卷事件携带的停留（最后一题）
    assert qs["q1"]["value"] == "A"
    assert qs["q2"]["value"] == ["X", "Y"]


def test_survey_event_rows(client, db_session, admin):
    s = Survey(slug="et", title="ER问卷", schema_json=[
        {"id": "q1", "type": "single", "title": "Q1"},
        {"id": "q2", "type": "multi", "title": "Q2"},
    ])
    db_session.add(s)
    db_session.commit()
    sub = Submission(survey_id=s.id, redeem_code="WJ-ET0001", channel="x",
                     answers_json={"q1": "A", "q2": ["X", "Y"]}, status="new", session_id="z1")
    db_session.add(sub)
    db_session.add_all([
        Event(survey_id=s.id, session_id="z1", event_type="页面浏览", fingerprint="f1"),
        Event(survey_id=s.id, session_id="z1", event_type="下一题", question_id="q1", dwell_seconds=2.0),
        Event(survey_id=s.id, session_id="z1", event_type="提交问卷", question_id="q2", dwell_seconds=5.0),
        Event(survey_id=s.id, session_id="z1", event_type="页面离开", dwell_seconds=8.0),
    ])
    db_session.commit()
    d = client.get(f"/admin/surveys/{s.id}/event-rows", auth=admin).json()
    assert d["survey_id"] == s.id
    assert d["survey_name"] == "ER问卷"
    assert d["pv"] == 1 and d["uv"] == 1
    rows = d["rows"]
    assert len(rows) == 3   # q1 一行 + q2 多选两个选项两行
    q1 = [x for x in rows if x["q_id"] == "q1"][0]
    assert q1["option"] == "A" and q1["q_dwell_ms"] == 2000 and q1["submitted"] == "是"  # 下一题事件停留
    assert q1["q_type"] == "单选"   # 问题类型中文
    assert q1["redeem_code"] == "WJ-ET0001" and q1["survey_name"] == "ER问卷"
    q2opts = sorted(x["option"] for x in rows if x["q_id"] == "q2")
    assert q2opts == ["X", "Y"]
    assert all(x["q_dwell_ms"] == 5000 for x in rows if x["q_id"] == "q2")  # 提交问卷事件停留


def test_create_survey_with_activity_window_persists(client, db_session, admin):
    resp = client.post("/admin/surveys", auth=admin, json={
        "slug": "campaign1", "title": "活动问卷", "schema_json": [],
        "starts_at": "2030-06-28T10:00:00",
        "ends_at": "2030-06-30T23:59:59"})
    assert resp.status_code == 201
    s = db_session.query(Survey).filter_by(slug="campaign1").one()
    assert s.starts_at is not None and s.starts_at.day == 28
    assert s.ends_at is not None and s.ends_at.year == 2030


def test_batch_delete_submissions(client, db_session, admin):
    s = Survey(slug="bd1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    db_session.add_all([
        Submission(survey_id=s.id, redeem_code=f"WJ-BD000{i}", channel="sms",
                   answers_json={}, status="new") for i in range(3)])
    db_session.commit()
    ids = [x.id for x in db_session.query(Submission).filter_by(survey_id=s.id).all()]
    resp = client.post("/admin/submissions/batch-delete", auth=admin,
                       json={"ids": ids[:2] + [99999]})  # 含一个不存在的 id
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    assert db_session.query(Submission).filter_by(survey_id=s.id).count() == 1


def test_batch_delete_requires_auth(client):
    resp = client.post("/admin/submissions/batch-delete", json={"ids": [1]})
    assert resp.status_code == 401


def test_survey_question_stats_aggregates_views_dwell_options(client, db_session, admin):
    s = Survey(slug="qs1", title="QS问卷", schema_json=[
        {"id": "q1", "type": "single", "title": "第一题", "options": ["A", "B"]},
        {"id": "q2", "type": "multi", "title": "第二题", "options": ["X", "Y"]},
    ])
    db_session.add(s)
    db_session.commit()
    # 会话1：q1 选 A(停留 2s)，q2 选 X+Y(停留 5s)，已提交
    db_session.add(Submission(survey_id=s.id, redeem_code="WJ-QS0001", channel="x",
                              answers_json={"q1": "A", "q2": ["X", "Y"]}, status="new", session_id="s1"))
    db_session.add_all([
        Event(survey_id=s.id, session_id="s1", event_type="页面浏览", fingerprint="f1"),
        Event(survey_id=s.id, session_id="s1", event_type="下一题", question_id="q1", dwell_seconds=2.0),
        Event(survey_id=s.id, session_id="s1", event_type="提交问卷", question_id="q2", dwell_seconds=5.0),
        Event(survey_id=s.id, session_id="s1", event_type="页面离开", dwell_seconds=8.0),
    ])
    # 会话2：只看了 q1 选 B(停留 4s)，未提交
    db_session.add_all([
        Event(survey_id=s.id, session_id="s2", event_type="页面浏览", fingerprint="f2"),
        Event(survey_id=s.id, session_id="s2", event_type="回答问题", question_id="q1", option_value="B"),
        Event(survey_id=s.id, session_id="s2", event_type="下一题", question_id="q1", dwell_seconds=4.0),
        Event(survey_id=s.id, session_id="s2", event_type="页面离开", dwell_seconds=4.5),
    ])
    db_session.commit()
    d = client.get(f"/admin/surveys/{s.id}/question-stats", auth=admin).json()
    assert d["survey_name"] == "QS问卷"
    assert d["pv"] == 2 and d["uv"] == 2 and d["submissions"] == 1
    qs = {q["q_id"]: q for q in d["questions"]}
    q1 = qs["q1"]
    assert q1["q_title"] == "第一题"
    assert q1["viewers"] == 2          # 两个会话都看过
    assert q1["answered"] == 1         # 正式答案仅统计已提交答卷，未提交埋点不混入样本
    assert q1["avg_dwell_ms"] == 3000  # (2000 + 4000) / 2
    opt = {o["option"]: o for o in q1["options"]}
    assert opt["A"]["count"] == 1 and "B" not in opt
    assert opt["A"]["pct"] == 100
    q2 = qs["q2"]
    assert q2["viewers"] == 1 and q2["answered"] == 1
    opt2 = {o["option"]: o for o in q2["options"]}
    assert opt2["X"]["count"] == 1 and opt2["Y"]["count"] == 1  # 多选各计一次
    # 顺序按 schema
    assert [q["q_id"] for q in d["questions"]] == ["q1", "q2"]


def test_track_endpoint_stores_cn_event_type_and_dwell(client, db_session, survey_for_track=None):
    s = Survey(slug="trk1", title="t", status="active", schema_json=[])
    db_session.add(s)
    db_session.commit()
    resp = client.post("/s/trk1/track", json={
        "session_id": "trk-s1", "fingerprint": "fp-trk", "channel": "sms", "token": None,
        "events": [
            {"name": "page_view", "props": {}, "client_ts": 1000},
            {"name": "nav_next", "props": {"question_id": "q1", "dwell_ms": 2300}, "client_ts": 5000},
            {"name": "page_leave", "props": {"dwell_ms": 8000}, "client_ts": 9000},
        ]})
    assert resp.status_code == 200
    rows = db_session.query(Event).filter_by(session_id="trk-s1").order_by(Event.id).all()
    assert [r.event_type for r in rows] == ["页面浏览", "下一题", "页面离开"]  # 落库即中文
    assert rows[1].dwell_seconds == 2.3   # 题目停留时长独立列（毫秒转秒）
    assert rows[1].question_id == "q1"
    assert rows[2].dwell_seconds == 8.0   # 页面总停留独立列
    assert rows[0].dwell_seconds is None


def test_track_endpoint_splits_multi_answer_rows(client, db_session):
    s = Survey(slug="trk2", title="t", status="active", schema_json=[])
    db_session.add(s)
    db_session.commit()
    resp = client.post("/s/trk2/track", json={
        "session_id": "trk-s2", "fingerprint": "fp-trk2", "channel": "sms", "token": None,
        "events": [
            {"name": "answer", "props": {"question_id": "q2", "value": ["X", "Y"]}},
            {"name": "answer", "props": {"question_id": "q3", "value": "单选A"}},
        ]})
    assert resp.status_code == 200
    rows = db_session.query(Event).filter_by(session_id="trk-s2").order_by(Event.id).all()
    assert len(rows) == 3  # 多选拆两行 + 单选一行
    assert [(r.question_id, r.option_value) for r in rows] == [
        ("q2", "X"), ("q2", "Y"), ("q3", "单选A")]
    assert all(r.event_type == "回答问题" for r in rows)


def test_delete_submission_releases_device_and_ip(client, db_session, admin):
    s = Survey(slug="rel1", title="t", status="active", schema_json=[
        {"id": "q1", "type": "single", "title": "q", "options": ["a"]}])
    db_session.add(s)
    db_session.commit()
    # 设备A 领取并提交,占住 IP
    claim = client.get(f"/api/s/rel1?fp=fp-rel-a", headers={"x-forwarded-for": "10.9.9.9"}).json()
    sub = client.post("/s/rel1/submit", json={
        "fingerprint": "fp-rel-a", "answers": {"q1": "a"}, "elapsed_ms": 9000,
        "channel": "sms", "token": claim["token"]})
    assert sub.status_code == 200
    # 设备B 同 IP → 被拦
    b1 = client.get(f"/api/s/rel1?fp=fp-rel-b", headers={"x-forwarded-for": "10.9.9.9"}).json()
    assert b1["token_status"] == "ineligible"
    # 后台批量删除 A 的提交 → 分发绑定级联释放
    sid = db_session.query(Submission).filter_by(fingerprint="fp-rel-a").one().id
    resp = client.post("/admin/submissions/batch-delete", auth=admin, json={"ids": [sid]})
    assert resp.status_code == 200 and resp.json()["deleted"] == 1
    assert db_session.query(Distribution).filter_by(token=claim["token"]).first() is None
    # 设备B 现在能正常领取;设备A 也能重新开始
    b2 = client.get(f"/api/s/rel1?fp=fp-rel-b", headers={"x-forwarded-for": "10.9.9.9"}).json()
    assert b2["token_status"] == "claim"


def test_list_distributions_only_unsubmitted(client, db_session, admin):
    """/admin/distributions 默认只列「打开了但没提交」的；token 或指纹命中提交即排除。"""
    from datetime import timedelta
    from app.timeutil import now_cn

    s = Survey(slug="d1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    now = now_cn().replace(microsecond=0)
    db_session.add_all([
        # 打开未提交（有效）
        Distribution(survey_id=s.id, channel="tmall", token="tk_open",
                     created_at=now, expires_at=now + timedelta(hours=72),
                     bound_fingerprint="fp_open", user_code="U1"),
        # 打开未提交（已过期）
        Distribution(survey_id=s.id, channel="tmall", token="tk_exp",
                     created_at=now - timedelta(hours=100), expires_at=now - timedelta(hours=28),
                     bound_fingerprint="fp_exp", user_code="U2"),
        # 打开且已提交（按 token 命中）
        Distribution(survey_id=s.id, channel="tmall", token="tk_sub",
                     created_at=now, expires_at=now + timedelta(hours=72),
                     bound_fingerprint="fp_sub", user_code="U3"),
    ])
    db_session.add(Submission(survey_id=s.id, channel="tmall", token="tk_sub",
                              fingerprint="fp_sub", redeem_code="WJ-CCCCCC",
                              answers_json={}, status="new"))
    db_session.commit()

    resp = client.get(f"/admin/distributions?survey_id={s.id}", auth=admin)
    assert resp.status_code == 200
    items = resp.json()["items"]
    codes = {it["user_code"]: it for it in items}
    assert set(codes) == {"U1", "U2"}            # 已提交 U3 被排除
    assert codes["U1"]["expired"] is False
    assert codes["U2"]["expired"] is True

    # only_unsubmitted=false 时全部返回，并标注 submitted
    allr = client.get(f"/admin/distributions?survey_id={s.id}&only_unsubmitted=false", auth=admin).json()["items"]
    assert len(allr) == 3
    assert {it["user_code"]: it["submitted"] for it in allr} == {"U1": False, "U2": False, "U3": True}


def test_delete_distribution(client, db_session, admin):
    """删除「打开未提交」记录(distribution),设备随后可重新领码参与。"""
    s = Survey(slug="dd1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    from datetime import timedelta
    from app.timeutil import now_cn
    now = now_cn().replace(microsecond=0)
    d = Distribution(survey_id=s.id, channel="tmall", token="tk_del",
                     created_at=now, expires_at=now + timedelta(hours=72),
                     bound_fingerprint="fp_del", user_code="U9")
    db_session.add(d)
    db_session.commit()
    did = d.id

    resp = client.delete(f"/admin/distributions/{did}", auth=admin)
    assert resp.status_code == 200 and resp.json()["deleted"] is True
    assert db_session.query(Distribution).filter_by(id=did).first() is None
    # 已删:不存在的 id 返回 404
    assert client.delete(f"/admin/distributions/{did}", auth=admin).status_code == 404
    # 鉴权
    assert client.delete(f"/admin/distributions/{did}").status_code == 401


def test_batch_delete_distributions(client, db_session, admin):
    """批量删除「打开未提交」记录;不存在的 id 跳过,返回实际删除条数。"""
    from datetime import timedelta
    from app.timeutil import now_cn
    s = Survey(slug="bd1", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    now = now_cn().replace(microsecond=0)
    ds = [
        Distribution(survey_id=s.id, channel="tmall", token=f"tk_b{i}",
                     created_at=now, expires_at=now + timedelta(hours=72),
                     bound_fingerprint=f"fp_b{i}", user_code=f"B{i}")
        for i in range(3)
    ]
    db_session.add_all(ds)
    db_session.commit()
    ids = [d.id for d in ds]

    # 删前两条 + 一个不存在的 id（应跳过，删除数=2）
    resp = client.post("/admin/distributions/batch-delete", auth=admin,
                       json={"ids": [ids[0], ids[1], 999999]})
    assert resp.status_code == 200 and resp.json()["deleted"] == 2
    remaining = db_session.query(Distribution).filter(Distribution.survey_id == s.id).all()
    assert {d.id for d in remaining} == {ids[2]}
    # 鉴权
    assert client.post("/admin/distributions/batch-delete", json={"ids": ids}).status_code == 401
