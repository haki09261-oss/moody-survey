# tests/test_distribution.py
from datetime import datetime, timedelta

import pytest

from app.models import Survey, Distribution
from app.distribution import (
    create_distribution,
    validate_token,
    claim_or_check,
    claim_for_device,
)


@pytest.fixture
def survey(db_session):
    s = Survey(slug="t", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    return s


def test_create_distribution_sets_expiry(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    assert dist.token
    assert dist.expires_at > dist.created_at


def test_default_ttl_is_three_days(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms")  # 不传 ttl → 默认 3 天
    delta = (dist.expires_at - dist.created_at).total_seconds()
    assert 71 * 3600 <= delta <= 73 * 3600


def test_validate_token_valid(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    status, found = validate_token(db_session, dist.token, now=datetime.utcnow())
    assert status == "valid"
    assert found.id == dist.id


def test_validate_token_not_found(db_session):
    status, found = validate_token(db_session, "nope", now=datetime.utcnow())
    assert status == "not_found"
    assert found is None


def test_validate_token_expired(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    later = dist.expires_at + timedelta(hours=1)
    status, _ = validate_token(db_session, dist.token, now=later)
    assert status == "expired"


def test_distribution_token_is_md5_of_times_and_device(db_session, survey):
    import hashlib
    dist = create_distribution(db_session, survey.id, "sms")
    expected = hashlib.md5(f"{dist.created_at.isoformat()}||{dist.expires_at.isoformat()}|".encode()).hexdigest()
    assert dist.token == expected


def test_claim_token_derives_from_device(db_session, survey):
    # 通用链接领取：token = md5(生成时间 + 设备指纹 + 到期时间)
    import hashlib
    from app.distribution import claim_for_device
    dist = claim_for_device(db_session, survey.id, "sms", "fp-tok", "1.2.3.4", ttl_hours=72)
    expected = hashlib.md5(
        f"{dist.created_at.isoformat()}|fp-tok|{dist.expires_at.isoformat()}|".encode()).hexdigest()
    assert dist.token == expected


def test_batch_distributions_have_unique_tokens(db_session, survey):
    tokens = {create_distribution(db_session, survey.id, "sms").token for _ in range(20)}
    assert len(tokens) == 20  # 同刻批量也不碰撞


def test_claim_or_check_binds_first_device(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    elig, uc = claim_or_check(db_session, dist, "fp-A")
    assert elig == "eligible"
    assert uc and dist.bound_fingerprint == "fp-A" and dist.user_code == uc


def test_claim_or_check_same_device_eligible(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    _, uc1 = claim_or_check(db_session, dist, "fp-A")
    db_session.expire(dist)  # 丢弃内存态，强制从已提交的 DB 行重新加载
    reloaded = db_session.query(Distribution).filter_by(id=dist.id).one()
    elig, uc2 = claim_or_check(db_session, reloaded, "fp-A")
    assert elig == "eligible" and uc2 == uc1


def test_claim_or_check_other_device_ineligible(db_session, survey):
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    claim_or_check(db_session, dist, "fp-A")
    elig, uc = claim_or_check(db_session, dist, "fp-B")
    assert elig == "ineligible" and uc is None


def test_claim_or_check_empty_fingerprint_passes_without_binding(db_session, survey):
    # 空指纹：放行但不绑定（前端始终会带指纹，这是防御性兜底分支）
    dist = create_distribution(db_session, survey.id, "sms", ttl_hours=48)
    elig, uc = claim_or_check(db_session, dist, "")
    assert elig == "eligible"
    assert dist.bound_fingerprint is None and uc is None


def test_claim_for_device_creates_bound_distribution(db_session, survey):
    dist = claim_for_device(db_session, survey.id, "sms", "fp-A", "1.1.1.1", ttl_hours=72)
    assert dist is not None
    assert dist.bound_fingerprint == "fp-A"
    assert dist.bound_ip == "1.1.1.1"
    assert dist.user_code
    delta = (dist.expires_at - dist.created_at).total_seconds()
    assert 71 * 3600 <= delta <= 73 * 3600  # 72h 生命周期


def test_claim_for_device_same_device_returns_same_token(db_session, survey):
    first = claim_for_device(db_session, survey.id, "sms", "fp-A", "1.1.1.1", ttl_hours=72)
    again = claim_for_device(db_session, survey.id, "sms", "fp-A", "2.2.2.2", ttl_hours=72)
    assert again.token == first.token  # 设备优先：换 IP 也拿回同一 token


def test_claim_for_device_same_ip_second_device_rejected(db_session, survey):
    claim_for_device(db_session, survey.id, "sms", "fp-A", "1.1.1.1", ttl_hours=72)
    second = claim_for_device(db_session, survey.id, "sms", "fp-B", "1.1.1.1", ttl_hours=72)
    assert second is None  # 同 IP 已被设备 A 绑定 → 硬拦


def test_claim_for_device_different_ip_gets_new_token(db_session, survey):
    a = claim_for_device(db_session, survey.id, "sms", "fp-A", "1.1.1.1", ttl_hours=72)
    b = claim_for_device(db_session, survey.id, "sms", "fp-B", "2.2.2.2", ttl_hours=72)
    assert b is not None and b.token != a.token


def test_claim_for_device_roamed_device_does_not_free_old_ip(db_session, survey):
    # 设备 A 绑 IP1 后漫游到 IP2 → bound_ip 仍是 IP1（首绑固定）；设备 C 在 IP2 可正常领取
    a = claim_for_device(db_session, survey.id, "sms", "fp-A", "1.1.1.1", ttl_hours=72)
    claim_for_device(db_session, survey.id, "sms", "fp-A", "2.2.2.2", ttl_hours=72)
    db_session.refresh(a)
    assert a.bound_ip == "1.1.1.1"
    c = claim_for_device(db_session, survey.id, "sms", "fp-C", "2.2.2.2", ttl_hours=72)
    assert c is not None and c.token != a.token


def test_claim_for_device_empty_fingerprint_rejected(db_session, survey):
    assert claim_for_device(db_session, survey.id, "sms", "", "1.1.1.1") is None


def test_claim_for_device_fingerprint_scoped_to_survey(db_session, survey):
    # 指纹幂等以 survey 为界：同设备在另一份问卷可领到新 token
    s2 = Survey(slug="t2", title="t2", schema_json=[])
    db_session.add(s2)
    db_session.commit()
    a = claim_for_device(db_session, survey.id, "sms", "fp-A", "1.1.1.1")
    b = claim_for_device(db_session, s2.id, "sms", "fp-A", "1.1.1.1")
    assert b is not None and b.token != a.token


def test_claim_for_device_ip_block_can_be_disabled(db_session, survey, monkeypatch):
    # 生产链路(SNI 透传)拿不到真实客户端 IP,所有人同 IP;开关关掉后不再硬拦
    from app.config import settings
    from app.distribution import claim_for_device
    monkeypatch.setattr(settings, "ip_single_device", False)
    a = claim_for_device(db_session, survey.id, "sms", "fp-nat-a", "172.19.0.1", ttl_hours=72)
    b = claim_for_device(db_session, survey.id, "sms", "fp-nat-b", "172.19.0.1", ttl_hours=72)
    assert a is not None and b is not None and b.token != a.token
    assert b.bound_ip == "172.19.0.1"  # IP 照常记录,只是不作硬拦


def test_tmall_aid_claim_is_idempotent_same_token(db_session, survey):
    a = claim_for_device(db_session, survey.id, "tmall", "fpA", "1.1.1.1", aid="mp_x")
    b = claim_for_device(db_session, survey.id, "tmall", "fpA", "1.1.1.1", aid="mp_x")
    assert a is not None and b is not None
    assert a.id == b.id and a.token == b.token
    assert a.bound_aid == "mp_x"


def test_tmall_same_ip_second_device_allowed_with_aid(db_session, survey):
    # 同 IP、不同 aid（不同人）→ tmall 渠道不再硬拦，各自拿到独立 token
    a = claim_for_device(db_session, survey.id, "tmall", "fpA", "9.9.9.9", aid="mp_a")
    b = claim_for_device(db_session, survey.id, "tmall", "fpB", "9.9.9.9", aid="mp_b")
    assert a is not None and b is not None
    assert a.id != b.id


def test_non_tmall_channel_keeps_ip_hard_block(db_session, survey):
    # 回归：非 tmall 渠道，同 IP 第二设备仍被硬拦（不传 aid）
    a = claim_for_device(db_session, survey.id, "sms", "fpA", "8.8.8.8")
    b = claim_for_device(db_session, survey.id, "sms", "fpB", "8.8.8.8")
    assert a is not None
    assert b is None


def test_tmall_without_aid_falls_back_to_fingerprint_ip(db_session, survey):
    # tmall 渠道但 aid 缺失 → 回退原指纹+IP 口径（同 IP 第二设备被硬拦）
    a = claim_for_device(db_session, survey.id, "tmall", "fpA", "7.7.7.7")
    b = claim_for_device(db_session, survey.id, "tmall", "fpB", "7.7.7.7")
    assert a is not None
    assert b is None


def test_claim_or_check_passes_aid_bound_dist_despite_fingerprint_drift(db_session, survey):
    dist = claim_for_device(db_session, survey.id, "tmall", "fp_old", "1.2.3.4", aid="mp_drift")
    # 重开后指纹漂移成 fp_new
    eligibility, user_code = claim_or_check(db_session, dist, "fp_new")
    assert eligibility == "eligible"
    assert user_code == dist.user_code


def test_claim_or_check_still_enforces_fingerprint_for_non_aid_dist(db_session, survey):
    # 回归：非 aid 绑定（普通指纹绑定）仍按指纹硬校验
    dist = claim_for_device(db_session, survey.id, "sms", "fp_owner", "5.6.7.8")
    eligibility, _ = claim_or_check(db_session, dist, "fp_stranger")
    assert eligibility == "ineligible"
