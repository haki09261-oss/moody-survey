# app/migrations.py
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _ensure_column(engine: Engine, table: str, column: str, ddl_type: str) -> None:
    """旧库补列：table 缺 column 则 ALTER 添加；新库为幂等空操作。

    ddl_type 是列定义片段，如 "INTEGER DEFAULT 1" 或 "VARCHAR(64)"（MySQL 要求 VARCHAR 带长度）.
    """
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns(table)}
    if column in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def ensure_tier_reached_column(engine: Engine) -> None:
    """wj_submissions 表若缺 tier_reached 则补列（默认 1）。"""
    _ensure_column(engine, "wj_submissions", "tier_reached", "INTEGER DEFAULT 1")


def ensure_new_product_url_column(engine: Engine) -> None:
    """wj_surveys 表若缺 new_product_url 则补列（可空）。"""
    _ensure_column(engine, "wj_surveys", "new_product_url", "VARCHAR(512)")


def ensure_channel_product_urls_column(engine: Engine) -> None:
    """wj_surveys 表若缺 channel_product_urls 则补列（按渠道配兑奖链接 JSON，可空）。"""
    # MySQL JSON / sqlite 用 JSON(底层 TEXT);_ensure_column 传 DDL 片段
    ddl = "JSON" if engine.dialect.name == "mysql" else "JSON"
    _ensure_column(engine, "wj_surveys", "channel_product_urls", ddl)


def ensure_session_id_column(engine: Engine) -> None:
    """wj_submissions 表若缺 session_id 则补列（关联埋点会话）。"""
    _ensure_column(engine, "wj_submissions", "session_id", "VARCHAR(64)")


def ensure_degree_column(engine: Engine) -> None:
    """wj_submissions 表若缺 degree 则补列（眼睛度数，默认 0）。"""
    _ensure_column(engine, "wj_submissions", "degree", "INTEGER DEFAULT 0")


def ensure_ends_at_column(engine: Engine) -> None:
    """wj_surveys 表若缺 ends_at 则补列（活动结束时间，可空）。"""
    _ensure_column(engine, "wj_surveys", "ends_at", "DATETIME")


def ensure_user_code_column(engine: Engine) -> None:
    """wj_distributions 表若缺 user_code 则补列（首开绑定派生码，可空）。"""
    _ensure_column(engine, "wj_distributions", "user_code", "VARCHAR(32)")


def ensure_bound_ip_column(engine: Engine) -> None:
    """wj_distributions 表若缺 bound_ip 则补列（首绑设备时的 IP，可空）。"""
    _ensure_column(engine, "wj_distributions", "bound_ip", "VARCHAR(64)")


def ensure_bound_aid_column(engine: Engine) -> None:
    """wj_distributions 表若缺 bound_aid 则补列（tmall 小程序匿名 aid，可空）。"""
    _ensure_column(engine, "wj_distributions", "bound_aid", "VARCHAR(128)")


def ensure_dist_aid_unique(engine: Engine) -> None:
    """wj_distributions 加 (survey_id, bound_aid) 唯一约束，杜绝并发同 aid 重复领取。
    先把历史重复的 bound_aid 置空(保留最小 id，不删数据)再加索引，避免已有重复导致建索引失败。
    仅 MySQL 执行；sqlite(测试)由 create_all 直接带上约束。
    """
    if engine.dialect.name != "mysql":
        return
    inspector = inspect(engine)
    if "wj_distributions" not in inspector.get_table_names():
        return
    existing = {idx.get("name") for idx in inspector.get_indexes("wj_distributions")}
    if "uq_wj_dist_survey_aid" in existing:
        return
    try:
        with engine.begin() as conn:
            # 1) 历史重复 bound_aid：保留最小 id，其余置 NULL（解绑、不删行）
            conn.execute(text(
                "UPDATE wj_distributions d "
                "JOIN (SELECT survey_id, bound_aid, MIN(id) AS keep_id FROM wj_distributions "
                "      WHERE bound_aid IS NOT NULL GROUP BY survey_id, bound_aid HAVING COUNT(*) > 1) g "
                "  ON d.survey_id = g.survey_id AND d.bound_aid = g.bound_aid AND d.id <> g.keep_id "
                "SET d.bound_aid = NULL"
            ))
            # 2) 加唯一约束（NULL 不互斥，非 tmall 分发不受影响）
            conn.execute(text(
                "ALTER TABLE wj_distributions ADD CONSTRAINT uq_wj_dist_survey_aid UNIQUE (survey_id, bound_aid)"
            ))
    except Exception as e:
        # 加约束失败不拖垮启动；运行时 claim_for_device 仍有「先查 + IntegrityError 兜底」
        print("[migration] ensure_dist_aid_unique skipped:", e)


def ensure_cn_time_shift(engine: Engine) -> None:
    """一次性把存量 UTC 时间 +8 小时校正为北京时间(配合全站改存北京时间 now_cn)。

    用 wj_meta 表的 tz_shifted_cn 标记防重跑(避免再次启动又 +8)。
    仅 MySQL 执行;sqlite(测试)无存量数据、由 create_all 直接建表,跳过。
    """
    if engine.dialect.name != "mysql":
        return
    inspector = inspect(engine)
    names = set(inspector.get_table_names())
    if "wj_surveys" not in names:
        return
    try:
        # 1) 标记表(DDL,自动提交)
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE IF NOT EXISTS wj_meta "
                "(k VARCHAR(64) PRIMARY KEY, v VARCHAR(255)) COMMENT '系统元信息:迁移标记'"
            ))
        # 2) 检查标记 + 迁移 + 写标记(同一事务,失败整体回滚,绝不半 +8)
        with engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM wj_meta WHERE k='tz_shifted_cn'")).first():
                return
            shifts = [
                ("wj_surveys", "created_at"), ("wj_surveys", "ends_at"),
                ("wj_distributions", "created_at"), ("wj_distributions", "expires_at"),
                ("wj_submissions", "created_at"),
                ("wj_events", "created_at"),
            ]
            for table, col in shifts:
                if table in names:
                    conn.execute(text(
                        f"UPDATE {table} SET {col} = {col} + INTERVAL 8 HOUR WHERE {col} IS NOT NULL"
                    ))
            conn.execute(text("INSERT INTO wj_meta (k, v) VALUES ('tz_shifted_cn', NOW())"))
    except Exception as e:
        # 失败不拖垮启动(已用事务保证不会半迁移);下次启动重试
        print("[migration] ensure_cn_time_shift skipped:", e)


def ensure_events_table_v2(engine: Engine) -> None:
    """wj_events v2：question_id / option_value / dwell_seconds(秒) 取代 props / client_ts / dwell_ms。

    旧结构（含 name/props/client_ts/dwell_ms 任一列）直接重建为新表——
    埋点是分析数据且尚在测试期，重建换取全量列注释与干净结构。
    """
    inspector = inspect(engine)
    if "wj_events" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("wj_events")}
    if {"name", "props", "client_ts", "dwell_ms"} & columns:
        from app.models import Event
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE wj_events"))
        Event.__table__.create(bind=engine)
        return
    # v2 表补 question_title（题目内容快照）
    ddl = "VARCHAR(255)"
    if engine.dialect.name == "mysql":
        ddl += " COMMENT '题目内容：落库时从问卷结构快照，便于直接查表阅读' AFTER question_id"
    _ensure_column(engine, "wj_events", "question_title", ddl)


def _drop_column(engine: Engine, table: str, column: str) -> None:
    """表存在且列存在则删除（MySQL 8 / SQLite 3.35+ 均支持 DROP COLUMN）。"""
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    if column not in {c["name"] for c in inspector.get_columns(table)}:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))


def ensure_schema_slim(engine: Engine) -> None:
    """瘦身迁移（幂等）：删死表 wj_redemptions 与各表冗余列。

    - wj_redemptions：零代码引用的死表
    - wj_distributions：target_hint(功能已下线)、used/used_at(与提交记录重复)、
      open_count/open_fingerprints/open_ips(与 wj_events 重复)
    - wj_submissions.phone：前端从不收集，恒空
    - wj_events.ua：每行重复存大文本，设备信息在提交记录里
    """
    inspector = inspect(engine)
    if "wj_redemptions" in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE wj_redemptions"))
    for col in ("target_hint", "used", "used_at", "open_count", "open_fingerprints", "open_ips"):
        _drop_column(engine, "wj_distributions", col)
    _drop_column(engine, "wj_submissions", "phone")
    _drop_column(engine, "wj_events", "ua")
    # 列注释刷新（语义随埋点演进；仅 MySQL，SQLite 无列注释）
    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE wj_events MODIFY option_value TEXT "
                "COMMENT '内容：回答问题=选项/答案(多选每选项一行)；页面浏览=落地页类型(答题页/无资格页/兑奖码页等)'"
            ))
            conn.execute(text(
                "ALTER TABLE wj_events MODIFY dwell_seconds FLOAT "
                "COMMENT '用户停留时长（秒）：页面离开=会话总停留；下一题/上一题/提交问卷/继续作答=刚离开那道题的停留；填写度数=度数框耗时；点击去兑奖=看码页到点击的耗时'"
            ))
