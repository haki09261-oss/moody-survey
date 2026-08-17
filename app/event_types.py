# app/event_types.py
"""埋点事件类型：前端上报英文代码（接口稳定），落库统一转中文（直接查表可读）。"""

EVENT_TYPE_CN = {
    "page_view": "页面浏览",
    "page_leave": "页面离开",
    "question_view": "浏览问题",
    "answer": "回答问题",
    "nav_next": "下一题",
    "nav_prev": "上一题",
    "submit": "提交问卷",
    "continue": "继续作答",
    "upgrade": "升级提交",
    "redeem_tip_view": "弹出兑奖提示",
    "redeem_click": "点击去兑奖",
    "redeem_fallback": "兑奖跳转兜底",
    "degree_view": "弹出度数框",
    "degree_done": "填写度数",
    "reward_view": "弹出奖励说明",
    "copy_code": "复制兑换码",
    "rules_view": "查看活动规则",
}

PAGE_VIEW = EVENT_TYPE_CN["page_view"]
PAGE_LEAVE = EVENT_TYPE_CN["page_leave"]
QUESTION_VIEW = EVENT_TYPE_CN["question_view"]
ANSWER = EVENT_TYPE_CN["answer"]
NAV_NEXT = EVENT_TYPE_CN["nav_next"]
NAV_PREV = EVENT_TYPE_CN["nav_prev"]
SUBMIT = EVENT_TYPE_CN["submit"]
CONTINUE = EVENT_TYPE_CN["continue"]
CLICK_TYPES = [EVENT_TYPE_CN[k] for k in
               ("nav_next", "nav_prev", "continue", "submit", "upgrade", "redeem_click")]
# 这些事件的 dwell_seconds 表示"刚离开那道题"的停留，按 question_id 汇总即每题停留
QUESTION_DWELL_TYPES = {NAV_NEXT, NAV_PREV, SUBMIT, CONTINUE}


def to_cn(name: str) -> str:
    """英文事件代码 → 中文事件类型；未知代码原样保留。"""
    return EVENT_TYPE_CN.get(name, name)
