interface Props {
  role: 'user' | 'ai';
  children: React.ReactNode;
}

export function ChatMessage({ role, children }: Props) {
  return (
    <div className={`flex gap-3 py-4 animate-slide-up ${role === 'user' ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-medium shrink-0 ${
        role === 'user' ? 'bg-accent text-white' : 'bg-[var(--bg-secondary)] text-accent border border-[var(--border-subtle)]'
      }`}>
        {role === 'user' ? 'You' : 'AI'}
      </div>
      <div className="max-w-[85%] min-w-0">
        {role === 'user' ? (
          <div className="bg-accent text-white px-4 py-2.5 rounded-2xl rounded-br-sm text-sm">{children}</div>
        ) : (
          <div className="text-sm leading-relaxed">{children}</div>
        )}
      </div>
    </div>
  );
}
