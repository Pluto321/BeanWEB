# BeanWEB

**A lightweight web workspace for Beancount.**

BeanWEB 是一个轻量级的 Beancount Web 工具，用于将银行、支付宝、微信等财务流水导入、整理、审核，并最终导出为 Beancount 分录。

## Features

* 📥 **Import** — 导入银行、支付宝等账单
* 🔍 **Deduplication** — 自动检查重复交易
* 🏷️ **Categorization** — 通过规则进行交易分类
* 👀 **Review** — 在导出前人工审核和修改
* 💰 **Accounts** — 管理支付账户和费用账户
* 📤 **Export** — 导出为 Beancount 分录
* 📝 **Audit Trail** — 保留交易处理记录

## Workflow

```text
Import
  ↓
Normalize
  ↓
Deduplicate
  ↓
Categorize
  ↓
Review
  ↓
Confirm
  ↓
Export
  ↓
Beancount
```

## Tech Stack

* **Backend:** Python · FastAPI · SQLAlchemy · SQLite
* **Frontend:** React · TypeScript · Vite
* **Accounting:** Beancount

## Project Structure

```text
BeanWEB/
├── backend/     # FastAPI backend
├── frontend/    # React frontend
├── tests/       # Tests
└── docs/        # Documentation
```

## Development

```bash
# Backend
cd backend
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Philosophy

BeanWEB 不试图替代 Beancount。

它专注于解决：

> **如何把现实世界的财务流水，可靠地变成经过审核的 Beancount 分录。**

原始数据保留，处理过程可追踪，最终账本由用户确认。

## License

See [LICENSE](LICENSE).
