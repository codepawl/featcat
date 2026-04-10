import { useState } from 'react'
import { ChevronDown, ChevronRight, Brain, Loader2 } from 'lucide-react'

interface Props {
  content: string
  isDone: boolean
}

export function ThinkingBlock({ content, isDone }: Props) {
  const [isOpen, setIsOpen] = useState(false)

  if (!content && !isDone) return null

  return (
    <div className="mb-3 border border-[var(--border-subtle)] rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] transition-colors"
      >
        {isDone ? (
          <Brain size={14} className="text-green-500 shrink-0" />
        ) : (
          <Loader2 size={14} className="text-amber-500 animate-spin shrink-0" />
        )}
        <span className="flex-1 text-left">
          {isDone ? 'Thought process' : 'Thinking...'}
        </span>
        {content && (
          isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        )}
      </button>
      {isOpen && content && (
        <div className="px-3 py-2 text-xs font-mono text-[var(--text-tertiary)] whitespace-pre-wrap max-h-48 overflow-y-auto border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] animate-fade-in">
          {content}
        </div>
      )}
    </div>
  )
}
