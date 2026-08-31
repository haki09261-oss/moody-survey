"""写入当前 moody 透明片调研问卷。

题目按业务路径拆为两层：
- Tier 1：所有用户的前五题，以及「只戴美瞳」用户的三道追加题；完成后发 M 系列 2 片装。
- Tier 2：两种都戴用户的透明片完整调研；完成后发 M 系列 10 片装。

重复执行为幂等 upsert，不会删除已有答卷。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.campaigns import MOODY_ENDS_AT as ENDS_AT, MOODY_STARTS_AT as STARTS_AT
from app.database import Base, SessionLocal, engine
import app.models  # noqa: F401 - 注册全部 SQLAlchemy 模型
from app.migrations import ensure_ends_at_column, ensure_starts_at_column
from app.models import Survey


SLUG = "moody"
TITLE = "moody 用户调研问卷"
NEW_PRODUCT_URL = "https://detail.tmall.com/item.htm?id=1072972797956"
CHANNEL_PRODUCT_URLS = {"tmall": NEW_PRODUCT_URL}

ONLY_BEAUTY = "只戴美瞳"
BOTH_MORE_BEAUTY = "两种都戴，戴美瞳更多"
BOTH_MORE_CLEAR = "两种都戴，戴透明片更多"

PURCHASE_REASONS = [
    "大促期间凑单",
    "刷到博主种草帖后买来尝试",
    "出于对 moody 美瞳的喜爱及品牌信任",
    "被“新手友好”的卖点打动",
    "被“水润”“舒适”等佩戴感受卖点打动",
    "被“高透氧”“泪循环”等产品参数/功能打动",
    "价格划算",
    "被包装吸引",
]

LAPSED_PURCHASE_REASONS = [
    "出于对 moody 美瞳的喜爱及品牌信任",
    "刷到博主种草帖后买来尝试",
    "被“新手友好”的卖点打动",
    "被“水润”“舒适”等佩戴感受卖点打动",
    "被“高透氧”“泪循环”等产品参数/功能打动",
    "大促期间凑单",
    "价格划算",
    "被包装吸引",
]

BRANDS_BOUGHT = [
    "强生安视优", "博士伦", "拉拜诗", "爱尔康", "库博光学", "欧舒天",
    "目立康 Miru", "海昌", "海俪恩", "卫康", "优瞳", "可啦啦",
    "只买 moody 的透明片", "其他",
]

BRANDS_DAILY = [
    "强生安视优", "博士伦", "拉拜诗", "小桔片", "爱尔康", "小蓝片",
    "库博光学", "欧舒天", "目立康 Miru", "海昌", "海俪恩", "卫康",
    "优瞳", "可啦啦", "其他",
]

DEGREES = [
    "100", "125", "150", "175", "200", "225", "250", "275", "300", "325",
    "350", "375", "400", "425", "450", "475", "500", "525", "550", "575",
    "600", "650", "700", "750", "800", "850", "900", "950", "1000",
]

SCHEMA = [
    {"id": "q1", "type": "multi", "tier": 1,
     "title": "你通常会在什么时候戴美瞳？",
     "options": ["日常上班/上学", "逛街/聚会/约会", "运动/健身/户外", "旅行/拍照", "不想戴框架镜的时候几乎都会戴美瞳"]},
    {"id": "q2", "type": "multi", "tier": 1, "max": 3,
     "title": "你戴美瞳时，最常遇到哪些不适？",
     "options": ["戴久了干涩", "有异物感/磨眼", "眼睛容易有红血丝", "视物模糊", "久看屏幕后眼睛酸胀", "镜片容易滑片", "基本没有不适"]},
    {"id": "q3_product_name_interest", "type": "multi", "tier": 1, "max": 3,
     "title": "以下哪种类型的产品名最能引起你对透明隐形眼镜的购买兴趣？",
     "options": [
         "佩戴感受型：欧舒适、舒润、水感",
         "功能直述型：防蓝光、防干眼",
         "功能概述型：双护、清氧清、水航线",
         "技术工艺型：水梯度、泪循环",
         "参数特点型：薄润、003",
         "字母系列型：M系列（Moist）、B系列（Basic）",
         "使用场景型：每日U新、睛靓每日",
         "口语昵称型：小粉片、锁水片、海洋片",
     ]},
    {"id": "q4_product_feature_interest", "type": "multi", "tier": 1, "max": 3,
     "title": "假设以下说法均经过验证，并用于同一款隐形眼镜。请问以下哪些产品特点最能吸引你进一步了解或购买？",
     "options": [
         "恢复眼睛自身水润力",
         "延长泪膜破裂时间，让眼睛多2秒水润",
         "干眼适用，降低眼表炎症发生可能性",
         "清除自由基，对抗眼表氧化",
         "提高泪膜稳定性，泪液更充盈",
         "降低戴镜压力，提高戴镜水润感",
     ]},
    {"id": "q3", "type": "single", "tier": 1,
     "title": "你平时戴美瞳和透明片的情况是？",
     "options": [ONLY_BEAUTY, BOTH_MORE_BEAUTY, BOTH_MORE_CLEAR]},

    {"id": "q4_only", "type": "multi", "tier": 1,
     "title": "你不戴透明片的原因是？",
     "options": ["和美瞳相比，没有修饰眼睛、完善妆容的功能", "美瞳的舒适度足够，没有尝试透明片的动力", "不清楚透明片和美瞳除有无花纹外有什么区别"],
     "show_if": {"q": "q3", "in": [ONLY_BEAUTY]}},
    {"id": "q5_only", "type": "single", "tier": 1,
     "title": "如 moody 提供免费的透明片试用，你是否愿意尝试佩戴？",
     "options": ["愿意", "不愿意"], "show_if": {"q": "q3", "in": [ONLY_BEAUTY]}},
    {"id": "q6_only", "type": "single", "tier": 1,
     "title": "如果佩戴感很好，什么样的日抛 10 片装价位是后续会考虑购买的？",
     "options": ["20元及以下", "20-30元", "30-40元", "40-50元", "50元以上"],
     "show_if": {"q": "q3", "in": [ONLY_BEAUTY]}},

    {"id": "q4_cycle", "type": "multi", "tier": 2,
     "title": "你平时会购买哪种类型的透明片？",
     "options": ["日抛", "月抛", "双周抛", "季抛", "半年抛", "年抛"]},
    {"id": "q5_scene", "type": "multi", "tier": 2,
     "title": "你平时会在哪些场景佩戴透明片？",
     "options": ["上班", "上学", "运动/健身", "长时间通勤（如旅行、出差途中等）", "淡妆或素颜出门时", "无社交或拍照需求时都会戴透明片"]},
    {"id": "q6_purchase", "type": "single", "tier": 2,
     "title": "你是否购买过 moody 的透明片？",
     "options": ["经常买", "偶尔买", "曾经买过，现在不买了", "从没买过"]},

    {"id": "q7_products", "type": "multi", "tier": 2,
     "title": "买过的 moody 透明片是？",
     "options": ["moody 目怡蓝 M 系列", "moody 目怡蓝薄润系列", "moody 目怡蓝 S 系列"],
     "show_if": {"q": "q6_purchase", "in": ["经常买", "偶尔买"]}},
    {"id": "q8_purchase_reason", "type": "multi", "tier": 2,
     "title": "购买 moody 透明片的契机是？", "options": PURCHASE_REASONS,
     "show_if": {"q": "q6_purchase", "in": ["经常买", "偶尔买"]}},
    {"id": "q9_other_brands", "type": "multi", "tier": 2,
     "title": "除了 moody 以外，你日常还购买哪些品牌的透明片？", "options": BRANDS_BOUGHT,
     "show_if": {"q": "q6_purchase", "in": ["经常买", "偶尔买"]}},
    {"id": "q10_satisfied", "type": "multi", "tier": 2,
     "title": "你对 moody 透明片的哪些方面感到满意？",
     "options": ["不磨眼", "久戴不干涩", "不滑片", "不模糊", "好戴、好摘", "价格划算", "包装好看"],
     "show_if": {"q": "q6_purchase", "in": ["经常买", "偶尔买"]}},

    {"id": "q7_lapsed_reason", "type": "multi", "tier": 2, "max": 3,
     "title": "最初购买 moody 透明片的契机是？", "options": LAPSED_PURCHASE_REASONS,
     "show_if": {"q": "q6_purchase", "in": ["曾经买过，现在不买了"]}},
    {"id": "q8_stop_reason", "type": "multi", "tier": 2,
     "title": "为什么后来不再购买了？",
     "options": ["对舒适度不满意", "发现材质更好的产品", "发现功能更丰富的产品（如防蓝光等）", "发现价格更合适的产品", "发现外包装更好看的产品", "做了近视矫正手术", "其他"],
     "show_if": {"q": "q6_purchase", "in": ["曾经买过，现在不买了"]}},
    {"id": "q9_return", "type": "multi", "tier": 2,
     "title": "以下哪些改进会让你重新选择购买 moody 透明片？",
     "options": ["镜片材质升级（如提高透氧等）", "舒适度提升", "增加护眼功能（如防蓝光、减轻干眼、减少眼睛酸胀等）", "价格更优惠", "外包装升级", "以上都不会", "其他"],
     "show_if": {"q": "q6_purchase", "in": ["曾经买过，现在不买了"]}},

    {"id": "q7_never_reason", "type": "multi", "tier": 2,
     "title": "没有购买 moody 透明片的原因是？",
     "options": ["不知道 moody 有透明片", "购买透明片时优先考虑其他品牌", "包装不够好看", "价格不够优惠"],
     "show_if": {"q": "q6_purchase", "in": ["从没买过"]}},
    {"id": "q8_daily_brands", "type": "multi", "tier": 2,
     "title": "你日常购买的是哪些品牌的透明隐形眼镜？", "options": BRANDS_DAILY,
     "show_if": {"q": "q6_purchase", "in": ["从没买过"]}},
    {"id": "q9_brand_reason", "type": "multi", "tier": 2,
     "title": "选择以上品牌的原因是？",
     "options": ["大品牌保障", "产品参数足够好（高含水/高透氧）", "明星/博主推荐", "实际试戴体验后觉得很舒服", "在购物软件首页刷到", "价格优惠", "包装好看", "其他"],
     "show_if": {"q": "q6_purchase", "in": ["从没买过"]}},
    {"id": "q10_first_purchase", "type": "single", "tier": 2,
     "title": "以下哪种方式最可能促使你第一次购买 moody 的透明隐形眼镜？",
     "options": ["提供9.9元试用装", "会员积分兑换透明片试用装", "博主真实测评种草", "医生/专业机构背书", "不会尝试"],
     "show_if": {"q": "q6_purchase", "in": ["从没买过"]}},

    {"id": "q11_price", "type": "single", "tier": 2,
     "title": "你对日抛 10 片装透明隐形眼镜的价格预期是？",
     "options": ["20元及以下", "20-30元", "30-40元", "40-50元", "50元以上"]},
    {"id": "q12_premium", "type": "multi", "tier": 2, "max": 3, "other_max": 100,
     "title": "你愿意因为什么接受比预期更高的透明隐形眼镜价格？",
     "options": ["权威性医疗背书（如与三甲医院联合研制）", "突破性的材质/含水量/镜片厚度/透氧量", "由信任或熟悉的品牌推出", "与你喜欢的 IP 联名", "漂亮的包装设计", "其他"]},
    {"id": "q13_channel", "type": "multi", "tier": 2,
     "title": "你通常通过什么渠道了解隐形眼镜新品？",
     "options": ["小红书", "抖音", "淘宝/天猫", "拼多多", "京东", "朋友或家人推荐", "b站", "视频号", "线下门店", "其他"]},
    {"id": "q14_content", "type": "multi", "tier": 2, "max": 3,
     "title": "哪种内容最容易让你对透明隐形眼镜产生兴趣？",
     "options": ["测评类", "科普类", "长时间佩戴体验测评", "大规格促销或试用装薅羊毛活动", "其他"]},

    {"id": "q_degree", "type": "single", "tier": 1, "degree": True,
     "title": "最后一步：你的隐形眼镜度数是？",
     "note": "请选择用于兑奖的镜片度数；若左右眼度数不同，请选择需要兑奖的度数。",
     "options": DEGREES},
]


def upsert_moody(db):
    """将当前问卷定义幂等同步到数据库，不删除任何已有答卷。"""
    survey = db.query(Survey).filter_by(slug=SLUG).one_or_none()
    if survey is None:
        survey = Survey(slug=SLUG, title=TITLE, schema_json=SCHEMA, status="active")
        db.add(survey)
    survey.title = TITLE
    survey.schema_json = SCHEMA
    survey.status = "active"
    survey.new_product_url = NEW_PRODUCT_URL
    survey.channel_product_urls = CHANNEL_PRODUCT_URLS
    survey.starts_at = STARTS_AT
    survey.ends_at = ENDS_AT
    db.commit()
    return survey


def main():
    Base.metadata.create_all(bind=engine)
    ensure_starts_at_column(engine)
    ensure_ends_at_column(engine)
    db = SessionLocal()
    try:
        upsert_moody(db)
        print("seeded moody: %d questions (tier1=%d, tier2=%d)" % (
            len(SCHEMA),
            sum(1 for q in SCHEMA if q.get("tier") == 1),
            sum(1 for q in SCHEMA if q.get("tier") == 2),
        ))
        print("active window (Asia/Shanghai): %s - %s" % (STARTS_AT, ENDS_AT))
    finally:
        db.close()


if __name__ == "__main__":
    main()
