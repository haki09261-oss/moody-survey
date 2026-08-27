# moody 用户调研问卷

当前生产框架基于 FastAPI + SQLAlchemy，问卷结构由数据库 JSON 配置驱动。移动端、答题分流、反作弊、设备/IP 去重、随机兑换码、后台核销与数据分析共用同一套服务端数据。

当前活动有效期（北京时间）：2026-08-28 10:00:00 至 2026-08-31 09:59:59。开始前不下发题目且禁止提交，结束后停止领取和提交。

## 当前业务流程

- 第 3 题选择「只戴美瞳」：完成共 6 题并选择度数，获得 M 系列 2 片装。
- 第 3 题选择任一「两种都戴」：自动继续透明片完整问卷，完成后获得 M 系列 10 片装。
- 兑换码格式为 `WJ-XXXXXX02-525` 或 `WJ-XXXXXX10-525`，同时包含奖品片数和度数。
- 点击「去兑奖」自动复制兑换码，并打开天猫商品 `1072972797956`。
- 后台搜索完整兑换码后核销；已核销状态保留用于审计和分析，但不能重复兑奖。

## 反作弊与数据口径

- 同一设备指纹只能参与一次；同一 IP 地址只能绑定一个参与设备。
- 少于 5 秒完成会保留为异常答卷，但前台不显示兑换码，后台禁止核销。
- 多道题持续选择相同选项位置，或答案文字全部相同，会标记为乱填；异常答卷同样不发码。
- 两种都戴的用户完成前五题后先保存为 `in_progress`，最终提交完整问卷时再按总耗时和全部答案判断有效性。
- 正式题目分析以 `wj_submissions.answers_json` 为准；行为埋点只用于浏览量、停留时间和流失点，避免埋点丢失造成答案少算。
- 后台的“核销”是状态销毁，不物理删除答卷，因此既能防止重复兑奖，也保留后续数据分析能力。

## 本地运行

推荐 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:SURVEY_DATABASE_URL='sqlite:///./data/survey.sqlite'
$env:SURVEY_ADMIN_SEED_USERNAME='admin'
$env:SURVEY_ADMIN_SEED_PASSWORD='请替换为强密码'
.\.venv\Scripts\python.exe scripts\seed_moody.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 3200
```

- 问卷：<http://127.0.0.1:3200/>
- 后台：<http://127.0.0.1:3200/admin>
- 健康检查：<http://127.0.0.1:3200/health>

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check web\survey.js
```

`npm.cmd run optimize:images` 仅用于重新生成 WebP 图片，不是问卷运行依赖。

## 云部署注意事项

1. 必须配置持久化数据库或持久化磁盘，不能把正式答卷只放在临时容器文件系统。
2. 必须通过 HTTPS，并配置真实的 `SURVEY_ADMIN_SEED_PASSWORD`。
3. Cloudflare/Nginx 代理需覆盖客户端转发头；服务端优先读取 `CF-Connecting-IP`，再读取 `X-Forwarded-For`。
4. 正式发布前用两台不同手机验收：2片装路径、10片装路径、同 IP 拦截、5秒异常、查码核销和二次核销。
5. SQLite 适合临时测试；多人长期使用建议迁移到 MySQL/PostgreSQL。

## 主要入口

- 问卷定义：[scripts/seed_moody.py](scripts/seed_moody.py)
- 用户端：[web/survey.html](web/survey.html)、[web/survey.js](web/survey.js)
- 提交/分流接口：[app/routers/survey.py](app/routers/survey.py)
- 后台接口：[app/routers/admin.py](app/routers/admin.py)
- 反作弊：[app/dedup.py](app/dedup.py)
- 服务端答案校验：[app/validation.py](app/validation.py)
