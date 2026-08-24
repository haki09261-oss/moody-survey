# app/schemas.py
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SubmitRequest(BaseModel):
    fingerprint: str = Field(min_length=1)
    answers: Dict[str, Any]
    elapsed_ms: int = 0
    channel: str = "unknown"
    token: Optional[str] = None
    device: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


class SubmitResponse(BaseModel):
    redeem_code: str
    status: str
    tier: int = 1
    display_code: str = ""


class UpgradeRequest(BaseModel):
    fingerprint: str = Field(min_length=1)
    answers: Dict[str, Any]
    elapsed_ms: int = 0
    session_id: Optional[str] = None


class UpgradeResponse(BaseModel):
    redeem_code: str
    tier: int
    display_code: str = ""


class TrackEvent(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    props: Optional[Dict[str, Any]] = None
    client_ts: Optional[int] = None  # 兼容旧缓存前端仍会上报；后端已不落库


class TrackRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    fingerprint: Optional[str] = None
    channel: str = "unknown"
    token: Optional[str] = None
    events: List[TrackEvent]


class SurveyCreate(BaseModel):
    slug: str
    title: str
    schema_json: List[Dict[str, Any]]
    reward_type: str = "manual"
    new_product_url: Optional[str] = None
    ends_at: Optional[datetime] = None


class BatchDeleteRequest(BaseModel):
    ids: List[int]


class RedeemRequest(BaseModel):
    staff_name: str = Field(min_length=1, max_length=100)
    note: Optional[str] = Field(default=None, max_length=500)
