import { useState, useRef, useEffect } from 'react'
import { Send, Sparkles, BarChart3, Activity, Loader2, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useChatStore } from '../hooks/useChatStore'
import { ChatMessage } from '../components/ChatMessage'
import { ThinkingBlock } from '../components/ThinkingBlock'
import type { ChatMessage as ChatMsg } from '../stores/chatStore'

function ResultTable({ data }: { data: any }) {
  if (!data) return null
  const results = data.results || []
  const existingFeatures = data.existing_features || []
  const suggestions = data.new_feature_suggestions || []

  return (
    <div className="space-y-3">
      {results.length > 0 && (
        <table className="w-full text-[13px] border-collapse">
          <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
            <th className="text-left py-1 font-medium">Feature</th>
            <th className="text-right py-1 font-medium">Score</th>
            <th className="text-left py-1 font-medium">Reason</th>
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
        <p className="text-[var(--text-tertiary)] italic text-sm">No matching features found.</p>
      )}
      {data.interpretation && <p className="text-xs text-[var(--text-secondary)]">{data.interpretation}</p>}
      {data.follow_up && <p className="text-xs text-blue-500">Try: {data.follow_up}</p>}
      {data.summary && <p className="text-sm text-[var(--text-secondary)] mt-2">{data.summary}</p>}

      {existingFeatures.length > 0 && (
        <>
          <h4 className="text-xs font-semibold mt-3">Relevant features</h4>
          <table className="w-full text-[13px] border-collapse">
            <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
              <th className="text-left py-1 font-medium">Name</th>
              <th className="text-right py-1 font-medium">Relevance</th>
              <th className="text-left py-1 font-medium">Reason</th>
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
          <h4 className="text-xs font-semibold mt-3">Suggested new features</h4>
          <div className="space-y-2">
            {suggestions.map((s: any, i: number) => (
              <div key={i} className="p-3 bg-[var(--bg-secondary)] rounded-lg border-l-2 border-accent">
                <span className="font-medium text-sm">{s.name}</span>
                <span className="text-[11px] text-[var(--text-tertiary)] ml-2">from {s.source}</span>
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

export function Chat() {
  const { messages, addMessage, updateLastMessage, appendToLastMessage, clear } = useChatStore()
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    api.health().then((d: Record<string, unknown>) => setLlmAvailable(!!d.llm)).catch(() => setLlmAvailable(false))
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(scrollToBottom, [messages])

  const send = () => {
    const q = input.trim()
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

  const streamQuery = (query: string) => {
    esRef.current?.close()
    const es = new EventSource(`/api/ai/ask/stream?query=${encodeURIComponent(query)}`)
    esRef.current = es

    es.onmessage = (event) => {
      const data = JSON.parse(event.data)
      switch (data.type) {
        case 'thinking_start':
          appendToLastMessage('thinking', '')
          break
        case 'thinking':
          appendToLastMessage('thinking', data.content)
          break
        case 'thinking_end':
          updateLastMessage({ isDoneThinking: true })
          break
        case 'token':
          appendToLastMessage('content', data.content)
          break
        case 'result':
          updateLastMessage({ result: data.content })
          break
        case 'done': {
          const last = messages[messages.length - 1]
          const hasContent = last?.content?.trim() || last?.result || last?.html
          if (!hasContent) {
            updateLastMessage({
              content: '\u26a0 LLM returned an empty response. Try again or check /api/health.',
              isStreaming: false,
            })
          } else {
            updateLastMessage({ isStreaming: false })
          }
          es.close()
          setBusy(false)
          break
        }
        case 'error':
          updateLastMessage({ content: `Error: ${data.content}`, isStreaming: false })
          es.close()
          setBusy(false)
          break
      }
    }

    es.onerror = () => {
      es.close()
      // Fallback to non-streaming
      api.ai.ask(query)
        .then((data) => {
          if (!data || (Array.isArray(data.results) && data.results.length === 0 && !data.interpretation)) {
            updateLastMessage({
              content: '\u26a0 No response received. The LLM may be unavailable or still loading.',
              isStreaming: false,
            })
          } else {
            updateLastMessage({ result: data, isStreaming: false })
          }
        })
        .catch(() => updateLastMessage({
          content: '\u26a0 Connection lost. LLM server may be unavailable.',
          isStreaming: false,
        }))
        .finally(() => setBusy(false))
    }
  }

  const handleDiscover = async (useCase: string) => {
    addMessage({ role: 'user', content: `/discover ${useCase}` })
    try {
      const data = await api.ai.discover(useCase)
      addMessage({ role: 'ai', content: '', result: data })
    } catch (e: any) {
      addMessage({ role: 'ai', content: `Error: ${e.message}` })
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
      addMessage({ role: 'ai', content: `Error: ${e instanceof Error ? e.message : String(e)}` })
    }
    setBusy(false)
  }

  const handleStats = async () => {
    addMessage({ role: 'user', content: '/stats' })
    try {
      const s = await api.stats()
      const html = `<div class="grid grid-cols-4 gap-3 text-center"><div><div class="text-lg font-semibold font-mono">${s.total_features || s.features || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">Features</div></div><div><div class="text-lg font-semibold font-mono">${s.sources || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">Sources</div></div><div><div class="text-lg font-semibold font-mono">${s.coverage ? Math.round(s.coverage) : 0}%</div><div class="text-[11px] text-[var(--text-tertiary)]">Coverage</div></div><div><div class="text-lg font-semibold font-mono">${s.documented || 0}/${s.total_features || s.features || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">Documented</div></div></div>`
      addMessage({ role: 'ai', content: '', html })
    } catch (e: any) {
      addMessage({ role: 'ai', content: `Error: ${e.message}` })
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
          <Loader2 size={14} className="animate-spin" /> Generating response...
        </div>
      )}
      {msg.result && <ResultTable data={msg.result} />}
      {!msg.result && msg.html && <div dangerouslySetInnerHTML={{ __html: msg.html }} />}
      {!msg.result && !msg.html && msg.content && (
        tryParseResult(msg.content)
          ? <ResultTable data={tryParseResult(msg.content)} />
          : msg.content.startsWith('\u26a0')
            ? <div className="text-amber-400 text-sm italic">{msg.content}</div>
            : <span>{msg.content}</span>
      )}
    </>
  )

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 48px)' }}>
      {llmAvailable === false && (
        <div className="bg-amber-900/30 border-b border-amber-500/40 px-4 py-2 text-amber-300 text-sm flex items-center gap-2">
          <span>{'\u26a0'}</span> LLM is not available. AI responses may be limited to keyword search only.
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-4">
        {messages.map((m) => (
          <ChatMessage key={m.id} role={m.role}>
            {m.role === 'user' ? m.content : renderAiContent(m)}
          </ChatMessage>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
        <div className="flex gap-2 mb-2">
          {[
            { label: 'Discover', query: 'discover: ', icon: Sparkles },
            { label: 'Check Drift', query: 'which features have drifted?', icon: Activity },
            { label: 'Stats', query: '/stats', icon: BarChart3 },
          ].map((s) => (
            <button key={s.label} onClick={() => setInput(s.query)}
              className="flex items-center gap-1 px-3 py-1 text-[11px] border border-[var(--border-default)] rounded-md bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] transition-colors">
              <s.icon size={12} /> {s.label}
            </button>
          ))}
          <button onClick={clear} title="Clear chat"
            className="ml-auto flex items-center gap-1 px-3 py-1 text-[11px] text-[var(--text-tertiary)] border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)] transition-colors">
            <Trash2 size={12} /> Clear
          </button>
        </div>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
            placeholder="Ask about features..."
            disabled={busy}
            className="flex-1 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none disabled:opacity-50"
          />
          <button onClick={send} disabled={busy || !input.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium disabled:opacity-50 hover:bg-accent-emphasis transition-colors">
            {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
