# app/models.py
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, JSON, Text, UniqueConstraint

from app.database import Base
from app.timeutil import now_cn


class Survey(Base):
    __tablename__ = "wj_surveys"   # wj_ 前缀：共享库（RDS web 库）内防撞名
    __table_args__ = {"comment": "问卷定义：题目结构、奖励口径与活动周期"}
    id = Column(Integer, primary_key=True, comment="主键")
    slug = Column(String(64), unique=True, nullable=False, index=True, comment="URL 标识，问卷链接 /s/{slug}")
    title = Column(String(255), nullable=False, comment="问卷标题")
    schema_json = Column(JSON, nullable=False, default=list, comment="题目结构 JSON（题型/选项/分支 show_if/分层 tier）")
    reward_type = Column(String(32), default="manual", comment="奖励发放方式：manual 人工核销")
    new_product_url = Column(String(512), nullable=True, comment="结果页「去兑奖」默认跳转地址（渠道未命中时回退）")
    channel_product_urls = Column(JSON, nullable=True, comment="按渠道配兑奖链接 {channel: url}，如 {tmall: 天猫商品, douyin: 抖店商品}；未命中回退 new_product_url")
    status = Column(String(16), default="active", comment="问卷状态：active 进行中 / closed 已关闭")
    ends_at = Column(DateTime, nullable=True, comment="活动结束时间；到点后 token 失效。空=不自动失效")
    created_at = Column(DateTime, default=now_cn, comment="创建时间（北京时间）")


class Distribution(Base):
    __tablename__ = "wj_distributions"
    __table_args__ = (
        # tmall 小程序按 aid 防重领：同问卷同 aid 唯一(NULL 不互斥,非 tmall 分发不受影响)
        UniqueConstraint("survey_id", "bound_aid", name="uq_wj_dist_survey_aid"),
        {"comment": "分发记录：通用链接按设备自动领取的 72h token（设备幂等/同 IP 单设备）"},
    )
    id = Column(Integer, primary_key=True, comment="主键")
    survey_id = Column(Integer, ForeignKey("wj_surveys.id"), nullable=False, index=True, comment="所属问卷 ID")
    channel = Column(String(32), nullable=False, comment="渠道标识：sms/wangwang/ad_xx 等")
    token = Column(String(64), unique=True, nullable=False, index=True, comment="访问令牌，md5(生成时间+到期时间) 派生")
    created_at = Column(DateTime, default=now_cn, comment="领取/生成时间（北京时间）")
    expires_at = Column(DateTime, nullable=False, comment="token 到期时间（领取后 72h）")
    bound_fingerprint = Column(String(128), nullable=True, comment="首开绑定的设备指纹，绑定后他人不可用")
    bound_ip = Column(String(64), nullable=True, comment="首绑设备时记录的 IP，用于同 IP 单设备硬拦")
    bound_aid = Column(String(128), nullable=True, comment="tmall 渠道小程序匿名 aid，按此防重领")
    user_code = Column(String(32), nullable=True, comment="用户核对码：md5(token+指纹)[:8]，首开绑定时派生")


class Submission(Base):
    __tablename__ = "wj_submissions"
    __table_args__ = {"comment": "问卷提交记录：答案、设备/风控信息与兑奖码"}
    id = Column(Integer, primary_key=True, comment="主键")
    survey_id = Column(Integer, ForeignKey("wj_surveys.id"), nullable=False, index=True, comment="所属问卷 ID")
    redeem_code = Column(String(16), unique=True, nullable=False, index=True, comment="兑奖码 WJ-XXXXXX（全局唯一）")
    channel = Column(String(32), nullable=False, comment="提交渠道")
    token = Column(String(64), nullable=True, comment="提交时使用的分发 token")
    answers_json = Column(JSON, nullable=False, default=dict, comment="答案 JSON：{题目ID: 答案}")
    ip = Column(String(64), nullable=True, comment="提交时客户端 IP")
    fingerprint = Column(String(128), nullable=True, index=True, comment="设备指纹（去重口径）")
    session_id = Column(String(64), nullable=True, index=True, comment="页面会话 ID，关联埋点 wj_events.session_id")
    ua = Column(Text, nullable=True, comment="User-Agent（服务端记录）")
    device_json = Column(JSON, nullable=True, comment="客户端采集的设备信息（平台/屏幕/时区等）")
    elapsed_ms = Column(Integer, default=0, comment="答题耗时（毫秒）")
    risk_score = Column(Integer, default=0, comment="风控总分，超阈值标记 flagged")
    risk_flags = Column(JSON, default=list, comment="命中的风控规则列表")
    status = Column(String(16), default="new", comment="状态：new 新提交 / flagged 可疑 / redeemed 已核销 / rejected 已拒绝")
    tier_reached = Column(Integer, default=1, comment="用户最终达到的层级：1 基础 / 2 进阶")
    degree = Column(Integer, default=0, comment="用户填写的眼睛度数（解析后 0-1000，非法为 0）")
    created_at = Column(DateTime, default=now_cn, comment="提交时间（北京时间）")


class AdminUser(Base):
    __tablename__ = "wj_admin_users"
    __table_args__ = {"comment": "后台账号：运营/客服登录管理端"}
    id = Column(Integer, primary_key=True, comment="主键")
    username = Column(String(64), unique=True, nullable=False, index=True, comment="登录用户名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希（bcrypt）")
    role = Column(String(16), default="ops", comment="角色：ops 运营 / csr 客服")


class Event(Base):
    """通用行为埋点事件。一行 = 一个行为；多选答题拆成每个选项一行。"""
    __tablename__ = "wj_events"
    __table_args__ = {"comment": "行为埋点事件：一行一个行为；多选答题按选项拆行"}
    id = Column(Integer, primary_key=True, comment="主键")
    survey_id = Column(Integer, ForeignKey("wj_surveys.id"), nullable=True, index=True, comment="所属问卷 ID（可空）")
    session_id = Column(String(64), nullable=True, index=True, comment="一次页面会话 ID")
    fingerprint = Column(String(128), nullable=True, index=True, comment="设备指纹")
    event_type = Column(String(48), nullable=False, index=True, comment="事件类型（中文）：页面浏览/页面离开/浏览问题/回答问题/下一题/上一题/提交问卷/继续作答/升级提交/点击去兑奖")
    question_id = Column(String(64), nullable=True, index=True, comment="题目ID：浏览问题/回答问题/翻题/提交时记录，其余事件为空")
    question_title = Column(String(255), nullable=True, comment="题目内容：落库时从问卷结构快照，便于直接查表阅读")
    option_value = Column(Text, nullable=True, comment="内容：回答问题=选项/答案(多选每选项一行)；页面浏览=落地页类型(答题页/无资格页/兑奖码页等)")
    dwell_seconds = Column(Float, nullable=True, comment="用户停留时长（秒）：页面离开=会话总停留；下一题/上一题/提交问卷/继续作答=刚离开那道题的停留；填写度数=度数框耗时；点击去兑奖=看码页到点击的耗时")
    channel = Column(String(32), nullable=True, comment="渠道标识")
    token = Column(String(64), nullable=True, comment="分发 token（可空）")
    ip = Column(String(64), nullable=True, comment="客户端 IP")
    created_at = Column(DateTime, default=now_cn, index=True, comment="服务端落库时间（北京时间）")
