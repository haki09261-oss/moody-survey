# app/main.py
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.migrations import (
    ensure_bound_aid_column,
    ensure_cn_time_shift,
    ensure_dist_aid_unique,
    ensure_channel_product_urls_column,
    ensure_bound_ip_column,
    ensure_degree_column,
    ensure_ends_at_column,
    ensure_events_table_v2,
    ensure_schema_slim,
    ensure_new_product_url_column,
    ensure_session_id_column,
    ensure_tier_reached_column,
    ensure_user_code_column,
)
import app.models  # noqa: F401  注册所有模型
from app.routers import admin, survey
from app.security import ensure_seed_admin


def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_tier_reached_column(engine)
    ensure_new_product_url_column(engine)
    ensure_channel_product_urls_column(engine)
    ensure_session_id_column(engine)
    ensure_bound_ip_column(engine)
    ensure_bound_aid_column(engine)
    ensure_dist_aid_unique(engine)
    ensure_degree_column(engine)
    ensure_ends_at_column(engine)
    ensure_user_code_column(engine)
    ensure_events_table_v2(engine)
    ensure_schema_slim(engine)
    ensure_cn_time_shift(engine)  # 存量 UTC → 北京时间(+8),标记防重跑
    db = SessionLocal()
    try:
        ensure_seed_admin(db, settings.admin_seed_username, settings.admin_seed_password)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    on_startup()
    yield


app = FastAPI(title="vim_survey_project", lifespan=lifespan)
app.include_router(survey.router)
app.include_router(admin.router)

_web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
_assets_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
mimetypes.add_type("image/webp", ".webp")
app.mount("/static", StaticFiles(directory=_web_dir), name="static")
app.mount("/s/assets", StaticFiles(directory=_assets_dir), name="survey-assets")


@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/static/", "/s/assets/")):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


@app.get("/")
def root(request: Request):
    target = "/s/moody"
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(target, status_code=307)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/admin")
def admin_page():
    # no-cache：后台页改版即生效，不被浏览器缓存卡住
    return FileResponse(
        os.path.join(_web_dir, "admin", "index.html"),
        headers={"Cache-Control": "no-cache"},
    )
