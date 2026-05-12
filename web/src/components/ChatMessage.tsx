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
      className={`flex gap-3 py-4 animate-slide-up items-start ${role === 'user' ? 'flex-row-reverse' : ''}`}
    >
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
          role === 'user'
            ? 'bg-brand text-white'
            : 'bg-brand/10 text-brand'
        }`}
      >
        {role === 'user' ? <User size={16} /> : <Brain size={16} />}
      </div>
      <div className={`min-w-0 flex-1 ${role === 'user' ? 'text-right' : ''}`}>
        {above && (
          <div className="mb-1.5 max-w-[85%] text-left">
            {above}
          </div>
        )}
        {role === 'user' ? (
          <div className="inline-block bg-brand text-white px-4 py-2.5 rounded-2xl rounded-br-sm text-sm max-w-[85%] text-left">
            {children}
          </div>
        ) : (
          <div className="inline-block bg-[var(--bg-secondary)] border border-[var(--border-default)] text-[var(--text-primary)] px-4 py-2.5 rounded-2xl rounded-tl-sm text-sm leading-relaxed max-w-[85%] text-left">
            {children}
          </div>
        )}
      </div>
    </div>
  )
}
