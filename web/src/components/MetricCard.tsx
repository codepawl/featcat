import type { LucideIcon } from 'lucide-react'

interface Props {
  label: string
  value: string | number
  icon?: LucideIcon
  color?: 'default' | 'success' | 'warning' | 'danger'
  progress?: number
}

const colorClasses: Record<string, string> = {
  default: 'text-[var(--text-primary)]',
  success: 'text-[var(--success)]',
  warning: 'text-[var(--warning)]',
  danger: 'text-[var(--danger)]',
}

export function MetricCard({ label, value, icon: Icon, color = 'default', progress }: Props) {
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-4 transition-colors hover:border-[var(--border-muted)]">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">{label}</span>
        {Icon && <Icon size={14} className="text-[var(--text-tertiary)]" strokeWidth={1.5} />}
      </div>
      <div className={`text-2xl font-semibold tracking-tight ${colorClasses[color]}`}>
        {value}
      </div>
      {progress != null && (
        <div className="mt-2.5 h-1.5 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--accent)]"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}
    </div>
  )
}
