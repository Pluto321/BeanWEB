# BeanWEB

个人 Beancount 账单管理 Web 应用：Import → Analyze → Dedup（含跨源 Layer 4）→ Rule → Review → Confirm → Export → .bean → Reconciliation（配合 Fava）。

> 本文件是开源版交接文档模板。个人运维文档 `HANDOFF.md` 含真实账户与数据状态，**不入库**（已 gitignore）。
> **隐私纪律：真实账单数据（卡号、姓名、本地商户、交易明细）绝不写入任何 git 跟踪文件；测试一律使用 `tests/fixtures/generate_*_fixture.py` 生成的合成数据。**

## 技术栈

- Backend: FastAPI + SQLAlchemy + Alembic + SQLite（uvicorn 端口 8000，工作目录须为 backend/）
- Frontend: React + TypeScript + Vite（端口 5173，proxy /api → 8000）
- 原生 CSS Design System（"Quiet Finance"），无 UI/chart/icon 依赖
- 依赖：pdfplumber（PDF 解析）、openpyxl（xlsx）、beancount（导出校验/账本加载，metadata 键仅 ASCII）；reportlab/openpyxl 仅用于生成合成测试 fixture

## 核心原则（不可违反）

1. SQLite 是业务 Source of Truth；.bean 是生成制品，可按 DB 整体重生成
2. Raw 不可变；Raw 与 Normalized 分离
3. Transaction 1:N TransactionSplit（role: expense=分类腿 / payment=支付腿）
4. 金额全程 Decimal；`NormalizedTransaction.amount` 恒为正幅值，符号语义由 direction 表达
5. 交易状态机：REVIEW_REQUIRED / POSSIBLE_DUPLICATE / CONFIRMED / IGNORED；导出状态由 ExportRecord 管理（PENDING/EXPORTING/EXPORTED/FAILED/SUPERSEDED）
6. Service 层不 db.commit()，由 API/caller 控制事务
7. 不引入 Redis/Celery/Kafka/AI/LLM/微服务
8. 前端所有 API 走 `frontend/src/api/client.ts` 的 apiFetch；金额 tabular-nums 右对齐；状态中文命名统一（待审核/疑似重复/已确认/已忽略/已导出）
9. 导出幂等：重复导出 409；re-export = SUPERSEDED 旧记录 + 月度 fragment 按月 DB-true 重生成
10. 跨源去重（Layer 4）只标 POSSIBLE_DUPLICATE，**绝不自动跳过**——裁决权在人
11. accounts.bean 分**手写区**与 **AUTO-OPEN 托管块**：导出时自动补 open，**手写行绝不触碰**
12. 分录渲染双实现必须同口径：`export_service.render_preview()` 与 `BeancountGenerator`
13. `settings.DATABASE_URL` 是唯一 DB 来源（env 可覆盖）；测试严禁触碰生产库（conftest 强制重定向 + 守卫）
14. 生产库写操作：先备份 + 用户明确授权

## 账单来源

支付宝 CSV、微信 XLSX、银行 PDF。新银行照 `bank_importers.py` 的 matches_file/detect/parse/normalize 模式扩展。

## API 要点

- **GET /api/transactions 双契约**：带 `page` → 分页对象；不带 → 全量裸数组（legacy 依赖，迁移是待办）
- **POST /api/backups**：SQLite 在线快照（sqlite3 backup API，审计入库）；GET 列表；恢复端点属高危暂不开放
- **POST /api/rules/apply**：对存量交易重跑规则。`dry_run` 默认 true；范围=非 CONFIRMED，收入跳过，只预填 expense 分类腿，不改状态
- **POST /api/imports/analyze**：返回全部行明细 `rows[]`（kind=new/existing/possible_duplicate/invalid）
- Importer 注册序按 `matches_file()` 魔数+表头签名探测；无全局交易号的银行账单用内容 sha256 合成 ID
- **Dedup 四层**：source_id → raw_hash → canonical_fingerprint → 跨源匹配；POSSIBLE 时落库 duplicate_reason

## 前端结构

- TransactionList：服务端分页（50/页）+ 搜索防抖 + chips 全局计数 + `?status=` 入历史栈
- RulesPage：规则 CRUD + 「重跑规则」（dry-run 预览 → 应用，不覆盖已确认）
- ReviewDrawer / TransactionDetail：split 幅值归一（PUT 契约为正数）；预览 meta 仅显 channel

## 测试纪律

- `tests/conftest.py`：任何 app 导入前强制 `DATABASE_URL` 指向 pytest 专用临时库；指向生产库立即 fail
- 直调 FastAPI 路由函数时可选参数**必须显式传 None**（`Query(...)` 默认值是对象）
- 合成 fixture 全部进 git，`generate_*_fixture.py` 可复现；真实账单冒烟测试 skip-if-present，绝不写生产库
- 造测试数据用独特标记（WTEST 前缀等），测后清理
