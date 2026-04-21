import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Sparkles, Activity, Search, Lightbulb, Bot, Loader2, Trash2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { useChatStore } from '../hooks/useChatStore'
import { ChatMessage } from '../components/ChatMessage'
import { ThinkingBlock } from '../components/ThinkingBlock'
import { chatStore } from '../stores/chatStore'
import type { ChatMessage as ChatMsg } from '../stores/chatStore'

function ResultTable({ data }: { data: any }) {
  const { t } = useTranslation('chat')
  if (!data) return null
  const results = data.results || []
  const existingFeatures = data.existing_features || []
  const suggestions = data.new_feature_suggestions || []

  return (
    <div className="space-y-3">
      {results.length > 0 && (
        <table className="w-full text-[13px] border-collapse">
          <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
            <th className="text-left py-1 font-medium">{t('result_table.feature')}</th>
            <th className="text-right py-1 font-medium">{t('result_table.score')}</th>
            <th className="text-left py-1 font-medium">{t('result_table.reason')}</th>
          </tr></thead>
          <tbody>
            {results.map((r: any, i: number) => (
              <tr key={i} className="border-b border-[var(--border-subtle)]">
                <td className="py-1.5"><code className="text-xs bg-[var(--code-bg)] px-1.5 py-0.5 rounded font-mono">{r.feature || r.name}</code></td>
                <td className="py-1.5 text-right font-mono">{typeof r.score === 'number' ? Math.round(r.score * 100) + '%' : r.score}</td>
                <td className="py-1.5 text-[var(--text-secondary)]">{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {results.length === 0 && !existingFeatures.length && !suggestions.length && (
        <p className="text-[var(--text-tertiary)] italic text-sm">{t('result_table.no_matches')}</p>
      )}
      {data.interpretation && <p className="text-xs text-[var(--text-secondary)]">{data.interpretation}</p>}
      {data.follow_up && <p className="text-xs text-[var(--accent)]">{t('result_table.try_follow_up', { text: data.follow_up })}</p>}
      {data.summary && <p className="text-sm text-[var(--text-secondary)] mt-2">{data.summary}</p>}

      {existingFeatures.length > 0 && (
        <>
          <h4 className="text-xs font-semibold mt-3">{t('result_table.relevant_features')}</h4>
          <table className="w-full text-[13px] border-collapse">
            <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
              <th className="text-left py-1 font-medium">{t('result_table.name')}</th>
              <th className="text-right py-1 font-medium">{t('result_table.relevance')}</th>
              <th className="text-left py-1 font-medium">{t('result_table.reason')}</th>
            </tr></thead>
            <tbody>
              {existingFeatures.map((f: any, i: number) => (
                <tr key={i} className="border-b border-[var(--border-subtle)]">
                  <td className="py-1.5"><code className="text-xs bg-[var(--code-bg)] px-1.5 py-0.5 rounded font-mono">{f.name}</code></td>
                  <td className="py-1.5 text-right font-mono">{typeof f.relevance === 'number' ? Math.round(f.relevance * 100) + '%' : f.relevance}</td>
                  <td className="py-1.5 text-[var(--text-secondary)]">{f.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {suggestions.length > 0 && (
        <>
          <h4 className="text-xs font-semibold mt-3">{t('result_table.suggested_new')}</h4>
          <div className="space-y-2">
            {suggestions.map((s: any, i: number) => (
              <div key={i} className="p-3 bg-[var(--bg-secondary)] rounded-lg border-l-2 border-accent">
                <span className="font-medium text-sm">{s.name}</span>
                <span className="text-[11px] text-[var(--text-tertiary)] ml-2">{t('result_table.from_source', { source: s.source })}</span>
                <p className="text-xs text-[var(--text-secondary)] mt-1">{s.reason}</p>
                {s.column_expression && <code className="text-[11px] bg-[var(--code-bg)] px-1.5 py-0.5 rounded mt-1 inline-block font-mono">{s.column_expression}</code>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function tryParseResult(text: string): any | null {
  try {
    const data = JSON.parse(text)
    if (data.results || data.existing_features || data.new_feature_suggestions) return data
  } catch { /* not JSON */ }
  return null
}

const SUGGESTIONS = [
  { icon: Sparkles,  titleKey: 'suggestions.discover.title', exampleKey: 'suggestions.discover.example', promptKey: 'suggestions.discover.prompt' },
  { icon: Activity,  titleKey: 'suggestions.drift.title',    exampleKey: 'suggestions.drift.example',    promptKey: 'suggestions.drift.prompt' },
  { icon: Search,    titleKey: 'suggestions.similar.title',  exampleKey: 'suggestions.similar.example',  promptKey: 'suggestions.similar.prompt' },
  { icon: Lightbulb, titleKey: 'suggestions.improve.title',  exampleKey: 'suggestions.improve.example',  promptKey: 'suggestions.improve.prompt' },
] as const

function SuggestionCard({ icon: Icon, title, example, onClick }: { icon: LucideIcon; title: string; example: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-left p-4 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg hover:border-[var(--border-muted)] hover:bg-[var(--bg-secondary)] transition-colors"
    >
      <Icon size={18} className="text-[var(--accent)] mb-2" />
      <div className="text-sm font-medium text-[var(--text-primary)] mb-1">{title}</div>
      <div className="text-xs text-[var(--text-tertiary)] leading-relaxed">{example}</div>
    </button>
  )
}

export function Chat() {
  const { t } = useTranslation('chat')
  const { messages, addMessage, updateLastMessage, appendToLastMessage, clear } = useChatStore()
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const sessionIdRef = useRef<string | null>(null)

  useEffect(() => {
    const check = () => {
      invalidateCache('/health')
      api.health().then((d: Record<string, unknown>) => setLlmAvailable(!!d.llm)).catch(() => setLlmAvailable(false))
    }
    check()
    const id = setInterval(check, 15_000)
    return () => clearInterval(id)
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(scrollToBottom, [messages])

  const send = (overrideInput?: string) => {
    const q = (overrideInput ?? input).trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)

    if (q.startsWith('/discover ') || q.startsWith('discover: ')) {
      handleDiscover(q.replace(/^(\/discover |discover: )/, ''))
      return
    }
    if (q.startsWith('/monitor')) { handleMonitor(); return }
    if (q.startsWith('/stats')) { handleStats(); return }

    addMessage({ role: 'user', content: q })
    addMessage({ role: 'ai', content: '', isStreaming: true })
    streamQuery(q)
  }

  const streamQuery = async (query: string) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: sessionIdRef.current }),
        signal: controller.signal,
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        updateLastMessage({ content: t('errors.prefix', { message: err.detail || res.statusText }), isStreaming: false })
        setBusy(false)
        return
      }

      const sid = res.headers.get('X-Session-Id')
      if (sid) sessionIdRef.current = sid

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let eventData = ''

      const dispatch = (raw: string): boolean => {
        let data: any
        try { data = JSON.parse(raw) } catch { return false }
        switch (data.type) {
          case 'thinking_start':
            appendToLastMessage('thinking', '')
            return false
          case 'thinking':
            appendToLastMessage('thinking', data.content)
            return false
          case 'thinking_end':
            updateLastMessage({ isDoneThinking: true })
            return false
          case 'tool_call':
            appendToLastMessage('thinking', `\nUsing tool: ${data.name}...`)
            return false
          case 'tool_result':
            return false
          case 'token':
            appendToLastMessage('content', data.content)
            return false
          case 'result':
            updateLastMessage({ result: data.content })
            return false
          case 'done': {
            const current = chatStore.getMessages()
            const last = current[current.length - 1]
            const hasContent = last?.content?.trim() || last?.result || last?.html
            if (!hasContent) {
              updateLastMessage({
                content: '⚠ ' + t('status.empty_response'),
                isStreaming: false,
              })
            } else {
              updateLastMessage({ isStreaming: false })
            }
            setBusy(false)
            return true
          }
          case 'error':
            updateLastMessage({ content: t('errors.prefix', { message: data.content }), isStreaming: false })
            setBusy(false)
            return true
        }
        return false
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          if (eventData && dispatch(eventData)) return
          break
        }
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split(/\r?\n/)
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            eventData = line.slice(6)
          } else if (line === '' && eventData) {
            const stop = dispatch(eventData)
            eventData = ''
            if (stop) return
          }
        }
      }

      updateLastMessage({ isStreaming: false })
      setBusy(false)
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      updateLastMessage({
        content: '⚠ ' + t('status.connection_lost'),
        isStreaming: false,
      })
      setBusy(false)
    }
  }

  const handleDiscover = async (useCase: string) => {
    addMessage({ role: 'user', content: `/discover ${useCase}` })
    try {
      const data = await api.ai.discover(useCase)
      addMessage({ role: 'ai', content: '', result: data })
    } catch (e: any) {
      addMessage({ role: 'ai', content: t('errors.prefix', { message: e.message }) })
    }
    setBusy(false)
  }

  const handleMonitor = async () => {
    addMessage({ role: 'user', content: '/monitor' })
    try {
      const data = await api.monitor.check()
      const d = data as Record<string, unknown>
      const html = `<p><strong>${d.healthy || 0}</strong> healthy, <strong>${d.warnings || 0}</strong> warnings, <strong>${d.critical || 0}</strong> critical</p>`
      const details = (d.details || []) as { feature: string; psi: number; severity: string }[]
      addMessage({
        role: 'ai', content: '', html,
        result: details.length ? { results: details.map(dd => ({ feature: dd.feature, score: dd.psi, reason: dd.severity })) } : undefined,
      })
    } catch (e) {
      addMessage({ role: 'ai', content: t('errors.prefix', { message: e instanceof Error ? e.message : String(e) }) })
    }
    setBusy(false)
  }

  const handleStats = async () => {
    addMessage({ role: 'user', content: '/stats' })
    try {
      const s = await api.stats()
      const html = `<div class="grid grid-cols-4 gap-3 text-center"><div><div class="text-lg font-semibold font-mono">${s.total_features || s.features || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">${t('stats_labels.features', { ns: 'dashboard', defaultValue: 'Features' })}</div></div><div><div class="text-lg font-semibold font-mono">${s.sources || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">${t('stats.sources', { ns: 'dashboard' })}</div></div><div><div class="text-lg font-semibold font-mono">${s.coverage ? Math.round(s.coverage) : 0}%</div><div class="text-[11px] text-[var(--text-tertiary)]">${t('stats.doc_coverage', { ns: 'dashboard' })}</div></div><div><div class="text-lg font-semibold font-mono">${s.documented || 0}/${s.total_features || s.features || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">${t('documentation.section_title', { ns: 'features', defaultValue: 'Documented' })}</div></div></div>`
      addMessage({ role: 'ai', content: '', html })
    } catch (e: any) {
      addMessage({ role: 'ai', content: t('errors.prefix', { message: e.message }) })
    }
    setBusy(false)
  }

  const renderAiContent = (msg: ChatMsg) => (
    <>
      {(msg.thinking || (msg.isStreaming && !msg.content && !msg.result)) && (
        <ThinkingBlock content={msg.thinking || ''} isDone={msg.isDoneThinking ?? false} />
      )}
      {msg.isDoneThinking && msg.thinking && !msg.isStreaming && (
        <ThinkingBlock content={msg.thinking} isDone />
      )}
      {msg.isStreaming && !msg.content && !msg.thinking && !msg.result && (
        <div className="flex items-center gap-2 text-sm text-[var(--text-tertiary)]">
          <Loader2 size={14} className="animate-spin" /> {t('status.generating')}
        </div>
      )}
      {msg.result && <ResultTable data={msg.result} />}
      {!msg.result && msg.html && <div dangerouslySetInnerHTML={{ __html: msg.html }} />}
      {!msg.result && !msg.html && msg.content && (
        tryParseResult(msg.content)
          ? <ResultTable data={tryParseResult(msg.content)} />
          : msg.content.startsWith('⚠')
            ? <div className="text-[var(--warning)] text-sm italic">{msg.content}</div>
            : <span>{msg.content}</span>
      )}
    </>
  )

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 48px)' }}>
      {llmAvailable === false && (
        <div className="bg-[var(--warning-subtle-bg)] border-b border-[var(--warning-subtle-bg)] px-4 py-2 text-[var(--warning)] text-sm flex items-center gap-2">
          <span>{'⚠'}</span> {t('status.llm_unavailable')}
        </div>
      )}

      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 overflow-y-auto">
          <div className="max-w-3xl w-full text-center">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-[var(--accent-subtle-bg)] mb-6">
              <Bot size={24} className="text-[var(--accent)]" />
            </div>

            <h1 className="text-2xl font-semibold text-[var(--text-primary)] mb-2">
              {t('empty.greeting')}
            </h1>
            <p className="text-sm text-[var(--text-secondary)] mb-10">
              {t('empty.subtitle')}
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 text-left">
              {SUGGESTIONS.map((s, i) => (
                <SuggestionCard
                  key={i}
                  icon={s.icon}
                  title={t(s.titleKey)}
                  example={t(s.exampleKey)}
                  onClick={() => send(t(s.promptKey))}
                />
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-4">
          {messages.map((m) => (
            <ChatMessage key={m.id} role={m.role}>
              {m.role === 'user' ? m.content : renderAiContent(m)}
            </ChatMessage>
          ))}
          <div ref={messagesEndRef} />
        </div>
      )}

      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
        {!isEmpty && (
          <div className="flex gap-2 mb-2">
            <button onClick={() => { clear(); sessionIdRef.current = null }} title={t('input.clear_title')}
              className="ml-auto flex items-center gap-1 px-3 py-1 text-[11px] text-[var(--text-tertiary)] border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)] transition-colors">
              <Trash2 size={12} /> {t('input.clear')}
            </button>
          </div>
        )}
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder={t('input.placeholder')}
            disabled={busy}
            className="flex-1 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none disabled:opacity-50"
          />
          <button onClick={() => send()} disabled={busy || !input.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium disabled:opacity-50 hover:bg-accent-emphasis transition-colors">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {t('input.send')}
          </button>
        </div>
      </div>
    </div>
  )
}
