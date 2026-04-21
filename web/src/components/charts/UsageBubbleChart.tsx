import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { Skeleton } from '../Skeleton'

interface UsageEntry {
  name: string
  view_count: number
  query_count: number
  created_at: string
  source: string
}

interface UsageBubbleChartProps {
  data: UsageEntry[]
  orphaned: { name: string }[]
  loading: boolean
}

const SOURCE_PALETTE = [
  '#1D9E75', '#6366F1', '#F59E0B', '#EF4444', '#8B5CF6',
  '#06B6D4', '#EC4899', '#84CC16', '#F97316', '#14B8A6',
]

// Deterministic hash-based jitter so positions are stable across renders
function jitter(val: number, seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    hash = ((hash << 5) - hash + seed.charCodeAt(i)) | 0
  }
  return val + ((hash % 100) / 100 - 0.5) * 1.5
}

function daysAgo(dateStr: string): number {
  const diff = (Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24)
  return Math.max(0, Math.round(diff))
}

interface ScatterPoint {
  x: number
  y: number
  z: number
  name: string
  views: number
  queries: number
  source: string
  created: string
  isOrphaned: boolean
}

export function UsageBubbleChart({ data, orphaned, loading }: UsageBubbleChartProps) {
  const { t } = useTranslation('dashboard')
  if (loading) return <Skeleton className="h-64" />

  if (data.length === 0 && orphaned.length === 0) {
    return (
      <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
        <h3 className="text-sm font-semibold mb-1">{t('usage_chart.title')}</h3>
        <p className="text-[var(--text-tertiary)] text-sm">{t('usage_chart.empty')}</p>
      </div>
    )
  }

  // Check if all features have 0 usage
  const allZero = data.every(d => d.view_count + d.query_count === 0)
  if (allZero && data.length > 0) {
    return (
      <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
        <h3 className="text-sm font-semibold mb-1">{t('usage_chart.title')}</h3>
        <div className="flex items-center justify-center h-48 text-[var(--text-tertiary)] text-sm">
          {t('usage_chart.empty_long')}
        </div>
      </div>
    )
  }

  const orphanedNames = new Set(orphaned.map(o => o.name))

  // Build source color map
  const allSources = [...new Set(data.map(d => d.source).filter(Boolean))]
  const colorMap = new Map(allSources.map((src, i) => [src, SOURCE_PALETTE[i % SOURCE_PALETTE.length]]))

  // Group by source for scatter series, apply jitter + y offset
  const bySource = new Map<string, ScatterPoint[]>()
  let maxUsage = 0
  for (const d of data) {
    const src = d.source || 'unknown'
    const total = d.view_count + d.query_count
    if (total > maxUsage) maxUsage = total
    const rawDays = d.created_at ? daysAgo(d.created_at) : 0
    const point: ScatterPoint = {
      x: jitter(rawDays, d.name),
      y: total + 0.5,
      z: Math.max(d.query_count, 1),
      name: d.name,
      views: d.view_count,
      queries: d.query_count,
      source: src,
      created: d.created_at,
      isOrphaned: orphanedNames.has(d.name),
    }
    if (!bySource.has(src)) bySource.set(src, [])
    bySource.get(src)!.push(point)
  }

  // Orphaned features not in the active data set
  const activeNames = new Set(data.map(d => d.name))
  const orphanedOnly = orphaned.filter(o => !activeNames.has(o.name)).slice(0, 10)
  const orphanedPoints: ScatterPoint[] = orphanedOnly.map(o => ({
    x: jitter(30, o.name),
    y: 0.5,
    z: 1,
    name: o.name,
    views: 0,
    queries: 0,
    source: 'orphaned',
    created: '',
    isOrphaned: true,
  }))

  const maxDays = Math.max(30, ...data.map(d => d.created_at ? daysAgo(d.created_at) : 0))

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: { payload: ScatterPoint }[] }) => {
    if (!active || !payload?.[0]) return null
    const d = payload[0].payload
    return (
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[12px] shadow-lg">
        <p className="font-semibold text-[var(--text-primary)] mb-1">{d.name}</p>
        <p className="text-[var(--text-secondary)]">{t('usage_chart.tooltip.usage', { views: d.views, queries: d.queries })}</p>
        {d.created && <p className="text-[var(--text-secondary)]">{t('usage_chart.tooltip.created', { days: daysAgo(d.created) })}</p>}
        <p className="text-[var(--text-secondary)]">{t('usage_chart.tooltip.source', { source: d.source })}</p>
        {d.isOrphaned && <p className="text-[var(--warning)] font-medium mt-0.5">{t('usage_chart.tooltip.orphaned')}</p>}
      </div>
    )
  }

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
      <h3 className="text-sm font-semibold mb-1">{t('usage_chart.title')}</h3>
      <p className="text-xs text-[var(--text-tertiary)] mb-3">{t('usage_chart.subtitle')}</p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <XAxis
            type="number"
            dataKey="x"
            name={t('usage_chart.axis_days')}
            domain={[0, maxDays]}
            reversed
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}
            label={{ value: t('usage_chart.axis_days'), position: 'insideBottom', offset: -5, fontSize: 11, fill: 'var(--text-tertiary)' }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={t('usage_chart.axis_usage')}
            domain={[0, maxUsage + 1]}
            tick={{ fontSize: 11, fill: 'var(--text-tertiary)' }}
            tickFormatter={(v: number) => String(Math.max(0, Math.round(v - 0.5)))}
            label={{ value: t('usage_chart.axis_usage'), angle: -90, position: 'insideLeft', fontSize: 11, fill: 'var(--text-tertiary)' }}
          />
          <ZAxis type="number" dataKey="z" range={[36, 576]} />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            verticalAlign="top"
            height={24}
            iconType="circle"
            iconSize={8}
            formatter={(value: string) => <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{value}</span>}
          />
          {[...bySource.entries()].map(([src, points]) => (
            <Scatter
              key={src}
              name={src}
              data={points}
              fill={colorMap.get(src) || '#94A3B8'}
              opacity={0.8}
            />
          ))}
          {orphanedPoints.length > 0 && (
            <Scatter
              name={t('usage_chart.orphaned_label')}
              data={orphanedPoints}
              fill="transparent"
              stroke="#EF4444"
              strokeWidth={2}
              opacity={0.5}
            />
          )}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
