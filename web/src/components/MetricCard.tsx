import type { LucideIcon } from 'lucide-react'

interface Props {
  label: string
  value: string | number
  color?: 'default' | 'success' | 'warning' | 'danger'
  progress?: number
  icon?: LucideIcon
}

const colorMap = {
  default: 'text-[var(--text-primary)]',
  success: 'text-green-600 dark:text-green-400',
  warning: 'text-amber-600 dark:text-amber-400',
  danger: 'text-red-600 dark:text-red-400',
}

export function MetricCard({ label, value, color = 'default', progress, icon: Icon }: Props) {
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg p-4 hover:shadow-md transition-all hover:-translate-y-0.5">
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-tertiary)] uppercase tracking-wider mb-1">
        {Icon && <Icon size={14} />}
        {label}
      </div>
      <div className={`text-2xl font-semibold font-mono ${colorMap[color]}`}>{value}</div>
      {progress !== undefined && (
        <div className="h-1 bg-[var(--border-subtle)] rounded-full mt-2">
          <div className="h-full bg-accent rounded-full transition-all duration-500" style={{ width: `${Math.min(100, progress)}%` }} />
        </div>
      )}
    </div>
  )
}
