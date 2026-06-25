# Code style

Conventions in featcat that aren't already obvious from running `ruff format`. The full ruleset is in `ruff.toml` and `mypy.ini`; this page captures the spirit, not the lookup table.

## Python

### Formatting

`ruff format` is the source of truth. Line-length 120, target Python 3.10+. Never argue about formatting in PR review — run the formatter.

### Imports + future

Every Python file starts with:

```python
from __future__ import annotations
```

This enables postponed evaluation of annotations, which lets us write `list[str]` instead of `List[str]` everywhere without a typing import.

Imports go in three groups separated by a blank line: stdlib, third-party, first-party.

### Type hints

Hint everywhere except very obvious local variables. Public APIs (anything called across module boundaries) must have full type hints — checked by mypy in CI.

Exceptions where mypy is loose:

- `featcat/tui/**`, `featcat/server/**`, `featcat/config.py` — `ignore_errors=true` in `mypy.ini`. Pragmatic: these layers cross too many dynamic boundaries (Textual, FastAPI dep injection, YAML loading) to be worth fighting.
- `featcat/cli/**`, `featcat/plugins/**` — selected error codes disabled (`misc`, `arg-type` mostly).

Don't try to "fix" the loose modules to be strict — that's a big project. New code in *strict* areas (catalog/, db/, ai/) does need to type-check.

### Naming

- `snake_case` for functions and variables, `PascalCase` for classes, `SCREAMING_SNAKE` for constants.
- Private to a module: leading `_`. Don't use double underscore for "private" — that's name-mangling, not privacy.
- Booleans read like predicates: `is_active`, `has_doc`, `should_refresh`. Not `active`, `doc_present`.
- Database column names match the Python attribute (`status_changed_at` in both, not `statusChangedAt` in one).

### Functions

- Small. If a function doesn't fit on a screen, suspect it's doing two things.
- Single return type. Don't return `Feature | None | bool` — pick one.
- Keyword-only after the first 2-3 positional args. Especially for booleans:

  ```python
  def list_features(source: str, *, has_doc: bool = False, limit: int = 50) -> list[Feature]: ...
  ```

  Forces callers to write `list_features("user_behavior", has_doc=True)`, which reads better than `list_features("user_behavior", True)`.

- No mutable default arguments. Use `None` and rebind.

### Classes

- Pydantic models for data crossing system boundaries (HTTP, file, DB→Python).
- `dataclasses` for internal value objects when Pydantic is overkill.
- ABCs for interface contracts (`CatalogBackend`, `BaseLLM`).
- No singletons unless they wrap external state (the SQLite connection pool counts; an in-memory cache doesn't).

### Comments

Default to no comments. Only when the *why* is non-obvious — a hidden constraint, a workaround, a surprising invariant. Code with good names doesn't need to be narrated.

```python
# OK — non-obvious
# tsvector column is GENERATED ALWAYS; can't be inserted into directly,
# so we update name/description/tags and let the DB recompute.

# Not OK — restates the code
# Update the user's email
user.email = new_email
```

No `# TODO: Alice, fix this in Q4`. File an issue. Code-base TODOs rot.

### Docstrings

One-line for most things. Reach for a multi-paragraph docstring only on the `BasePlugin.execute` / `BaseLLM.generate` kind of API where contract details matter.

```python
def list_features(source: str, *, limit: int = 50) -> list[Feature]:
    """Return features in `source`, ordered by name."""
```

Don't restate the type signature in the docstring.

### Errors

- Raise typed exceptions. Have a small hierarchy per domain (`FeatCatError → FeatureNotFound`).
- Don't swallow with `except Exception:` unless you're going to log and re-raise (or in a top-level handler that has to). Bare `except:` is forbidden.
- Validate at boundaries. Internal code can trust internal contracts.
- No `try/except` to hide bugs. If you don't know what to do with the exception, let it propagate.

### Async

FastAPI routes that touch the LLM are `async` and use `run_in_threadpool` + `asyncio.wait_for(..., timeout=180)` so blocking inference doesn't starve the event loop. Don't put bare blocking calls in `async def` routes.

CLI / TUI / scheduler are sync. Don't `asyncio.run` from sync code unless you really mean it.

## TypeScript / React

### Formatting

`bun run format` (or Biome via your editor). Don't hand-format.

### Components

- Function components only. No class components.
- One component per file when ≥ 50 lines. Co-locate small ones.
- Props typed at the function signature, not via separate `interface FooProps {}` unless it's reused.
- `useMemo` / `useCallback` only when the profiler shows it matters. Default to plain.

### State

- React state for UI-local stuff.
- Module-level stores (`stores/chatStore.ts`) for state that must survive tab switches. Subscribed via `useSyncExternalStore`.
- No Redux / Zustand / Recoil. The patterns above cover everything we have today.

### Styling

- Tailwind utility classes. No CSS modules, no styled-components.
- Dark mode: `dark:` prefix. Theme stored in localStorage, applied by toggling `document.documentElement.classList`.
- Reusable visual primitives in `web/src/components/ui/`.

### API calls

- `web/src/api.ts` is the only file allowed to call `fetch`. Components import its named functions.
- 10-second client-side cache for GETs; mutations call `invalidateCache(...)`.
- For SSE, use `EventSource` directly (the `useSSE` hook is for read-only streaming).

## Commit messages

Conventional commits: `<type>(<scope>): <subject>`.

Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `perf`.

Subject in imperative mood, ≤ 70 chars. Body wraps at 72.

```
docs(monitoring): clarify sensitive-feature drift guidance

Explains how to use feature hints to record why a reviewer should
investigate drift earlier than the global warning threshold.

Co-Authored-By: …
```

No scope is fine when the change is broad (`refactor: drop pandas hard-dep`).

## PR shape

- One theme per branch. If you find a refactor you want to do mid-feature, open a separate PR for the refactor first.
- Title in the same format as a commit: `feat(...)`. Body answers: what changed, why now, how was it tested, what's out of scope.
- Test plan a checklist. Even "ran make check; verified manually with /api/features" is fine.
- Link issues with `Fixes #N` if appropriate.

## What we *don't* do

- No 100% test coverage targets. Test what's risky; trust internal contracts.
- No "interfaces for everything" (no `IUserService`-style abstraction zoos).
- No microservices for things that share a database.
- No premature abstraction: 3 similar lines is better than a half-fitting helper.
- No "for future flexibility" code. Add the flexibility when you need it.

## Related

- **[Setup](setup.md)** — get the dev env running first
- **[Testing](testing.md)** — what to write tests for and how
- **[Architecture Overview](../architecture/overview.md)** — context for "where does my change go?"
