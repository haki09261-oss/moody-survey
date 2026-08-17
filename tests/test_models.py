# tests/test_models.py
from app.models import Survey


def test_create_survey(db_session):
    survey = Survey(slug="spring-2026", title="春季满意度", schema_json=[
        {"id": "q1", "type": "single", "title": "满意吗", "options": ["满意", "一般"]}
    ])
    db_session.add(survey)
    db_session.commit()

    fetched = db_session.query(Survey).filter_by(slug="spring-2026").one()
    assert fetched.id is not None
    assert fetched.status == "active"
    assert fetched.schema_json[0]["id"] == "q1"


def test_survey_has_ends_at_column(db_session):
    from datetime import datetime
    from app.models import Survey
    s = Survey(slug="ea", title="t", schema_json=[], ends_at=datetime(2030, 1, 1))
    db_session.add(s)
    db_session.commit()
    assert db_session.query(Survey).filter_by(slug="ea").one().ends_at.year == 2030


def test_distribution_has_user_code_column(db_session):
    from app.models import Survey, Distribution
    from datetime import datetime, timedelta
    s = Survey(slug="uc", title="t", schema_json=[])
    db_session.add(s)
    db_session.commit()
    d = Distribution(survey_id=s.id, channel="sms", token="tk-uc",
                     created_at=datetime.utcnow(), expires_at=datetime.utcnow() + timedelta(hours=1),
                     user_code="ABCD1234")
    db_session.add(d)
    db_session.commit()
    assert db_session.query(Distribution).filter_by(token="tk-uc").one().user_code == "ABCD1234"
