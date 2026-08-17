# scripts/migrate_sqlite_to_mysql.py
"""SQLite → MySQL 一次性迁移：只搬 surveys + admin_users（按 slug/username 幂等）。

用法：项目根目录执行（.env 里 SURVEY_DATABASE_URL 须指向 MySQL）
    .venv/bin/python3.11 scripts/migrate_sqlite_to_mysql.py [--sqlite ./survey.db]
"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import Base, engine as mysql_engine  # noqa: E402
from app.models import AdminUser, Survey  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="./survey.db", help="源 SQLite 文件路径")
    args = parser.parse_args()

    if settings.database_url.startswith("sqlite"):
        raise SystemExit("SURVEY_DATABASE_URL 仍指向 SQLite，请先在 .env 配置 MySQL 地址")
    if not Path(args.sqlite).exists():
        raise SystemExit(f"找不到源库 {args.sqlite}")

    # 源库是改名前的旧 SQLite（表名无 wj_ 前缀），用原生 SQL 读；目标走 ORM（wj_*）
    src_engine = create_engine(f"sqlite:///{args.sqlite}")
    dst = sessionmaker(bind=mysql_engine)()

    print("目标:", settings.database_url.split("@")[-1])
    Base.metadata.create_all(bind=mysql_engine)  # wj_* 表不存在则建（幂等）

    import json
    from datetime import datetime

    def _dt(v):
        return datetime.fromisoformat(v) if v else None

    copied = {"surveys": 0, "admin_users": 0}
    with src_engine.connect() as src:
        for r in src.execute(text(
                "SELECT slug, title, schema_json, reward_type, new_product_url,"
                " status, ends_at, created_at FROM surveys")).mappings():
            if dst.query(Survey).filter_by(slug=r["slug"]).first():
                continue
            dst.add(Survey(
                slug=r["slug"], title=r["title"],
                schema_json=json.loads(r["schema_json"]) if isinstance(r["schema_json"], str) else (r["schema_json"] or []),
                reward_type=r["reward_type"], new_product_url=r["new_product_url"],
                status=r["status"], ends_at=_dt(r["ends_at"]), created_at=_dt(r["created_at"]),
            ))
            copied["surveys"] += 1
        for r in src.execute(text(
                "SELECT username, password_hash, role FROM admin_users")).mappings():
            if dst.query(AdminUser).filter_by(username=r["username"]).first():
                continue
            dst.add(AdminUser(username=r["username"], password_hash=r["password_hash"], role=r["role"]))
            copied["admin_users"] += 1
    dst.commit()
    print("迁移完成:", copied)
    dst.close()


if __name__ == "__main__":
    main()
