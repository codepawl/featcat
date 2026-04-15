import type { LucideIcon } from 'lucide-react'

const styles: Record<string, string> = {
  success: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',
  warning: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400',
  danger: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
  info: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400',
  default: 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]',
  // Aliases
  healthy: 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400',
  critical: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
  error: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400',
}

interface Props {
  variant?: string
  children: React.ReactNode
  icon?: LucideIcon
}

export function Badge({ variant = 'default', children, icon: Icon }: Props) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono font-medium ${styles[variant] || styles.default}`}>
      {Icon && <Icon size={12} strokeWidth={1.8} />}
      {children}
    </span>
  )
}
