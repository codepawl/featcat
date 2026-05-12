import i18n from './i18n/config'

const API = '/api'

// Simple client-side cache for GET requests
const cache = new Map<string, { data: any; timestamp: number }>()
const CACHE_TTL = 10_000 // 10 seconds

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${endpoint}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `API ${res.status}`)
  }
  return res.json()
}

async function cachedRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const method = options?.method || 'GET'
  if (method === 'GET') {
    const key = endpoint
    const cached = cache.get(key)
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      return cached.data as T
    }
    const data = await request<T>(endpoint, options)
    cache.set(key, { data, timestamp: Date.now() })
    return data
  }
  return request<T>(endpoint, options)
}

export function invalidateCache(prefix?: string) {
  if (prefix) {
    for (const key of cache.keys()) {
      if (key.includes(prefix)) cache.delete(key)
    }
  } else {
    cache.clear()
  }
}

export interface SimilarityFeatureBrief {
  id: string
  name: string
  dtype: string
  source: string
  has_doc: boolean
}

export type SimilarityReasonCode = 'name_similarity' | 'schema_match' | 'distribution_match' | 'semantic_match'

export interface RecommendMatch {
  feature: SimilarityFeatureBrief
  score: number
  reason: string
}

export interface RecommendResponse {
  use_case: string
  method: 'llm' | 'tfidf' | 'embedding'
  matches: RecommendMatch[]
  summary: string | null
}

export interface DriftMatrixCell {
  date: string
  severity: string
  psi: number | null
}

export interface DriftMatrixFeature {
  id: string
  name: string
  source: string
  daily: DriftMatrixCell[]
}

export interface DriftMatrixResponse {
  date_range: string[]
  features: DriftMatrixFeature[]
  truncated: boolean
  total_count: number
}

export const api = {
  health: () => cachedRequest<{ status: string; llm: boolean; model?: string }>('/health'),
  stats: () => cachedRequest<Record<string, number>>('/stats'),
  docDebt: () => cachedRequest<{ owner: string; source: string; total: number; undocumented: number; pct_undocumented: number }[]>('/stats/doc-debt'),
  statsBySource: () => cachedRequest<{ source_name: string; path: string; feature_count: number; documented_count: number; drift_alerts: number; critical_alerts: number; last_scanned: string | null; top_drifting_feature: string | null }[]>('/stats/by-source'),
  sources: {
    list: () => cachedRequest<any[]>('/sources'),
    get: (name: string) => cachedRequest<any>(`/sources/${encodeURIComponent(name)}`),
    add: (data: Record<string, any>) => request<any>('/sources', { method: 'POST', body: JSON.stringify(data) }),
    scan: (name: string) => request<any>(`/sources/${encodeURIComponent(name)}/scan`, { method: 'POST' }),
  },
  features: {
    list: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : ''
      return cachedRequest<any[]>(`/features${qs}`)
    },
    /**
     * Paginated variant. Server returns `{items, total, limit, offset}` envelope
     * when `?limit` is set. Use this for the Features page (5000+ row scale);
     * `list()` stays for callers that want the unbounded enriched list (they
     * accept the O(N) cost — health-grade filter, exporter, etc.).
     */
    listPaginated: (params: Record<string, string | number>) => {
      const qs = '?' + new URLSearchParams(
        Object.entries(params).map(([k, v]) => [k, String(v)])
      ).toString()
      return cachedRequest<{ items: any[]; total: number; limit: number; offset: number }>(`/features${qs}`)
    },
    get: (name: string) => cachedRequest<any>(`/features/by-name?name=${encodeURIComponent(name)}`),
    update: (name: string, data: any) => request<any>(`/features/by-name?name=${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (name: string) => request<any>(`/features/by-name?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
    versions: (name: string) => cachedRequest<Record<string, unknown>[]>(
      `/features/by-name/versions?name=${encodeURIComponent(name)}`
    ),
    healthSummary: () => cachedRequest<{
      grade_distribution: Record<string, number>;
      average_score: number;
      lowest_scored: { spec: string; score: number; grade: string }[];
      improvement_opportunities: { spec: string; missing: string[] }[];
    }>('/features/health-summary'),
    /**
     * Aggregated certification-status counts for the Dashboard tile.
     * Backend computes via a single GROUP BY — much cheaper than
     * fetching the full feature list and counting client-side.
     */
    statusCounts: () => cachedRequest<{
      draft: number;
      reviewed: number;
      certified: number;
      deprecated: number;
      total: number;
    }>('/features/stats/status-counts'),
    recommend: (body: { use_case: string; top_k?: number; use_llm?: boolean; exclude_ids?: string[] }) =>
      request<RecommendResponse>('/features/recommend', {
        method: 'POST',
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30_000),
      }),
  },
  docs: {
    get: (name: string) => cachedRequest<Record<string, unknown>>(`/docs/by-name?name=${encodeURIComponent(name)}`),
    stats: () => cachedRequest<Record<string, unknown>>('/docs/stats'),
    glossary: () => cachedRequest<{ terms: Record<string, GlossaryTerm> }>('/docs/glossary'),
    generate: (data: Record<string, unknown>) => request<Record<string, unknown>>('/docs/generate', { method: 'POST', body: JSON.stringify(data) }),
    generateBatch: (data: { feature_specs: string[]; regenerate_existing: boolean; global_hint: string | null }) =>
      request<{ job_id: string; total: number }>('/docs/generate-batch', { method: 'POST', body: JSON.stringify(data) }),
    batchStatus: (jobId: string) =>
      request<{ job_id: string; total: number; completed: number; failed: number; status: string }>(
        `/docs/generate-batch/${encodeURIComponent(jobId)}/status`
      ),
  },
  monitor: {
    check: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : ''
      return cachedRequest<Record<string, unknown>>(`/monitor/check${qs}`)
    },
    baseline: () => request<Record<string, unknown>>('/monitor/baseline', { method: 'POST' }),
    report: () => request<Record<string, unknown>>('/monitor/report'),
    history: (featureSpec: string, days = 30) =>
      cachedRequest<{ checked_at: string; psi: number | null; severity: string }[]>(
        `/monitor/history/${encodeURIComponent(featureSpec)}?days=${days}`
      ),
    baselineStats: (featureSpec: string) =>
      cachedRequest<{ feature_spec: string; baseline_stats: Record<string, number>; computed_at: string | null }>(
        `/monitor/baseline/${encodeURIComponent(featureSpec)}`
      ),
  },
  search: {
    /**
     * Ranked full-text search (T2.2a). Server returns
     * `[{id, name, dtype, source, rank, snippet?}]` sorted by rank desc.
     */
    query: (params: { q: string; source?: string[]; tag?: string[]; dtype?: string[]; has_doc?: boolean | null; limit?: number }) => {
      const qs = new URLSearchParams()
      qs.set('q', params.q)
      // Backend accepts a single value per filter (str | None). When multiple
      // values are picked we send the first; the rest are filtered client-side
      // from the result set so toggling stays interactive.
      if (params.source && params.source.length > 0) qs.set('source', params.source[0])
      if (params.tag && params.tag.length > 0) qs.set('tag', params.tag[0])
      if (params.dtype && params.dtype.length > 0) qs.set('dtype', params.dtype[0])
      if (params.has_doc != null) qs.set('has_doc', String(params.has_doc))
      qs.set('limit', String(params.limit ?? 50))
      return cachedRequest<{ id: string; name: string; dtype: string; source: string; rank: number; snippet?: string }[]>(
        `/search?${qs.toString()}`
      )
    },
    /**
     * Facet counts for the search-result sidebar. Same filter set as the
     * search itself, so applying a filter narrows other facet counts.
     */
    facets: (params: { q?: string; source?: string; tag?: string; dtype?: string; has_doc?: boolean | null }) => {
      const qs = new URLSearchParams()
      if (params.q) qs.set('q', params.q)
      if (params.source) qs.set('source', params.source)
      if (params.tag) qs.set('tag', params.tag)
      if (params.dtype) qs.set('dtype', params.dtype)
      if (params.has_doc != null) qs.set('has_doc', String(params.has_doc))
      const suffix = qs.toString() ? `?${qs.toString()}` : ''
      return cachedRequest<{
        sources: { name: string; count: number }[]
        tags: { name: string; count: number }[]
        dtypes: { name: string; count: number }[]
        has_doc: { true: number; false: number }
      }>(`/search/facets${suffix}`)
    },
    /** Lightweight typeahead — top-N ranked names for an autocomplete dropdown. */
    suggest: (q: string, limit = 10) => {
      const qs = new URLSearchParams({ q, limit: String(limit) })
      return cachedRequest<{ id: string; name: string; dtype: string; source: string; rank: number }[]>(
        `/search?${qs.toString()}`
      )
    },
  },
  ai: {
    ask: (query: string) => request<any>('/ai/ask', {
      method: 'POST',
      body: JSON.stringify({ query }),
      signal: AbortSignal.timeout(180_000),
    }),
    discover: (useCase: string) => request<any>('/ai/discover', {
      method: 'POST',
      body: JSON.stringify({ use_case: useCase }),
      signal: AbortSignal.timeout(180_000),
    }),
  },
  scanBulk: (data: { path: string; recursive?: boolean; owner?: string; tags?: string[]; dry_run?: boolean }) =>
    request<any>('/scan-bulk', { method: 'POST', body: JSON.stringify(data) }),
  groups: {
    list: (project?: string) => cachedRequest<any[]>(`/groups${project ? `?project=${encodeURIComponent(project)}` : ''}`),
    get: (name: string) => cachedRequest<any>(`/groups/${encodeURIComponent(name)}`),
    create: (data: { name: string; description?: string; project?: string; owner?: string }) =>
      request<any>('/groups', { method: 'POST', body: JSON.stringify(data) }),
    update: (name: string, data: any) =>
      request<any>(`/groups/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (name: string) =>
      request<any>(`/groups/${encodeURIComponent(name)}`, { method: 'DELETE' }),
    addMembers: (name: string, specs: string[]) =>
      request<any>(`/groups/${encodeURIComponent(name)}/members`, { method: 'POST', body: JSON.stringify({ feature_specs: specs }) }),
    removeMember: (name: string, spec: string) =>
      request<any>(`/groups/${encodeURIComponent(name)}/members?spec=${encodeURIComponent(spec)}`, { method: 'DELETE' }),
    health: (name: string) => cachedRequest<{
      group: string
      member_count: number
      average_score: number
      grade_distribution: Record<string, number>
      members: { spec: string; score: number; grade: string; drift_status: string; has_doc: boolean }[]
      lowest_scored: { spec: string; score: number; grade: string }[]
    }>(`/groups/${encodeURIComponent(name)}/health`),
    monitoring: (name: string) => cachedRequest<{
      group: string
      member_count: number
      severity_counts: Record<string, number>
      psi_average: number | null
      members_with_drift: { spec: string; severity: string; psi: number | null; checked_at: string | null }[]
      members: { spec: string; severity: string; psi: number | null; checked_at: string | null }[]
      last_check_at: string | null
    }>(`/groups/${encodeURIComponent(name)}/monitoring`),
    /**
     * Per-feature × per-day severity matrix for the heatmap chart.
     * Backend caps the response at 200 features (truncated=true when above).
     */
    driftMatrix: (name: string, days = 30) =>
      cachedRequest<DriftMatrixResponse>(
        `/groups/${encodeURIComponent(name)}/drift-matrix?days=${days}`,
      ),
    regenerateDocs: (name: string, opts: { regenerate_existing?: boolean; global_hint?: string | null } = {}) =>
      request<{ job_id: string; total: number; group: string }>(
        `/groups/${encodeURIComponent(name)}/regenerate-docs`,
        { method: 'POST', body: JSON.stringify({ regenerate_existing: opts.regenerate_existing ?? false, global_hint: opts.global_hint ?? null }) }
      ),
  },
  definitions: {
    get: (name: string) => cachedRequest<any>(`/features/by-name/definition?name=${encodeURIComponent(name)}`),
    save: (name: string, data: { definition: string; definition_type: string }) =>
      request<any>(`/features/by-name/definition?name=${encodeURIComponent(name)}`, { method: 'PUT', body: JSON.stringify(data) }),
    delete: (name: string) =>
      request<any>(`/features/by-name/definition?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },
  hints: {
    get: (name: string) => cachedRequest<any>(`/features/by-name/hints?name=${encodeURIComponent(name)}`),
    save: (name: string, hints: string) =>
      request<any>(`/features/by-name/hints?name=${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify({ hints }) }),
    delete: (name: string) =>
      request<any>(`/features/by-name/hints?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
  },
  usage: {
    top: (limit = 10, days = 30) => cachedRequest<{ name: string; view_count: number; query_count: number; total_count: number; last_seen: string; created_at: string; source: string }[]>(`/usage/top?limit=${limit}&days=${days}`),
    orphaned: (days = 30) => cachedRequest<{ name: string; last_seen: string | null }[]>(`/usage/orphaned?days=${days}`),
    activity: (days = 7) => cachedRequest<{ date: string; view_count: number; query_count: number; unique_features: number; total: number }[]>(`/usage/activity?days=${days}`),
    feature: (name: string, days = 30) => cachedRequest<Record<string, unknown>>(`/usage/feature?name=${encodeURIComponent(name)}&days=${days}`),
  },
  versions: {
    recent: (limit = 20, days = 7) => cachedRequest<Record<string, unknown>[]>(
      `/versions/recent?limit=${limit}&days=${days}`
    ),
  },
  export: {
    create: (data: { feature_specs?: string[]; group_name?: string; join_on?: string | null; format?: string }) =>
      request<{
        export_id: string; download_url: string; feature_count: number; row_count: number;
        sources_used: string[]; join_column: string | null; code_snippet: string;
        warnings: string[]; file_size: number;
      }>('/export', { method: 'POST', body: JSON.stringify(data) }),
    download: (exportId: string) => `${API}/export/${encodeURIComponent(exportId)}/download`,
  },
  similarity: {
    graph: (threshold = 0.3, source?: string) => cachedRequest<{
      nodes: { id: string; spec: string; source: string; dtype: string; has_doc: boolean; drift_status: string; tags: string[] }[];
      edges: { source: string; target: string; similarity: number }[];
    }>(`/features/similarity-graph?threshold=${threshold}${source ? `&source=${encodeURIComponent(source)}` : ''}`),
    matrix: (ids: string[], threshold: number) => cachedRequest<{
      features: SimilarityFeatureBrief[];
      cells: { a: number; b: number; score: number }[];
      threshold: number;
      cached_at: string | null;
    }>(`/features/similarity-matrix?ids=${encodeURIComponent(ids.join(','))}&threshold=${threshold}`),
    pair: (a: string, b: string) => cachedRequest<{
      a: SimilarityFeatureBrief;
      b: SimilarityFeatureBrief;
      score: number;
      reasons: { code: SimilarityReasonCode; detail: string }[];
    }>(`/features/similarity-pair?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`),
  },
  lineage: {
    full: () => cachedRequest<{
      nodes: { name: string; source: string; dtype: string; owner: string }[];
      edges: { child: string; parent: string; transform: string; detected_method: string }[];
    }>('/lineage/full'),
  },
  jobs: {
    list: () => cachedRequest<any[]>('/jobs'),
    logs: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : ''
      return cachedRequest<any[]>(`/jobs/logs${qs}`)
    },
    stats: () => cachedRequest<any>('/jobs/stats'),
    run: (name: string) => request<any>(`/jobs/${encodeURIComponent(name)}/run`, { method: 'POST' }),
    update: (name: string, data: any) => request<any>(`/jobs/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  scheduler: {
    /**
     * Unified job-status API (T1.5c). Same endpoints regardless of whether the
     * server is running APScheduler in-process or Celery — the `backend` field
     * on each summary tells you which.
     */
    listJobs: () => cachedRequest<JobSummary[]>('/scheduler/jobs'),
    getJob: (name: string) =>
      cachedRequest<JobDetail>(`/scheduler/jobs/${encodeURIComponent(name)}`),
    runJob: (name: string, kwargs?: Record<string, unknown>) =>
      request<JobTriggerResponse>(`/scheduler/jobs/${encodeURIComponent(name)}/run`, {
        method: 'POST',
        body: JSON.stringify({ kwargs: kwargs ?? null }),
      }),
    listRuns: (params?: { job?: string; limit?: number; since?: string }) => {
      const qs = new URLSearchParams()
      if (params?.job) qs.set('job', params.job)
      if (params?.limit) qs.set('limit', String(params.limit))
      if (params?.since) qs.set('since', params.since)
      const suffix = qs.toString() ? `?${qs.toString()}` : ''
      return cachedRequest<JobRun[]>(`/scheduler/runs${suffix}`)
    },
  },
  admin: {
    cacheStats: () => cachedRequest<{ total: number; active: number; expired: number }>('/admin/cache/stats'),
    cacheClear: () => request<{ deleted: number }>('/admin/cache/clear', { method: 'POST' }),
    cacheClearExpired: () => request<{ deleted: number }>('/admin/cache/clear-expired', { method: 'POST' }),
  },
  bulk: {
    tags: (data: { feature_ids: string[]; action: 'add' | 'remove' | 'replace'; tags: string[] }) =>
      request<{ updated: number; requested: number }>('/features/bulk/tags', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    groups: (data: { feature_ids: string[]; action: 'add_to' | 'remove_from'; group_id: string }) =>
      request<{ changed: number; requested: number }>('/features/bulk/groups', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    delete: (data: { feature_ids: string[]; confirm: boolean }) =>
      request<{ deleted: number; requested: number }>('/features/bulk/delete', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
  },
  actions: {
    list: (params?: { feature_name?: string; status?: string; source?: string; limit?: number }) => {
      const qs = new URLSearchParams()
      if (params?.feature_name) qs.set('feature_name', params.feature_name)
      if (params?.status) qs.set('status', params.status)
      if (params?.source) qs.set('source', params.source)
      if (params?.limit) qs.set('limit', String(params.limit))
      const suffix = qs.toString() ? `?${qs.toString()}` : ''
      return cachedRequest<ActionItem[]>(`/actions${suffix}`)
    },
    count: (status = 'pending') =>
      cachedRequest<{ count: number }>(`/actions/count?status=${encodeURIComponent(status)}`),
    get: (id: string) => cachedRequest<ActionItem>(`/actions/${encodeURIComponent(id)}`),
    create: (data: {
      feature_name: string
      source: string
      title: string
      recommendation: string
      context?: Record<string, unknown>
    }) => request<ActionItem>('/actions', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: { status: string; applied_by?: string; change_summary?: string }) =>
      request<ActionItem>(`/actions/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
  },
}

export type GlossaryTerm = {
  label: string
  description: string
  formula?: string
  thresholds?: { grade?: string; min?: number; range?: string; severity?: string; meaning?: string; label?: string }[]
  values?: Record<string, string>
}

export type JobSummary = {
  name: string
  cron: string
  enabled: boolean
  next_run_at: string | null
  last_status: string | null
  last_run_at: string | null
  last_duration_ms: number | null
  last_error: string | null
  backend: string
}

export type JobRun = {
  id: string
  job_name: string
  status: string
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
  result_summary: Record<string, unknown>
  error_message: string | null
  triggered_by: string
}

export type JobDetail = JobSummary & {
  description: string
  recent_runs: JobRun[]
  active_celery_task_ids: string[]
}

export type JobTriggerResponse = {
  job_log_id: string
  celery_task_id: string | null
  status: string
}

export type ActionItem = {
  id: string
  feature_id: string
  feature_name: string
  source: 'drift_alert' | 'chat' | 'autodoc' | 'manual'
  title: string
  recommendation: string
  status: 'pending' | 'applied' | 'dismissed' | 'snoozed'
  created_by: string
  applied_by: string
  applied_at: string | null
  change_summary: string
  context: Record<string, unknown>
  created_at: string
  updated_at: string
}

/**
 * Human-friendly duration: 45ms / 1.2s / 2m 15s / 1h 5m. Accepts milliseconds
 * (preferred — matches `last_duration_ms` from /scheduler/jobs) or `null`.
 */
export function humanizeDuration(ms: number | null | undefined): string {
  if (ms == null) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const totalSec = Math.round(seconds)
  const minutes = Math.floor(totalSec / 60)
  const remSec = totalSec % 60
  if (minutes < 60) return remSec ? `${minutes}m ${remSec}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remMin = minutes % 60
  return remMin ? `${hours}h ${remMin}m` : `${hours}h`
}

/** Future-friendly variant of timeAgo — returns "in 5 min" for upcoming dates. */
export function timeUntil(dateStr: string | null | undefined): string {
  if (!dateStr) return i18n.t('time.never', { ns: 'common' })
  const lang = i18n.resolvedLanguage === 'vi' ? 'vi' : 'en'
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  const diff = (new Date(dateStr).getTime() - Date.now()) / 1000
  if (Math.abs(diff) < 60) return rtf.format(Math.round(diff), 'second')
  if (Math.abs(diff) < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (Math.abs(diff) < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  if (Math.abs(diff) < 604800) return rtf.format(Math.round(diff / 86400), 'day')
  return rtf.format(Math.round(diff / 604800), 'week')
}

export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return i18n.t('time.never', { ns: 'common' })
  const lang = i18n.resolvedLanguage === 'vi' ? 'vi' : 'en'
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto' })
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000
  if (diff < 60) return rtf.format(-Math.round(diff), 'second')
  if (diff < 3600) return rtf.format(-Math.round(diff / 60), 'minute')
  if (diff < 86400) return rtf.format(-Math.round(diff / 3600), 'hour')
  if (diff < 604800) return rtf.format(-Math.round(diff / 86400), 'day')
  if (diff < 2592000) return rtf.format(-Math.round(diff / 604800), 'week')
  if (diff < 31536000) return rtf.format(-Math.round(diff / 2592000), 'month')
  return rtf.format(-Math.round(diff / 31536000), 'year')
}
