const API = '/api';

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${endpoint}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request<{ status: string; llm: boolean; model?: string }>('/health'),
  stats: () => request<Record<string, any>>('/stats'),
  sources: {
    list: () => request<any[]>('/sources'),
    get: (name: string) => request<any>(`/sources/${encodeURIComponent(name)}`),
    add: (data: Record<string, any>) => request<any>('/sources', { method: 'POST', body: JSON.stringify(data) }),
    scan: (name: string) => request<any>(`/sources/${encodeURIComponent(name)}/scan`, { method: 'POST' }),
  },
  features: {
    list: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : '';
      return request<any[]>(`/features${qs}`);
    },
    get: (name: string) => request<any>(`/features/${encodeURIComponent(name)}`),
    update: (name: string, data: any) => request<any>(`/features/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  docs: {
    get: (name: string) => request<any>(`/docs/${encodeURIComponent(name)}`),
    stats: () => request<any>('/docs/stats'),
    generate: (data: Record<string, any>) => request<any>('/docs/generate', { method: 'POST', body: JSON.stringify(data) }),
  },
  monitor: {
    check: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : '';
      return request<any>(`/monitor/check${qs}`);
    },
    baseline: () => request<any>('/monitor/baseline', { method: 'POST' }),
    report: () => request<any>('/monitor/report'),
  },
  ai: {
    ask: (query: string) => request<any>('/ai/ask', { method: 'POST', body: JSON.stringify({ query }) }),
    discover: (useCase: string) => request<any>('/ai/discover', { method: 'POST', body: JSON.stringify({ use_case: useCase }) }),
  },
  jobs: {
    list: () => request<any[]>('/jobs'),
    logs: (params?: Record<string, string>) => {
      const qs = params ? '?' + new URLSearchParams(params).toString() : '';
      return request<any[]>(`/jobs/logs${qs}`);
    },
    stats: () => request<any>('/jobs/stats'),
    run: (name: string) => request<any>(`/jobs/${encodeURIComponent(name)}/run`, { method: 'POST' }),
    update: (name: string, data: any) => request<any>(`/jobs/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
};

export function timeAgo(dateStr: string | null | undefined): string {
  if (!dateStr) return 'never';
  const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}
