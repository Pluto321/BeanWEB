# Architecture: Personal Beancount Manager

A modular monolith web application for importing, normalizing, auditing, and converting personal financial statements into Beancount ledger files.

## Core Principles
1. **Source of Truth**: SQLite database.
2. **Auditability**: Original files are immutable; every state change is logged.
3. **Separation of Concerns**: Importers, Normalizers, Rule Engine, and Generators are decoupled modules.
4. **Human in the Loop**: Low-confidence transactions must be manually reviewed.
5. **No Over-Engineering**: Single-user, modular monolith, no unnecessary distributed systems.

## Data Pipeline
1. **Ingestion**: Raw file upload → `Files` table.
2. **Normalization**: `Importer` → `RawTransaction` → `NormalizedTransaction`.
3. **Deduplication**: Hash collision check on `(date, amount, counterpart, source)`.
4. **Classification**: `Rule Engine` (deterministic) → `AI Service` (probabilistic/optional) → `Status: PENDING_REVIEW`.
5. **Human Review**: UI-based manual override/confirmation → `Status: CONFIRMED`.
6. **Export**: `Generator` → `.bean` file (with metadata referencing DB IDs).

## Tech Stack
- **Backend**: Python, FastAPI, SQLAlchemy, SQLite, Pydantic, Alembic.
- **Frontend**: React, TypeScript, Tailwind CSS.
- **Deployment**: Docker Compose.
