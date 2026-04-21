import { Skeleton } from '../Skeleton'

interface Stats {
  mean?: number
  std?: number
  min?: number
  max?: number
  null_ratio?: number
}

interface DistributionShiftProps {
  baselineStats: Stats | null
  currentStats: Stats | null
  loading: boolean
}

interface StatRow {
  key: keyof Stats
  label: string
  isPct: boolean
}

const STAT_ROWS: StatRow[] = [
  { key: 'mean', label: 'Mean', isPct: false },
  { key: 'std', label: 'Std', isPct: false },
  { key: 'min', label: 'Min', isPct: false },
  { key: 'max', label: 'Max', isPct: false },
  { key: 'null_ratio', label: 'Null ratio', isPct: true },
]

function formatVal(val: number | undefined, isPct: boolean): string {
  if (val == null) return '-'
  if (isPct) return `${(val * 100).toFixed(1)}%`
  return val.toFixed(4)
}

function deltaColor(pctChange: number, isPct: boolean): string {
  const threshold = isPct ? 0.01 : 0.1 // 1pp for null_ratio, 10% for others
  const warningThreshold = isPct ? 0.01 : 0.3
  const abs = Math.abs(pctChange)
  if (abs <= threshold) return 'text-[var(--success)]'
  if (abs <= warningThreshold) return 'text-[var(--warning)]'
  return 'text-[var(--danger)]'
}

function computeDelta(base: number | undefined, curr: number | undefined, isPct: boolean): { display: string; colorClass: string } {
  if (base == null || curr == null) return { display: '-', colorClass: 'text-[var(--text-tertiary)]' }

  if (isPct) {
    // For null_ratio: show absolute delta in percentage points
    const absDelta = curr - base
    const sign = absDelta >= 0 ? '+' : ''
    return {
      display: `${sign}${(absDelta * 100).toFixed(1)}pp`,
      colorClass: deltaColor(absDelta, true),
    }
  }

  // For numeric stats: show percentage change
  if (base === 0) {
    if (curr === 0) return { display: '0%', colorClass: 'text-[var(--success)]' }
    return { display: 'N/A', colorClass: 'text-[var(--text-tertiary)]' }
  }
  const pctChange = (curr - base) / Math.abs(base)
  const sign = pctChange >= 0 ? '+' : ''
  return {
    display: `${sign}${(pctChange * 100).toFixed(0)}%`,
    colorClass: deltaColor(pctChange, false),
  }
}

export function DistributionShift({ baselineStats, currentStats, loading }: DistributionShiftProps) {
  if (loading) return <Skeleton className="h-32" />

  if (!baselineStats && !currentStats) {
    return (
      <div className="flex items-center justify-center h-20 text-xs text-[var(--text-tertiary)] border border-dashed border-[var(--border-default)] rounded-lg">
        No baseline or current stats available
      </div>
    )
  }

  const base = baselineStats || {}
  const curr = currentStats || {}

  return (
    <div className="mb-3">
      <p className="text-xs font-medium text-[var(--text-secondary)] mb-2">Distribution Comparison</p>
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-[var(--text-tertiary)] border-b border-[var(--border-subtle)]">
            <th className="text-left py-1 font-medium">Metric</th>
            <th className="text-right py-1 font-medium">Baseline</th>
            <th className="text-right py-1 font-medium">Current</th>
            <th className="text-right py-1 font-medium">Delta</th>
          </tr>
        </thead>
        <tbody>
          {STAT_ROWS.map(({ key, label, isPct }) => {
            const baseVal = base[key]
            const currVal = curr[key]
            const delta = computeDelta(baseVal, currVal, isPct)
            return (
              <tr key={key} className="border-b border-[var(--border-subtle)]">
                <td className="py-1.5 font-medium text-[var(--text-secondary)]">{label}</td>
                <td className="py-1.5 text-right font-mono">{formatVal(baseVal, isPct)}</td>
                <td className="py-1.5 text-right font-mono">{formatVal(currVal, isPct)}</td>
                <td className={`py-1.5 text-right font-mono font-semibold ${delta.colorClass}`}>{delta.display}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
