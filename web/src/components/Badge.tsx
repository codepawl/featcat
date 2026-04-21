import type { LucideIcon } from 'lucide-react'

const SUCCESS = 'bg-[var(--success-subtle-bg)] text-[var(--success)] border border-[var(--success-subtle-bg)]'
const WARNING = 'bg-[var(--warning-subtle-bg)] text-[var(--warning)] border border-[var(--warning-subtle-bg)]'
const DANGER = 'bg-[var(--danger-subtle-bg)] text-[var(--danger)] border border-[var(--danger-subtle-bg)]'
const INFO = 'bg-[var(--accent-subtle-bg)] text-[var(--accent)] border border-[var(--accent-subtle-bg)]'
const DEFAULT = 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] border border-transparent'

const styles: Record<string, string> = {
  success: SUCCESS,
  warning: WARNING,
  danger: DANGER,
  info: INFO,
  default: DEFAULT,
  healthy: SUCCESS,
  critical: DANGER,
  error: DANGER,
  running: INFO,
}

interface Props {
  variant?: string
  children: React.ReactNode
  icon?: LucideIcon
}

export function Badge({ variant = 'default', children, icon: Icon }: Props) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${styles[variant] || styles.default}`}>
      {Icon && <Icon size={12} strokeWidth={1.8} />}
      {children}
    </span>
  )
}
