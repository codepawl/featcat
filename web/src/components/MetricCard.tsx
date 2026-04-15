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
  success: 'text-green-500',
  warning: 'text-amber-500',
  danger: 'text-red-500',
}

export function MetricCard({ label, value, icon: Icon, color = 'default', progress }: Props) {
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-4 hover:border-[var(--border-default)] hover:-translate-y-0.5 hover:shadow-md transition-all duration-200">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)] font-mono">{label}</span>
        {Icon && <Icon size={14} className="text-[var(--text-tertiary)]" strokeWidth={1.5} />}
      </div>
      <div className={`text-2xl font-semibold font-mono tracking-tight ${colorClasses[color]}`}>
        {value}
      </div>
      {progress != null && (
        <div className="mt-2.5 h-1 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
          <div
            className="h-full rounded-full bg-accent transition-all duration-700"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
      )}
    </div>
  )
}
