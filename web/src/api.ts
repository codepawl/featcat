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
  stats: () => cachedRequest<Record<string, any>>('/stats'),
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
  },
  docs: {
    get: (name: string) => cachedRequest<any>(`/docs/by-name?name=${encodeURIComponent(name)}`),
    stats: () => cachedRequest<any>('/docs/stats'),
    generate: (data: Record<string, any>) => request<any>('/docs/generate', { method: 'POST', body: JSON.stringify(data) }),
  },
  monitor: {
    check: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : ''
      return cachedRequest<any>(`/monitor/check${qs}`)
    },
    baseline: () => request<any>('/monitor/baseline', { method: 'POST' }),
    report: () => request<any>('/monitor/report'),
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
