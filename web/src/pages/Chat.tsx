import { useState, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Send, Sparkles, Activity, Search, Lightbulb, Brain, Loader2, Trash2, ArrowUpRight, AlertCircle, RotateCw } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { useChatStore } from '../hooks/useChatStore'
import { ChatMessage } from '../components/ChatMessage'
import { Reasoning, ReasoningTrigger, ReasoningContent } from '@/components/ai-elements/reasoning'
import { Tool, ToolHeader, ToolContent, ToolInput, ToolOutput } from '@/components/ai-elements/tool'
import { Response } from '@/components/ai-elements/response'
import { CodeBlock, CodeBlockCopyButton } from '@/components/ai-elements/code-block'
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
      {data.follow_up && <p className="text-xs text-[var(--brand)]">{t('result_table.try_follow_up', { text: data.follow_up })}</p>}
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
              <div key={i} className="p-3 bg-[var(--bg-secondary)] rounded-lg border-l-2 border-brand">
                <span className="font-medium text-sm">{s.name}</span>
                <span className="text-[11px] text-[var(--text-tertiary)] ml-2">{t('result_table.from_source', { source: s.source })}</span>
                <p className="text-xs text-[var(--text-secondary)] mt-1">{s.reason}</p>
                {s.column_expression && (
                  <div className="mt-2">
                    <CodeBlock code={s.column_expression} language="sql">
                      <CodeBlockCopyButton />
                    </CodeBlock>
                  </div>
                )}
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
      className="group relative text-left p-5 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-xl hover:border-brand/40 hover:bg-[var(--bg-secondary)] hover:shadow-[0_1px_2px_rgba(0,0,0,0.04),0_8px_24px_-12px_rgba(0,0,0,0.08)] transition-all duration-200"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="w-9 h-9 rounded-lg bg-brand/10 text-brand flex items-center justify-center group-hover:bg-brand/15 transition-colors">
          <Icon size={18} strokeWidth={1.75} />
        </div>
        <ArrowUpRight
          size={16}
          className="text-[var(--text-tertiary)] opacity-0 -translate-x-1 translate-y-1 group-hover:opacity-100 group-hover:translate-x-0 group-hover:translate-y-0 group-hover:text-brand transition-all duration-200"
        />
      </div>
      <div className="text-[14px] font-medium text-[var(--text-primary)] mb-1 tracking-tight">{title}</div>
      <div className="text-[12.5px] text-[var(--text-tertiary)] leading-relaxed italic">{example}</div>
    </button>
  )
}

export function Chat() {
  const { t } = useTranslation('chat')
  const { messages, addMessage, updateLastMessage, appendToLastMessage, upsertToolCall, popLastMessage, clear } = useChatStore()
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
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
    // Auto-resize keeps the textarea expanded after typing; clearing the
    // value alone doesn't shrink it. Reset height explicitly so the input
    // collapses back to a single row after send.
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
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
        updateLastMessage({
          content: err.detail || res.statusText,
          error: true,
          isStreaming: false,
        })
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
          case 'tool_start': {
            const id = data.id || data.tool || `tool-${Date.now()}`
            upsertToolCall(id, { name: data.tool || data.name || 'tool', state: 'input-available', input: data.input })
            return false
          }
          case 'tool_call': {
            const id = data.id || data.name || `tool-${Date.now()}`
            upsertToolCall(id, { name: data.name || 'tool', state: 'input-available', input: data.input ?? data.args })
            return false
          }
          case 'tool_result': {
            const id = data.id || data.tool || data.name || `tool-${Date.now()}`
            const isError = data.error || data.status === 'error'
            upsertToolCall(id, {
              state: isError ? 'output-error' : 'output-available',
              output: data.result ?? data.content ?? data.output,
              error: isError ? (data.error || 'Tool error') : undefined,
            })
            return false
          }
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
                content: t('status.empty_response'),
                error: true,
                isStreaming: false,
              })
            } else {
              updateLastMessage({ isStreaming: false })
            }
            setBusy(false)
            return true
          }
          case 'error':
            updateLastMessage({
              content: data.content,
              error: true,
              isStreaming: false,
            })
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
        content: t('status.connection_lost'),
        error: true,
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
      addMessage({ role: 'ai', content: e.message, error: true })
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
      addMessage({
        role: 'ai',
        content: e instanceof Error ? e.message : String(e),
        error: true,
      })
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
      addMessage({ role: 'ai', content: e.message, error: true })
    }
    setBusy(false)
  }

  const retryLast = () => {
    if (busy) return
    const current = chatStore.getMessages()
    if (current.length < 2) return
    const lastAi = current[current.length - 1]
    const lastUser = current[current.length - 2]
    if (!lastAi.error || lastUser.role !== 'user') return
    const query = lastUser.content
    popLastMessage()
    setBusy(true)
    addMessage({ role: 'ai', content: '', isStreaming: true })
    streamQuery(query)
  }

  const renderAiContent = (msg: ChatMsg, isLast: boolean) => {
    if (msg.error) {
      return (
        <div className="inline-flex flex-col gap-2 rounded-2xl rounded-tl-sm bg-[var(--danger-subtle-bg,var(--bg-secondary))] border border-[var(--danger)]/30 px-4 py-3 max-w-[85%]">
          <div className="flex items-center gap-2 text-[var(--danger)]">
            <AlertCircle size={14} />
            <span className="text-[12px] font-semibold uppercase tracking-wide">
              {t('errors.label')}
            </span>
          </div>
          <p className="text-[13.5px] leading-relaxed text-[var(--text-primary)] break-words">
            {msg.content}
          </p>
          {isLast && (
            <button
              onClick={retryLast}
              disabled={busy}
              className="self-start inline-flex items-center gap-1.5 mt-1 text-[12px] font-medium text-brand hover:text-brand-emphasis disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <RotateCw size={12} className={busy ? 'animate-spin' : ''} />
              {t('errors.retry')}
            </button>
          )}
        </div>
      )
    }
    return (
      <>
        {(msg.thinking || (msg.isStreaming && !msg.content && !msg.result)) && (
          <Reasoning
            className="mb-3"
            isStreaming={msg.isStreaming === true && !(msg.isDoneThinking ?? false)}
          >
            <ReasoningTrigger />
            <ReasoningContent>{msg.thinking || ''}</ReasoningContent>
          </Reasoning>
        )}
        {msg.tools && msg.tools.length > 0 && (
          <div className="mb-3 space-y-0.5">
            {msg.tools.map((tool) => (
              <Tool key={tool.id} defaultOpen={false}>
                <ToolHeader type="dynamic-tool" toolName={tool.name} state={tool.state} />
                <ToolContent>
                  {tool.input !== undefined && <ToolInput input={tool.input} />}
                  {(tool.output !== undefined || tool.error) && (
                    <ToolOutput output={tool.output} errorText={tool.error} />
                  )}
                </ToolContent>
              </Tool>
            ))}
          </div>
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
            : <Response>{msg.content}</Response>
        )}
      </>
    )
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 48px)' }}>
      {llmAvailable === false && (
        <div className="bg-[var(--warning-subtle-bg)] border-b border-[var(--warning-subtle-bg)] px-4 py-2 text-[var(--warning)] text-sm flex items-center gap-2">
          <span>{'⚠'}</span> {t('status.llm_unavailable')}
        </div>
      )}

      {isEmpty ? (
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 overflow-y-auto animate-fade-in">
          <div className="max-w-2xl w-full">
            <div className="flex flex-col items-center text-center mb-10">
              <div className="relative mb-6">
                <div
                  aria-hidden
                  className="absolute inset-0 rounded-2xl bg-brand/20 blur-2xl scale-110 opacity-60"
                />
                <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-brand/15 to-brand/5 border border-brand/20 flex items-center justify-center">
                  <Brain size={28} strokeWidth={1.5} className="text-brand" />
                </div>
              </div>

              <h1 className="text-[28px] leading-tight font-semibold text-[var(--text-primary)] tracking-tight mb-2">
                {t('empty.greeting')}
              </h1>
              <p className="text-[14px] text-[var(--text-tertiary)] max-w-md leading-relaxed">
                {t('empty.subtitle')}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
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
          {/* Reading width capped at 800px (matches ChatGPT/Claude). Both
              AI and user messages share this width; the centred container
              keeps line length comfortable on wide displays. */}
          <div className="max-w-[1200px] mx-auto">
            {messages.map((m, idx) => (
              <ChatMessage key={m.id} role={m.role}>
                {m.role === 'user' ? m.content : renderAiContent(m, idx === messages.length - 1)}
              </ChatMessage>
            ))}
            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {/* Input area — outer container has the full-width border + bg so the
          separator runs edge-to-edge. Inner 800px column carries all padding
          so the content stays centered without looking detached from the
          border above it (matches ChatGPT / Claude). */}
      <div className="border-t border-[var(--border-subtle)] bg-transparent">
        <div className="max-w-[1200px] mx-auto px-4 py-4">
          {/* Unified pill-shaped input: textarea + embedded send button. The
              container owns the focus ring so the whole pill highlights when
              the textarea is focused (ChatGPT-style). */}
          <div className="relative flex items-end gap-2 border border-[var(--border-default)] rounded-2xl bg-[var(--bg-secondary)] focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20 transition-colors">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value)
                // Auto-resize up to 200px, then scroll. Reset to 'auto' first
                // so shrink-back works when the user deletes lines.
                const el = e.target
                el.style.height = 'auto'
                el.style.height = `${Math.min(el.scrollHeight, 200)}px`
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              placeholder={t('input.placeholder')}
              disabled={busy}
              rows={1}
              className="flex-1 bg-transparent px-4 py-3 text-[14px] outline-none resize-none disabled:opacity-50 placeholder:text-[var(--text-tertiary)]"
            />
            <button
              onClick={() => send()}
              disabled={busy || !input.trim()}
              aria-label={t('input.send')}
              className="m-2 p-2 rounded-lg bg-brand text-white hover:bg-brand-emphasis disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
            >
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>

          {/* Footer: keyboard hint left, clear-chat right. Both small + muted
              so they don't compete with the input. Only shown when there's a
              conversation to clear. */}
          <div className="flex items-center justify-between mt-2 px-1 min-h-[18px]">
            <span className="text-[11px] text-[var(--text-tertiary)] hidden sm:inline">
              {t('input.hint_enter_send')}
            </span>
            {!isEmpty && (
              <button
                onClick={() => { clear(); sessionIdRef.current = null }}
                title={t('input.clear_title')}
                className="ml-auto flex items-center gap-1 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--danger)] transition-colors"
              >
                <Trash2 size={12} /> {t('input.clear_chat')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
