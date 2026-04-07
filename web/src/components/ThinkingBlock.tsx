interface Props { content: string; isDone: boolean; }

export function ThinkingBlock({ content, isDone }: Props) {
  if (!content) return null;
  return (
    <details className="mb-2 border border-[var(--border-subtle)] rounded-lg text-sm">
      <summary className="px-3 py-2 cursor-pointer text-[var(--text-tertiary)] flex items-center gap-2 hover:bg-[var(--bg-secondary)] rounded-lg select-none">
        <span className={`w-2 h-2 rounded-full ${isDone ? 'bg-green-500' : 'bg-amber-500 animate-breathe'}`} />
        {isDone ? 'Thought for a moment' : 'Reasoning...'}
      </summary>
      <div className="px-3 py-2 text-xs text-[var(--text-tertiary)] font-mono whitespace-pre-wrap max-h-48 overflow-y-auto border-t border-[var(--border-subtle)]">
        {content}
      </div>
    </details>
  );
}
