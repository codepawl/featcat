import { useState, useRef, useEffect } from 'react'
import { api } from '../api'
import { useSSE } from '../hooks/useSSE'
import { ChatMessage } from '../components/ChatMessage'
import { ThinkingBlock } from '../components/ThinkingBlock'
import { Badge } from '../components/Badge'

interface Message {
  role: 'user' | 'ai'
  content: string
  thinking?: string
  isDoneThinking?: boolean
  result?: any
  html?: string
}

function escapeHtml(s: string): string {
  const d = document.createElement('div')
  d.textContent = s
  return d.innerHTML
}

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
                <td className="py-1.5"><code className="text-xs bg-[var(--code-bg)] px-1.5 py-0.5 rounded">{r.feature || r.name}</code></td>
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
                  <td className="py-1.5"><code className="text-xs bg-[var(--code-bg)] px-1.5 py-0.5 rounded">{f.name}</code></td>
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
                {s.column_expression && <code className="text-[11px] bg-[var(--code-bg)] px-1.5 py-0.5 rounded mt-1 inline-block">{s.column_expression}</code>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'ai', content: 'Welcome to featcat AI Chat! Ask anything about your features.' },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const sse = useSSE()

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(scrollToBottom, [messages, sse.answer, sse.thinking])

  const send = () => {
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)

    // Slash commands
    if (q.startsWith('/discover ') || q.startsWith('discover: ')) {
      const useCase = q.replace(/^(\/discover |discover: )/, '')
      handleDiscover(useCase)
      return
    }
    if (q.startsWith('/monitor')) { handleMonitor(); return }
    if (q.startsWith('/stats')) { handleStats(); return }

    // Streaming query
    setMessages((m) => [...m, { role: 'user', content: q }])
    sse.stream(q)
  }

  // When SSE finishes, commit the message
  useEffect(() => {
    if (!sse.isStreaming && (sse.answer || sse.result || sse.thinking)) {
      setMessages((m) => [
        ...m,
        {
          role: 'ai',
          content: sse.answer,
          thinking: sse.thinking,
          isDoneThinking: sse.isDoneThinking,
          result: sse.result,
        },
      ])
      setBusy(false)
    }
  }, [sse.isStreaming])

  const handleDiscover = async (useCase: string) => {
    setMessages((m) => [...m, { role: 'user', content: `/discover ${useCase}` }])
    try {
      const data = await api.ai.discover(useCase)
      setMessages((m) => [...m, { role: 'ai', content: '', result: data }])
    } catch (e: any) {
      setMessages((m) => [...m, { role: 'ai', content: `Error: ${e.message}` }])
    }
    setBusy(false)
  }

  const handleMonitor = async () => {
    setMessages((m) => [...m, { role: 'user', content: '/monitor' }])
    try {
      const data = await api.monitor.check()
      const html = `<p><strong>${data.healthy || 0}</strong> healthy, <strong>${data.warnings || 0}</strong> warnings, <strong>${data.critical || 0}</strong> critical</p>`
      setMessages((m) => [...m, { role: 'ai', content: '', html, result: data.details?.length ? { results: data.details.map((d: any) => ({ feature: d.feature, score: d.psi, reason: d.severity })) } : undefined }])
    } catch (e: any) {
      setMessages((m) => [...m, { role: 'ai', content: `Error: ${e.message}` }])
    }
    setBusy(false)
  }

  const handleStats = async () => {
    setMessages((m) => [...m, { role: 'user', content: '/stats' }])
    try {
      const s = await api.stats()
      const html = `<div class="grid grid-cols-4 gap-3 text-center"><div><div class="text-lg font-semibold font-mono">${s.total_features || s.features || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">Features</div></div><div><div class="text-lg font-semibold font-mono">${s.sources || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">Sources</div></div><div><div class="text-lg font-semibold font-mono">${s.coverage ? Math.round(s.coverage) : 0}%</div><div class="text-[11px] text-[var(--text-tertiary)]">Coverage</div></div><div><div class="text-lg font-semibold font-mono">${s.documented || 0}/${s.total_features || s.features || 0}</div><div class="text-[11px] text-[var(--text-tertiary)]">Documented</div></div></div>`
      setMessages((m) => [...m, { role: 'ai', content: '', html }])
    } catch (e: any) {
      setMessages((m) => [...m, { role: 'ai', content: `Error: ${e.message}` }])
    }
    setBusy(false)
  }

  // Try to parse answer as JSON for structured display
  const tryParseResult = (text: string): any | null => {
    try {
      const data = JSON.parse(text)
      if (data.results || data.existing_features || data.new_feature_suggestions) return data
    } catch { /* not JSON */ }
    return null
  }

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 48px)' }}>
      <div className="flex-1 overflow-y-auto px-4">
        {messages.map((m, i) => (
          <ChatMessage key={i} role={m.role}>
            {m.thinking && <ThinkingBlock content={m.thinking} isDone={m.isDoneThinking ?? true} />}
            {m.result ? <ResultTable data={m.result} /> :
             m.html ? <div dangerouslySetInnerHTML={{ __html: m.html }} /> :
             m.content && tryParseResult(m.content) ? <ResultTable data={tryParseResult(m.content)} /> :
             <span>{m.content}</span>}
          </ChatMessage>
        ))}

        {/* Streaming message in progress */}
        {sse.isStreaming && (
          <ChatMessage role="ai">
            {sse.thinking && <ThinkingBlock content={sse.thinking} isDone={sse.isDoneThinking} />}
            {sse.answer && <div className="text-sm">{sse.answer}</div>}
            {!sse.answer && !sse.thinking && <span className="text-[var(--text-tertiary)] italic">Thinking...</span>}
          </ChatMessage>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
        <div className="flex gap-2 mb-2">
          {[
            { label: 'Discover', query: 'discover: ' },
            { label: 'Check Drift', query: 'which features have drifted?' },
            { label: 'Stats', query: '/stats' },
          ].map((s) => (
            <button key={s.label} onClick={() => setInput(s.query)}
              className="px-3 py-1 text-[11px] border border-[var(--border-default)] rounded-md bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] transition-colors">
              {s.label}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
            placeholder="Ask about features..."
            disabled={busy}
            className="flex-1 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent focus:ring-2 focus:ring-accent/20 outline-none disabled:opacity-50"
          />
          <button onClick={send} disabled={busy || !input.trim()}
            className="px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium disabled:opacity-50 hover:bg-accent-emphasis transition-colors">
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
