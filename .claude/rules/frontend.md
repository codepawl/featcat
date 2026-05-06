---
paths:
  - "web/**/*.{ts,tsx}"
---

# Frontend rules
- Tailwind only, no custom CSS unless unavoidable
- All API calls go through `web/src/api.ts` (`api` object + `invalidateCache()`), never `fetch()` directly in components
- No `any` type in TypeScript
- Dark/light theme via Tailwind `class` strategy — toggle `document.documentElement.classList`, persist to localStorage
- Chat state lives in `stores/chatStore.ts` (module-level store, not React state) — persists across tab switches via `useSyncExternalStore`
- Use bun as package manager (bun.lock is committed)