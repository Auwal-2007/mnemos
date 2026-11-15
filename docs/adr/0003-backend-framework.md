# ADR-0003: Backend — Python + FastAPI + Pydantic v2

- **Status:** Accepted
- **Date:** 2026-11-15

## Context

MNEMOS needs a Python-based application and API that orchestrates
agents, enforces authorization, validates input, and accesses Supabase
through controlled repositories. The stack must support async I/O for
model calls and provide strong validation at trust boundaries.

## Decision

Use Python 3.11+ with FastAPI (async ASGI), Pydantic v2 for validation
and settings, httpx for HTTP, and the Supabase Python client for data
access. Type checking with mypy (strict), linting/formatting with Ruff,
tests with pytest + httpx. Dependencies pinned in `requirements.txt`.

## Alternatives considered

- **Django:** rejected — heavier framework with its own ORM that
  conflicts with the Supabase-first data-access strategy; MNEMOS needs
  a focused API, not a full CMS-style stack.
- **Flask:** rejected — less structured for async agent orchestration
  and OpenAPI generation; FastAPI provides validation and docs out of
  the box.
- **Node/Express backend:** rejected — project direction is
  Python-based, and the AI/agent ecosystem (Pydantic, LangChain-adjacent
  tooling) is strongest in Python.

## Consequences

- Positive: async support, OpenAPI generation, Pydantic validation,
  mature testing ecosystem, easy Supabase integration.
- Negative: Python performance characteristics require care for
  CPU-bound work (mitigated by async I/O and future workers if needed).
- Replaceability: moderate — REST boundary decouples frontend; agent
  logic is isolated behind service interfaces.
