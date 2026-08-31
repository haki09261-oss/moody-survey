# tests/test_migrations.py
from sqlalchemy import create_engine, inspect, text

from app.migrations import (
    ensure_ends_at_column,
    ensure_moody_activity_window,
    ensure_new_product_url_column,
    ensure_starts_at_column,
    ensure_tier_reached_column,
    ensure_user_code_column,
)


def _legacy_engine():
    """构造一个没有 tier_reached 列的旧版 submissions 表。"""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE wj_submissions ("
            "id INTEGER PRIMARY KEY, redeem_code VARCHAR)"
        ))
    return engine


def _legacy_survey_engine():
    """构造一个没有 new_product_url 列的旧版 surveys 表。"""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE wj_surveys ("
            "id INTEGER PRIMARY KEY, slug VARCHAR)"
        ))
    return engine


def _legacy_distribution_engine():
    """构造一个没有 user_code 列的旧版 distributions 表。"""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE wj_distributions ("
            "id INTEGER PRIMARY KEY, token VARCHAR)"
        ))
    return engine


def _columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("wj_submissions")}


def _survey_columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("wj_surveys")}


def _distribution_columns(engine):
    return {c["name"] for c in inspect(engine).get_columns("wj_distributions")}


def test_migration_adds_missing_column():
    engine = _legacy_engine()
    assert "tier_reached" not in _columns(engine)
    ensure_tier_reached_column(engine)
    assert "tier_reached" in _columns(engine)


def test_migration_is_idempotent():
    engine = _legacy_engine()
    ensure_tier_reached_column(engine)
    ensure_tier_reached_column(engine)  # 第二次不应报错
    assert "tier_reached" in _columns(engine)


def test_migration_noop_when_no_table():
    engine = create_engine("sqlite://")  # 完全没有 submissions 表
    ensure_tier_reached_column(engine)  # 不应抛异常


def test_new_product_url_migration_adds_missing_column():
    engine = _legacy_survey_engine()
    assert "new_product_url" not in _survey_columns(engine)
    ensure_new_product_url_column(engine)
    assert "new_product_url" in _survey_columns(engine)


def test_new_product_url_migration_is_idempotent():
    engine = _legacy_survey_engine()
    ensure_new_product_url_column(engine)
    ensure_new_product_url_column(engine)  # 第二次不应报错
    assert "new_product_url" in _survey_columns(engine)


def test_new_product_url_migration_noop_when_no_table():
    engine = create_engine("sqlite://")  # 完全没有 surveys 表
    ensure_new_product_url_column(engine)  # 不应抛异常


def test_survey_ends_at_migration_adds_missing_column():
    engine = _legacy_survey_engine()
    assert "ends_at" not in _survey_columns(engine)
    ensure_ends_at_column(engine)
    assert "ends_at" in _survey_columns(engine)


def test_survey_starts_at_migration_adds_missing_column_and_is_idempotent():
    engine = _legacy_survey_engine()
    assert "starts_at" not in _survey_columns(engine)
    ensure_starts_at_column(engine)
    ensure_starts_at_column(engine)
    assert "starts_at" in _survey_columns(engine)


def test_moody_activity_window_updates_existing_survey_only():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE wj_surveys ("
            "id INTEGER PRIMARY KEY, slug VARCHAR, starts_at DATETIME, ends_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO wj_surveys (id, slug) VALUES (1, 'moody'), (2, 'other')"))
    ensure_moody_activity_window(engine)
    with engine.connect() as conn:
        moody = conn.execute(text(
            "SELECT starts_at, ends_at FROM wj_surveys WHERE slug = 'moody'"
        )).one()
        other = conn.execute(text(
            "SELECT starts_at, ends_at FROM wj_surveys WHERE slug = 'other'"
        )).one()
    assert str(moody.starts_at).startswith("2026-08-28 10:00:00")
    assert str(moody.ends_at).startswith("2026-09-30 23:59:59")
    assert other.starts_at is None and other.ends_at is None


def test_session_id_migration_adds_missing_column():
    from app.migrations import ensure_session_id_column
    engine = _legacy_engine()  # submissions 表无 session_id
    assert "session_id" not in _columns(engine)
    ensure_session_id_column(engine)
    assert "session_id" in _columns(engine)


def test_degree_migration_adds_missing_column():
    from app.migrations import ensure_degree_column
    engine = _legacy_engine()
    assert "degree" not in _columns(engine)
    ensure_degree_column(engine)
    assert "degree" in _columns(engine)


def test_distribution_user_code_migration_adds_missing_column():
    engine = _legacy_distribution_engine()
    assert "user_code" not in _distribution_columns(engine)
    ensure_user_code_column(engine)
    assert "user_code" in _distribution_columns(engine)


def test_ensure_ends_at_column_adds_when_missing():
    from sqlalchemy import create_engine, inspect, text
    from app.migrations import ensure_ends_at_column
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE wj_surveys (id INTEGER PRIMARY KEY, slug VARCHAR)"))
    ensure_ends_at_column(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("wj_surveys")}
    assert "ends_at" in cols
    ensure_ends_at_column(engine)  # 幂等


def test_ensure_user_code_column_adds_when_missing():
    from sqlalchemy import create_engine, inspect, text
    from app.migrations import ensure_user_code_column
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE wj_distributions (id INTEGER PRIMARY KEY, token VARCHAR)"))
    ensure_user_code_column(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("wj_distributions")}
    assert "user_code" in cols
    ensure_user_code_column(engine)  # 幂等


def test_distribution_bound_ip_migration_adds_missing_column():
    from app.migrations import ensure_bound_ip_column
    engine = _legacy_distribution_engine()
    assert "bound_ip" not in _distribution_columns(engine)
    ensure_bound_ip_column(engine)
    assert "bound_ip" in _distribution_columns(engine)
    ensure_bound_ip_column(engine)  # 幂等


def test_events_table_v2_recreates_old_shape():
    from sqlalchemy import create_engine, inspect, text
    from app.migrations import ensure_events_table_v2
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE wj_events (id INTEGER PRIMARY KEY, name VARCHAR, props TEXT, client_ts INTEGER)"))
    ensure_events_table_v2(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("wj_events")}
    assert {"event_type", "question_id", "option_value", "dwell_seconds"} <= cols
    assert not ({"name", "props", "client_ts", "dwell_ms"} & cols)  # 旧列全部移除
    ensure_events_table_v2(engine)  # 幂等


def test_distribution_bound_aid_migration_adds_missing_column():
    from app.migrations import ensure_bound_aid_column
    engine = _legacy_distribution_engine()
    assert "bound_aid" not in _distribution_columns(engine)
    ensure_bound_aid_column(engine)
    assert "bound_aid" in _distribution_columns(engine)
    ensure_bound_aid_column(engine)  # 幂等


def test_schema_slim_drops_dead_table_and_columns():
    from sqlalchemy import create_engine, inspect, text
    from app.migrations import ensure_schema_slim
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE wj_redemptions (id INTEGER PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE wj_distributions (id INTEGER PRIMARY KEY, token VARCHAR, "
            "target_hint VARCHAR, used BOOLEAN, used_at DATETIME, open_count INTEGER, "
            "open_fingerprints TEXT, open_ips TEXT)"))
        conn.execute(text("CREATE TABLE wj_submissions (id INTEGER PRIMARY KEY, phone VARCHAR)"))
        conn.execute(text("CREATE TABLE wj_events (id INTEGER PRIMARY KEY, ua TEXT)"))
    ensure_schema_slim(engine)
    insp = inspect(engine)
    assert "wj_redemptions" not in insp.get_table_names()
    dist_cols = {c["name"] for c in insp.get_columns("wj_distributions")}
    assert not ({"target_hint", "used", "used_at", "open_count", "open_fingerprints", "open_ips"} & dist_cols)
    assert "phone" not in {c["name"] for c in insp.get_columns("wj_submissions")}
    assert "ua" not in {c["name"] for c in insp.get_columns("wj_events")}
    ensure_schema_slim(engine)  # 幂等
