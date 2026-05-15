import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
  Legend,
} from 'recharts'
import type { MetricSeriesPoint } from '../../api'

interface MultiMetricTimelineProps {
  data: MetricSeriesPoint[]
  loading: boolean
  onRangeChange?: (days: number) => void
  days?: number
}

const RANGE_OPTIONS = [30, 90, 180] as const
type RangeDays = (typeof RANGE_OPTIONS)[number]

const COLORS = {
  psi: '#1D9E75',
  null_ratio: '#3B82F6',
  mean_z_score: '#A855F7',
  sample_size: '#F59E0B',
  kl_divergence: '#0EA5E9',
  wasserstein: '#EC4899',
}

const SEVERITY_THRESHOLDS = {
  psi_warning: 0.10,
  psi_critical: 0.25,
  z_score_alert: 3.0,
}

type MetricKey =
  | 'psi'
  | 'null_ratio'
  | 'mean_z_score'
  | 'sample_size'
  | 'kl_divergence'
  | 'wasserstein'

interface AnomalyHit {
  index: number
  metric: MetricKey
  value: number
  threshold: number
  reason: string
}

function formatDate(isoDate: string): string {
  const d = new Date(isoDate)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function detectAnomalies(data: MetricSeriesPoint[]): AnomalyHit[] {
  // Reasons are derived from the threshold map; no i18n at compute time —
  // the chart only uses the index/metric/value to draw the marker, and the
  // user reads the threshold off the visible reference lines + tooltip.
  const hits: AnomalyHit[] = []
  data.forEach((p, i) => {
    if (p.psi != null && p.psi >= SEVERITY_THRESHOLDS.psi_critical) {
      hits.push({ index: i, metric: 'psi', value: p.psi, threshold: SEVERITY_THRESHOLDS.psi_critical, reason: 'psi_critical' })
    } else if (p.psi != null && p.psi >= SEVERITY_THRESHOLDS.psi_warning) {
      hits.push({ index: i, metric: 'psi', value: p.psi, threshold: SEVERITY_THRESHOLDS.psi_warning, reason: 'psi_warning' })
    }
    if (p.mean_z_score != null && Math.abs(p.mean_z_score) > SEVERITY_THRESHOLDS.z_score_alert) {
      hits.push({ index: i, metric: 'mean_z_score', value: p.mean_z_score, threshold: SEVERITY_THRESHOLDS.z_score_alert, reason: 'zscore' })
    }
  })
  return hits
}

interface TooltipRow {
  payload: MetricSeriesPoint & { date: string }
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipRow[] }) {
  const { t } = useTranslation('monitoring')
  if (!active || !payload?.[0]) return null
  const d = payload[0].payload
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[12px] shadow-lg space-y-0.5 min-w-[180px]">
      <p className="text-[var(--text-secondary)]">{new Date(d.checked_at).toLocaleString()}</p>
      <p className="font-mono">
        <span style={{ color: COLORS.psi }}>●</span> PSI: {d.psi != null ? d.psi.toFixed(4) : '—'}
      </p>
      <p className="font-mono">
        <span style={{ color: COLORS.null_ratio }}>●</span> {t('multi_metric.metric_null_ratio', 'Null ratio')}: {d.null_ratio != null ? d.null_ratio.toFixed(4) : '—'}
      </p>
      <p className="font-mono">
        <span style={{ color: COLORS.mean_z_score }}>●</span> {t('multi_metric.metric_z_score', 'Z-score')}: {d.mean_z_score != null ? d.mean_z_score.toFixed(3) : '—'}
      </p>
      <p className="font-mono">
        <span style={{ color: COLORS.sample_size }}>●</span> {t('multi_metric.metric_sample_size', 'Sample size')}: {d.sample_size != null ? d.sample_size.toLocaleString() : '—'}
      </p>
      <p className="font-mono">
        <span style={{ color: COLORS.kl_divergence }}>●</span> {t('multi_metric.metric_kl', 'KL divergence')}: {d.kl_divergence != null ? d.kl_divergence.toFixed(4) : '—'}
      </p>
      <p className="font-mono">
        <span style={{ color: COLORS.wasserstein }}>●</span> {t('multi_metric.metric_wasserstein', 'Wasserstein')}: {d.wasserstein != null ? d.wasserstein.toFixed(4) : '—'}
      </p>
    </div>
  )
}

export function MultiMetricTimeline({ data, loading, onRangeChange, days = 30 }: MultiMetricTimelineProps) {
  const { t } = useTranslation('monitoring')
  const [hidden, setHidden] = useState<Set<MetricKey>>(new Set())

  // Use a per-render computed dataset that adds a formatted x-axis label.
  const chartData = useMemo(
    () => data.map(d => ({ ...d, date: formatDate(d.checked_at) })),
    [data],
  )

  const anomalies = useMemo(() => detectAnomalies(data), [data])

  const toggle = (key: MetricKey) => {
    setHidden(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const isHidden = (key: MetricKey) => hidden.has(key)

  if (loading) {
    return <div className="h-44 bg-[var(--bg-tertiary)] rounded animate-shimmer" />
  }

  const hasEnough = data.filter(d => d.psi != null).length >= 3
  if (!hasEnough) {
    return (
      <div className="flex items-center justify-center h-32 text-xs text-[var(--text-tertiary)] border border-dashed border-[var(--border-default)] rounded-lg">
        {t('multi_metric.not_enough_history', 'Not enough monitoring history yet')}
      </div>
    )
  }

  // Y-axis scale for left side (PSI / null_ratio / Z-score / KL) — pad on top.
  // Wasserstein lives on the right axis because its unit is the feature's
  // original unit, not the [0, ~1] range PSI / null_ratio / KL share.
  const leftMax = Math.max(
    ...data.map(d => Math.max(
      d.psi ?? 0,
      d.null_ratio ?? 0,
      Math.abs(d.mean_z_score ?? 0),
      d.kl_divergence ?? 0,
    )),
    SEVERITY_THRESHOLDS.psi_critical,
  ) + 0.05

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-[var(--text-secondary)]">
          {t('multi_metric.title', 'Metric history')}
        </p>
        {onRangeChange && (
          <select
            value={days}
            onChange={e => onRangeChange(Number(e.target.value))}
            className="text-[11px] bg-[var(--bg-primary)] border border-[var(--border-default)] rounded px-2 py-0.5"
          >
            {RANGE_OPTIONS.map(d => (
              <option key={d} value={d}>{t('multi_metric.range_days', { count: d, defaultValue: '{{count}} days' })}</option>
            ))}
          </select>
        )}
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={chartData} margin={{ top: 5, right: 30, bottom: 5, left: 5 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
            axisLine={{ stroke: 'var(--border-default)' }}
            minTickGap={20}
          />
          <YAxis
            yAxisId="left"
            domain={[0, leftMax]}
            tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
            axisLine={{ stroke: 'var(--border-default)' }}
            width={36}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
            axisLine={{ stroke: 'var(--border-default)' }}
            width={42}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine
            y={SEVERITY_THRESHOLDS.psi_warning}
            yAxisId="left"
            stroke={COLORS.psi}
            strokeDasharray="3 3"
            strokeOpacity={0.4}
          />
          <ReferenceLine
            y={SEVERITY_THRESHOLDS.psi_critical}
            yAxisId="left"
            stroke="#EF4444"
            strokeDasharray="3 3"
            strokeOpacity={0.4}
          />

          <Line
            yAxisId="left"
            type="monotone"
            dataKey="psi"
            name="PSI"
            stroke={COLORS.psi}
            strokeWidth={2}
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
            hide={isHidden('psi')}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="null_ratio"
            name={t('multi_metric.metric_null_ratio', 'Null ratio')}
            stroke={COLORS.null_ratio}
            strokeWidth={1.5}
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
            hide={isHidden('null_ratio')}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="mean_z_score"
            name={t('multi_metric.metric_z_score', 'Z-score')}
            stroke={COLORS.mean_z_score}
            strokeWidth={1.5}
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
            hide={isHidden('mean_z_score')}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="sample_size"
            name={t('multi_metric.metric_sample_size', 'Sample size')}
            stroke={COLORS.sample_size}
            strokeWidth={1.5}
            strokeDasharray="4 2"
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
            hide={isHidden('sample_size')}
          />
          {/* KL divergence shares the left axis (unitless, ~[0, leftMax])
              and renders dashed so it visually separates from PSI's solid line. */}
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="kl_divergence"
            name={t('multi_metric.metric_kl', 'KL divergence')}
            stroke={COLORS.kl_divergence}
            strokeWidth={1.5}
            strokeDasharray="6 3"
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
            hide={isHidden('kl_divergence')}
          />
          {/* Wasserstein lives on the right axis because it's in the feature's
              original units. Rendered dotted to distinguish from sample_size's
              dashed line on the same axis. */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="wasserstein"
            name={t('multi_metric.metric_wasserstein', 'Wasserstein')}
            stroke={COLORS.wasserstein}
            strokeWidth={1.5}
            strokeDasharray="2 3"
            connectNulls={false}
            dot={false}
            activeDot={{ r: 4 }}
            hide={isHidden('wasserstein')}
          />

          {/* Anomaly markers — small red dots on the PSI line at threshold crossings.
              Skipped when PSI is hidden so the tooltip content makes sense. */}
          {!isHidden('psi') && anomalies
            .filter(a => a.metric === 'psi')
            .map(a => (
              <ReferenceDot
                key={`anom-${a.index}-${a.metric}`}
                x={chartData[a.index]?.date}
                y={a.value}
                yAxisId="left"
                r={4}
                fill="#EF4444"
                stroke="var(--bg-primary)"
                strokeWidth={1.5}
                ifOverflow="extendDomain"
              />
            ))}

          <Legend
            iconType="line"
            wrapperStyle={{ fontSize: 11, paddingTop: 6 }}
            onClick={(entry) => {
              // dataKey is typed as string | number | (obj => any) on Recharts'
              // LegendPayload — it's a string for our Lines, so coerce defensively.
              const raw = entry.dataKey
              const key = typeof raw === 'string' ? raw : ''
              if (
                key === 'psi' ||
                key === 'null_ratio' ||
                key === 'mean_z_score' ||
                key === 'sample_size' ||
                key === 'kl_divergence' ||
                key === 'wasserstein'
              ) {
                toggle(key)
              }
            }}
          />
        </LineChart>
      </ResponsiveContainer>

      {anomalies.length > 0 && (
        <p className="text-[11px] text-[var(--text-tertiary)] mt-1">
          {t('multi_metric.anomaly_count', { count: anomalies.length, defaultValue: '{{count}} anomaly marker(s) — hover the data points for the threshold crossed' })}
        </p>
      )}
    </div>
  )
}
