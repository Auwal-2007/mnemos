# Testing

What is covered, how to run it, and what the numbers do and do not prove.

---

## 1. Running everything

```bash
# Backend: 487 tests, includes real-PostgreSQL integration
cd backend && .venv/bin/python -m pytest -q

# Migrations and RLS: 223 assertions against a real PostgreSQL
.venv/bin/python ../scripts/verify-migrations.py

# Static analysis
.venv/bin/ruff check app && .venv/bin/ruff format --check app
.venv/bin/python -m mypy app

# Frontend: 142 tests
cd ../frontend && npx vitest run
npx tsc --noEmit
npm run build

# Evaluation (boots its own PostgreSQL)
cd ../backend && .venv/bin/python -m app.evaluation.run --label check
```

CI runs the same commands; a pull request is not mergeable until they pass.

## 2. What the backend tests cover

| Area | Files | What is actually asserted |
|---|---|---|
| Retrieval service | `test_retrieval_service.py` (21) | Ranking, workspace scoping, empty results, degradation without embeddings |
| Verification | `test_verification.py` (38) | Verdict boundaries, contradiction handling, conflict detection, self-review refusal |
| Orchestration | `test_orchestration.py` (29) | Planning, delegation order, capability isolation, trace persistence, failure degradation |
| Generation | `test_generation.py` (24) | Citation binding, invalid-citation rejection, abstention when evidence is absent, provider failure produces no answer row |
| Completion provider | `test_completion_provider.py` (14) | Retry semantics, 429 vs 5xx distinction, timeouts, no-secret logging |
| Ingestion | `test_ingestion_*.py` (77) | Validation, extraction, status transitions, failure recording |
| API authorization | `test_authorization.py` (53) | Every protected route: no token, wrong user, wrong role |
| Conversations API | `test_conversations_api.py` (20) | Ask flow, abstention as 200, message ordering |
| Retrieval API | `test_retrieval_api.py` (14) | Contract, limits, degraded flag |
| Rate limiting | `test_rate_limit.py` (7) | Enforcement, probe exemption, per-subject bucketing, window reset |
| Evaluation | `test_evaluation.py` (26) | Metric arithmetic, dataset validation, calibration maths |

Integration tests against **real PostgreSQL** (`tests/integration/`): migrations,
RLS enforcement, retrieval through the actual SQL function, correction lifecycle,
write permissions, evaluation harness and seeding.

## 3. What the frontend tests cover

142 tests across 13 files: API client contracts (path, method, payload shape,
error normalisation, retryability), answer rendering in all three states,
conversation modes including the negative assertion that the old "no model
execution" copy is gone, accessibility and responsive assertions, design-system
consistency.

## 4. The honest limits of these numbers

**A high test count is not a quality claim.** Specifically:

- **No answer-quality test exists.** Whether a generated answer is *good* cannot
  be asserted without a model. Retrieval quality is measured separately in
  `docs/EVALUATION.md`; answer quality is unmeasured.
- **Provider interaction is tested against fakes**, not a live API. The retry and
  error-mapping logic is exercised; the real provider's behaviour is not.
- **No browser rendering test exists.** Playwright and Chromium could not be
  installed here, so responsive layout, focus order and visual regressions are
  asserted structurally (DOM, classes, ARIA) and by unit tests, not observed in a
  browser. Anyone claiming pixel verification of this build is wrong.
- **No coverage percentage is reported.** Line coverage would reward trivial
  assertions; the tests target behaviour, and no number here should be read as
  "percentage complete".
- **No load, soak or penetration testing** was performed.
- **Two tests were rewritten** during Phase 5A because they asserted that the
  composer was permanently disabled. They were locking in a false statement after
  the feature shipped. Rewriting a test is normally a smell; here the assertion
  itself was the defect, and the replacements assert the new behaviour *and* the
  absence of the old copy.

## 5. What "passing" means

A green run means: the assertions written were true at that commit, against a
real database where the test required one. It does not mean the feature is
correct in a way nobody thought to check, and it does not mean any provider
integration works — no live provider call has ever been made.
