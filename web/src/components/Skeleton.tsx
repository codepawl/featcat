export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-gradient-to-r from-[var(--bg-secondary)] via-[var(--bg-tertiary)] to-[var(--bg-secondary)] bg-[length:200%_100%] animate-shimmer rounded-xl ${className}`} />
  )
}
