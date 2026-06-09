import { Brain, User } from 'lucide-react'

interface Props {
  role: 'user' | 'ai'
  children: React.ReactNode
  /** Optional content rendered outside the bubble, directly above it.
   *  Used for tool-call cards on AI messages so they read as metadata
   *  separate from the answer itself. */
  above?: React.ReactNode
}

/** Chat row: avatar + message content.
 *
 *  Visual tweaks vs. v1:
 *  - AI avatar uses subtle brand-tinted bg (`bg-brand/10`) instead of a
 *    bordered secondary box → matches ChatGPT/Claude visual weight.
 *  - Brain icon (lucide) replaces Bot — the spec calls for a brain glyph.
 *  - Avatar aligns to the TOP of the message content via `items-start`
 *    so multi-line responses don't push the avatar center-aligned.
 *  - User message keeps the brand-bubble; AI message is unbubbled
 *    inline text (reader-friendly, ~700px line length).
 */
export function ChatMessage({ role, children, above }: Props) {
  return (
    <div
      className={`flex gap-4.5 py-5 animate-slide-up items-start ${role === 'user' ? 'flex-row-reverse' : ''}`}
    >
      <div
        className={`w-8.5 h-8.5 rounded-xl flex items-center justify-center shrink-0 shadow-sm transition-all duration-200 ${
          role === 'user'
            ? 'bg-gradient-to-br from-brand to-brand-emphasis text-white'
            : 'bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-brand'
        }`}
      >
        {role === 'user' ? <User size={15} strokeWidth={2} /> : <Brain size={15} strokeWidth={2} />}
      </div>
      <div className={`min-w-0 flex-1 ${role === 'user' ? 'text-right' : ''}`}>
        {above && (
          <div className="mb-2 max-w-[85%] text-left">
            {above}
          </div>
        )}
        {role === 'user' ? (
          <div className="inline-block bg-gradient-to-tr from-brand to-brand-emphasis text-white px-4.5 py-3 rounded-2xl rounded-tr-sm text-[13.5px] leading-relaxed max-w-[85%] text-left shadow-sm">
            {children}
          </div>
        ) : (
          <div className="inline-block bg-[var(--bg-secondary)] text-[var(--text-primary)] px-4.5 py-3 rounded-2xl rounded-tl-sm text-[13.5px] leading-relaxed max-w-[85%] text-left shadow-sm">
            {children}
          </div>
        )}
      </div>
    </div>
  )
}
