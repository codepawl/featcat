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
  },
  docs: {
    get: (name: string) => cachedRequest<Record<string, unknown>>(`/docs/by-name?name=${encodeURIComponent(name)}`),
    stats: () => cachedRequest<Record<string, unknown>>('/docs/stats'),
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
}

export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return 'never'
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
