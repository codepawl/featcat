export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block text-[10px] px-2 py-0.5 rounded-md bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-mono tracking-wide">
      {children}
    </span>
  )
}
