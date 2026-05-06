---
paths:
  - "featcat/server/**/*.py"
---

# API rules
- Route handlers call CatalogBackend methods via `Depends(get_db)`, no raw SQL in routes
- All endpoints return typed Pydantic response models
- LLM-calling routes must be `async` with `run_in_threadpool()` + `asyncio.wait_for` timeout (3 min)
- Feature lookups by name use query parameters (`?name=...`), not path parameters (dots in names break path routing)
- Scheduler tables (`job_schedules`, `job_logs`) are accessed directly via `backend.conn`, not through CatalogBackend