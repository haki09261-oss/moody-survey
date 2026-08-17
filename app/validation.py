from typing import Any, Dict, Iterable, List

from fastapi import HTTPException


def _selected(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def _matches_option(value: str, options: Iterable[str]) -> bool:
    for option in options:
        if value == option:
            return True
        if option.startswith("其他") and value.startswith(option + "："):
            return True
    return False


def _visible(question: Dict[str, Any], answers: Dict[str, Any], by_id: Dict[str, Dict[str, Any]]) -> bool:
    condition = question.get("show_if")
    if not condition:
        return True
    dependency = by_id.get(condition.get("q"))
    if dependency is not None and not _visible(dependency, answers, by_id):
        return False
    actual = _selected(answers.get(condition.get("q")))
    wanted = condition.get("in") or []
    return any(value in wanted for value in actual)


def validate_tier_answers(schema: List[Dict[str, Any]], answers: Dict[str, Any], tier: int) -> None:
    questions = [q for q in schema if not q.get("degree") and int(q.get("tier") or 1) == tier]
    by_id = {q.get("id"): q for q in questions}
    for question in questions:
        if not _visible(question, answers, by_id):
            continue
        qid = question.get("id")
        values = _selected(answers.get(qid))
        if not values and question.get("optional") is not True:
            raise HTTPException(status_code=422, detail=f"missing_answer:{qid}")
        if not values:
            continue
        qtype = question.get("type")
        if qtype == "single" and len(values) != 1:
            raise HTTPException(status_code=422, detail=f"invalid_answer:{qid}")
        maximum = question.get("max")
        if maximum and len(values) > int(maximum):
            raise HTTPException(status_code=422, detail=f"too_many_answers:{qid}")
        if qtype in ("single", "multi"):
            options = question.get("options") or []
            if any(not _matches_option(value, options) for value in values):
                raise HTTPException(status_code=422, detail=f"invalid_option:{qid}")
            other_max = int(question.get("other_max") or 300)
            for value in values:
                if "：" in value and value.split("：", 1)[0].startswith("其他"):
                    other_text = value.split("：", 1)[1].strip()
                    if not other_text or len(other_text) > other_max:
                        raise HTTPException(status_code=422, detail=f"invalid_other:{qid}")


def validate_degree(schema: List[Dict[str, Any]], answers: Dict[str, Any]) -> None:
    degree_question = next((q for q in schema if q.get("degree")), None)
    if degree_question is None:
        return
    qid = degree_question.get("id")
    value = str(answers.get(qid) or "")
    if value not in (degree_question.get("options") or []):
        raise HTTPException(status_code=422, detail=f"invalid_degree:{qid}")
