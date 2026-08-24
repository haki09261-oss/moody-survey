import base64

import pytest

from app.models import Submission, Survey
from app.security import ensure_seed_admin
from scripts.seed_moody import SCHEMA


@pytest.fixture
def moody(db_session):
    survey = Survey(
        slug="moody-current",
        title="moody 用户调研问卷",
        schema_json=SCHEMA,
        status="active",
        new_product_url="https://detail.tmall.com/item.htm?id=1072972797956",
    )
    db_session.add(survey)
    ensure_seed_admin(db_session, "admin", "test-password")
    db_session.commit()
    return survey


def _claim(client, fingerprint, ip):
    response = client.get(
        "/api/s/moody-current?c=test&fp=" + fingerprint,
        headers={"CF-Connecting-IP": ip},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_status"] == "claim"
    return data["token"]


def _only_answers(degree="525"):
    return {
        "q1": ["日常上班/上学"],
        "q2": ["戴久了干涩"],
        "q3": "只戴美瞳",
        "q4_only": ["美瞳的舒适度足够，没有尝试透明片的动力"],
        "q5_only": "愿意",
        "q6_only": "30-40元",
        "q_degree": degree,
    }


def _full_answers(degree="575"):
    return {
        "q4_cycle": ["日抛"],
        "q5_scene": ["长时间通勤（如旅行、出差途中等）"],
        "q6_purchase": "经常买",
        "q7_products": ["moody 目怡蓝 M 系列"],
        "q8_purchase_reason": ["被“新手友好”的卖点打动"],
        "q9_other_brands": ["只买 moody 的透明片"],
        "q10_satisfied": ["不磨眼"],
        "q11_price": "30-40元",
        "q12_premium": ["其他：愿意为专业服务付费"],
        "q13_channel": ["小红书"],
        "q14_content": ["测评类"],
        "q_degree": degree,
    }


def test_current_schema_contains_latest_requested_content():
    by_id = {question["id"]: question for question in SCHEMA}
    assert "长时间通勤（如旅行、出差途中等）" in by_id["q5_scene"]["options"]
    assert "525" in by_id["q_degree"]["options"]
    assert "535" not in by_id["q_degree"]["options"]
    assert by_id["q12_premium"]["other_max"] == 100
    assert "moody 目怡蓝 M 系列" in by_id["q7_products"]["options"]
    assert "被“高透氧”“泪循环”等产品参数/功能打动" in by_id["q8_purchase_reason"]["options"]


def test_moody_uses_original_visual_layout_with_fastapi_adapter(client, moody):
    page = client.get("/s/moody")
    assert page.status_code == 200
    assert "universal-survey-background.webp" in page.text
    assert "画布保持原始比例并在短屏中上下居中裁切" in page.text
    assert "--safe-top:env(safe-area-inset-top,0px)" in page.text
    assert "--usable-vh:calc(100dvh - var(--safe-top) - var(--safe-bottom))" in page.text
    assert "width:var(--usable-vw);max-width:none;height:calc(var(--usable-vw) * 923 / 426)" in page.text
    assert "width:var(--usable-vw);height:calc(var(--usable-vw) * 1847 / 852)" in page.text
    assert "transform:translateY(calc((var(--usable-vh) - 100%) / 2))" in page.text
    assert "body{display:block;padding:var(--safe-top)" in page.text
    assert "var(--usable-vh) * .9215" in page.text
    assert "background:linear-gradient(180deg,#ff963c,#ff6718)!important" in page.text
    assert "@media(max-width:768px) and (min-aspect-ratio:1/2)" in page.text
    assert "bottom:max(16.2%,calc(50% - 40dvh + var(--safe-top) + var(--safe-bottom)))" in page.text
    assert "function resetViewportScroll()" in page.text
    assert ".shell.q6a .options:not(.q7b1):not(.q15):not(.q16)>.option:not(.placeholder){height:52px!important;min-height:52px!important;flex:0 0 52px!important}" in page.text
    assert "container-type:inline-size" in page.text
    assert "font-size:clamp(14px,5.6cqw,35px)" in page.text
    assert "white-space:nowrap;user-select:all" in page.text
    assert '<script src="survey-submit.js?v=20260805-3"></script>' in page.text

    adapter = client.get("/s/survey-submit.js")
    assert adapter.status_code == 200
    assert adapter.headers["content-type"].startswith("application/javascript")
    assert 'await api(`/s/${SLUG}/submit`' in adapter.text
    assert 'await api(`/s/${SLUG}/upgrade`' in adapter.text
    assert "打开淘宝 App？" in adapter.text
    assert "tbopen://m.taobao.com/tbopen/index.html" in adapter.text
    assert "location.assign(productUrl)" in adapter.text

    artwork = client.get("/s/assets/universal-survey-background.webp")
    assert artwork.status_code == 200
    assert artwork.headers["content-type"] == "image/webp"
    assert "max-age=604800" in artwork.headers["cache-control"]


def test_only_beauty_path_returns_two_pack_code(client, db_session, moody):
    token = _claim(client, "fp-only", "10.20.0.1")
    response = client.post("/s/moody-current/submit", headers={"CF-Connecting-IP": "10.20.0.1"}, json={
        "fingerprint": "fp-only", "token": token, "channel": "test",
        "elapsed_ms": 20000, "answers": _only_answers(),
    })
    assert response.status_code == 200
    assert response.json()["display_code"].endswith("02-525")
    assert response.json()["status"] == "new"
    reopen = client.get(
        f"/api/s/moody-current?c=test&fp=fp-only&t={token}",
        headers={"CF-Connecting-IP": "10.20.0.1"},
    ).json()
    assert reopen["token_status"] == "submitted_self"
    assert reopen["can_resume_tier2"] is False
    assert reopen["submission_status"] == "new"


def test_both_wear_path_stays_in_progress_then_returns_ten_pack(client, db_session, moody):
    token = _claim(client, "fp-full", "10.20.0.2")
    first = client.post("/s/moody-current/submit", headers={"CF-Connecting-IP": "10.20.0.2"}, json={
        "fingerprint": "fp-full", "token": token, "channel": "test", "elapsed_ms": 9000,
        "answers": {"q1": ["日常上班/上学"], "q2": ["戴久了干涩"], "q3": "两种都戴，戴透明片更多"},
    })
    assert first.status_code == 200
    assert first.json()["status"] == "in_progress"
    reopen = client.get(
        f"/api/s/moody-current?c=test&fp=fp-full&t={token}",
        headers={"CF-Connecting-IP": "10.20.0.2"},
    ).json()
    assert reopen["can_resume_tier2"] is True

    final = client.post("/s/moody-current/upgrade", headers={"CF-Connecting-IP": "10.20.0.2"}, json={
        "fingerprint": "fp-full", "elapsed_ms": 65000, "answers": _full_answers(),
    })
    assert final.status_code == 200
    assert final.json()["display_code"].endswith("10-575")
    submission = db_session.query(Submission).filter_by(fingerprint="fp-full").one()
    assert submission.status == "new"
    assert submission.tier_reached == 2


def test_same_ip_cannot_claim_for_second_device(client, moody):
    _claim(client, "fp-ip-first", "10.20.0.3")
    second = client.get(
        "/api/s/moody-current?c=test&fp=fp-ip-second",
        headers={"CF-Connecting-IP": "10.20.0.3"},
    )
    assert second.status_code == 200
    assert second.json()["token_status"] == "ineligible"


def test_too_fast_only_path_is_flagged(client, moody):
    token = _claim(client, "fp-fast-current", "10.20.0.4")
    response = client.post("/s/moody-current/submit", headers={"CF-Connecting-IP": "10.20.0.4"}, json={
        "fingerprint": "fp-fast-current", "token": token, "elapsed_ms": 4000,
        "answers": _only_answers(),
    })
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_submission"


def test_same_option_position_pattern_is_rejected(client, moody):
    token = _claim(client, "fp-uniform-current", "10.20.0.7")
    answers = {
        "q1": ["日常上班/上学"],
        "q2": ["戴久了干涩"],
        "q3": "只戴美瞳",
        "q4_only": ["和美瞳相比，没有修饰眼睛、完善妆容的功能"],
        "q5_only": "愿意",
        "q6_only": "20元及以下",
        "q_degree": "525",
    }
    response = client.post("/s/moody-current/submit", headers={"CF-Connecting-IP": "10.20.0.7"}, json={
        "fingerprint": "fp-uniform-current", "token": token, "elapsed_ms": 30000,
        "answers": answers,
    })
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_submission"


def test_q12_other_is_limited_server_side(client, moody):
    token = _claim(client, "fp-other-long", "10.20.0.5")
    client.post("/s/moody-current/submit", headers={"CF-Connecting-IP": "10.20.0.5"}, json={
        "fingerprint": "fp-other-long", "token": token, "elapsed_ms": 9000,
        "answers": {"q1": ["日常上班/上学"], "q2": ["戴久了干涩"], "q3": "两种都戴，戴美瞳更多"},
    })
    answers = _full_answers()
    answers["q12_premium"] = ["其他：" + ("字" * 101)]
    response = client.post("/s/moody-current/upgrade", headers={"CF-Connecting-IP": "10.20.0.5"}, json={
        "fingerprint": "fp-other-long", "elapsed_ms": 65000, "answers": answers,
    })
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_other:q12_premium"


def test_admin_can_find_and_idempotently_redeem_code(client, moody):
    token = _claim(client, "fp-redeem", "10.20.0.6")
    created = client.post("/s/moody-current/submit", headers={"CF-Connecting-IP": "10.20.0.6"}, json={
        "fingerprint": "fp-redeem", "token": token, "elapsed_ms": 20000,
        "answers": _only_answers("475"),
    }).json()
    auth = "Basic " + base64.b64encode(b"admin:test-password").decode()
    headers = {"Authorization": auth}
    found = client.get("/admin/submissions", params={"code": created["display_code"]}, headers=headers)
    assert found.status_code == 200
    assert len(found.json()["items"]) == 1
    submission_id = found.json()["items"][0]["id"]
    first = client.post(
        f"/admin/submissions/{submission_id}/redeem",
        headers=headers,
        json={"staff_name": "现场同事", "note": "上海快闪店"},
    )
    second = client.post(f"/admin/submissions/{submission_id}/redeem", headers=headers)
    assert first.json() == {"id": submission_id, "status": "redeemed", "already_redeemed": False}
    assert second.json() == {"id": submission_id, "status": "redeemed", "already_redeemed": True}
    redeemed = client.get("/admin/submissions", params={"code": created["display_code"]}, headers=headers)
    assert redeemed.json()["items"][0]["redeemed_by"] == "现场同事"
    assert redeemed.json()["items"][0]["redeemed_at"] is not None
