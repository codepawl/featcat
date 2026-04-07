/* featcat API client */

const API_BASE = '/api';

async function api(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
    };
    const res = await fetch(url, config);
    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(error.detail || `API error: ${res.status}`);
    }
    return res.json();
}

const featcat = {
    health: () => api('/health'),
    stats: () => api('/stats'),

    sources: {
        list: () => api('/sources'),
        get: (name) => api(`/sources/${encodeURIComponent(name)}`),
        add: (data) => api('/sources', { method: 'POST', body: JSON.stringify(data) }),
        scan: (name) => api(`/sources/${encodeURIComponent(name)}/scan`, { method: 'POST' }),
    },

    features: {
        list: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return api(`/features${qs ? '?' + qs : ''}`);
        },
        get: (name) => api(`/features/${encodeURIComponent(name)}`),
        update: (name, data) => api(`/features/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
    },

    docs: {
        stats: () => api('/docs/stats'),
        generate: (data) => api('/docs/generate', { method: 'POST', body: JSON.stringify(data) }),
        get: (name) => api(`/docs/${encodeURIComponent(name)}`),
    },

    monitor: {
        check: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return api(`/monitor/check${qs ? '?' + qs : ''}`);
        },
        baseline: () => api('/monitor/baseline', { method: 'POST' }),
        report: () => api('/monitor/report'),
    },

    jobs: {
        list: () => api('/jobs'),
        logs: (params = {}) => {
            const qs = new URLSearchParams(params).toString();
            return api(`/jobs/logs${qs ? '?' + qs : ''}`);
        },
        run: (name) => api(`/jobs/${encodeURIComponent(name)}/run`, { method: 'POST' }),
        update: (name, data) => api(`/jobs/${encodeURIComponent(name)}`, { method: 'PATCH', body: JSON.stringify(data) }),
        stats: () => api('/jobs/stats'),
    },

    ai: {
        discover: (useCase) => api('/ai/discover', { method: 'POST', body: JSON.stringify({ use_case: useCase }) }),
        ask: (query) => api('/ai/ask', { method: 'POST', body: JSON.stringify({ query }) }),
        stream: (query, callbacks) => {
            const url = `${API_BASE}/ai/ask/stream?query=${encodeURIComponent(query)}`;
            const source = new EventSource(url);
            source.onmessage = (event) => {
                const data = JSON.parse(event.data);
                switch (data.type) {
                    case 'thinking_start':
                        if (callbacks.onThinkingStart) callbacks.onThinkingStart();
                        break;
                    case 'thinking':
                        if (callbacks.onThinking) callbacks.onThinking(data.content);
                        break;
                    case 'thinking_end':
                        if (callbacks.onThinkingEnd) callbacks.onThinkingEnd();
                        break;
                    case 'token':
                        if (callbacks.onToken) callbacks.onToken(data.content);
                        break;
                    case 'result':
                        if (callbacks.onResult) callbacks.onResult(data.content);
                        break;
                    case 'error':
                        if (callbacks.onError) callbacks.onError(new Error(data.content));
                        break;
                    case 'done':
                        source.close();
                        if (callbacks.onDone) callbacks.onDone();
                        break;
                }
            };
            source.onerror = () => {
                source.close();
                if (callbacks.onError) callbacks.onError(new Error('SSE connection failed'));
            };
            return source;
        },
    },
};

/* Utility helpers */

function timeAgo(dateStr) {
    if (!dateStr) return 'never';
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function checkHealth() {
    featcat.health().then(data => {
        const serverDot = document.getElementById('server-dot');
        const llmDot = document.getElementById('llm-dot');
        const llmStatus = document.getElementById('llm-status');
        if (serverDot) serverDot.className = 'status-dot green';
        if (llmDot) llmDot.className = data.llm ? 'status-dot green' : 'status-dot red';
        if (llmStatus) llmStatus.textContent = data.llm ? data.model || 'connected' : 'offline';
    }).catch(() => {
        const serverDot = document.getElementById('server-dot');
        if (serverDot) serverDot.className = 'status-dot red';
    });
}

// Check health on load
document.addEventListener('DOMContentLoaded', checkHealth);
