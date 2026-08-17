# tests/test_startup.py
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.database import Base
import app.models  # noqa: F401  确保模型已注册到 Base


def test_all_tables_created():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    tables = set(inspect(engine).get_table_names())
    assert {"wj_surveys", "wj_distributions", "wj_submissions", "wj_admin_users", "wj_events"} <= tables


def test_all_tables_and_columns_have_comments():
    # MySQL 共享库(web)里的表必须自带表注释+字段注释,DDL 即文档
    for table in Base.metadata.tables.values():
        assert table.comment, f"{table.name} 缺表注释"
        for col in table.columns:
            assert col.comment, f"{table.name}.{col.name} 缺字段注释"
