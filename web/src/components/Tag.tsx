export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block text-[11px] px-2 py-0.5 rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-mono">
      {children}
    </span>
  );
}
