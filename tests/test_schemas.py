# tests/test_schemas.py
import pytest
from pydantic import ValidationError

from app.schemas import SubmitRequest, SurveyCreate


def test_submit_request_requires_fingerprint():
    with pytest.raises(ValidationError):
        SubmitRequest(answers={"q1": "A"}, elapsed_ms=1000)


def test_submit_request_ok():
    req = SubmitRequest(fingerprint="fp", answers={"q1": "A"}, elapsed_ms=1000, channel="sms")
    assert req.fingerprint == "fp"
    assert req.token is None


def test_survey_create_defaults():
    s = SurveyCreate(slug="x", title="t", schema_json=[])
    assert s.reward_type == "manual"
