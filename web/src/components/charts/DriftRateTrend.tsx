import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, ReferenceLine, Tooltip } from 'recharts'
import { api, type DriftRateResponse } from '../../api'
import { Skeleton } from '../Skeleton'

interface DriftRateTrendProps {
  /** Alert-level reference line, percentage. Defaults to 10. */
  alertThresholdPct?: number
}

const RANGE_OPTIONS = [30, 90, 180, 365] as const
type RangeDays = (typeof RANGE_OPTIONS)[number]

const COLORS = {
  critical: '#EF4444',
  warning: '#F59E0B',
}

function formatDate(isoDate: string): string {
  const d = new Date(isoDate)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

interface TooltipPoint {
  payload: { date: string; critical_pct: number; warning_pct: number; total_features: number }
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: TooltipPoint[] }) {
  const { t } = useTranslation('dashboard')
  if (!active || !payload?.[0]) return null
  const d = payload[0].payload
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[12px] shadow-lg">
      <p className="text-[var(--text-secondary)] mb-1">{new Date(d.date).toLocaleDateString()}</p>
      <p className="font-mono">
        <span style={{ color: COLORS.critical }}>●</span> {t('drift_trend.critical', 'Critical')}: {d.critical_pct.toFixed(1)}%
      </p>
      <p className="font-mono">
        <span style={{ color: COLORS.warning }}>●</span> {t('drift_trend.warning', 'Warning')}: {d.warning_pct.toFixed(1)}%
      </p>
      <p className="text-[var(--text-tertiary)] mt-1">
        {t('drift_trend.tracked_features', { count: d.total_features, defaultValue: '{{count}} features tracked' })}
      </p>
    </div>
  )
}

export function DriftRateTrend({ alertThresholdPct = 10 }: DriftRateTrendProps) {
  const { t } = useTranslation('dashboard')
  const [days, setDays] = useState<RangeDays>(90)
  const [data, setData] = useState<DriftRateResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [showWarning, setShowWarning] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.monitor.driftRate(days)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [days])

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold">{t('drift_trend.title', 'Drift rate trend')}</h3>
          <p className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
            {t('drift_trend.subtitle', '% of feature-store features in critical / warning status per day')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-[12px] cursor-pointer text-[var(--text-secondary)]">
            <input
              type="checkbox"
              checked={showWarning}
              onChange={e => setShowWarning(e.target.checked)}
              className="accent-amber-500"
            />
            {t('drift_trend.show_warning', 'Show warning')}
          </label>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value) as RangeDays)}
            className="text-[12px] bg-[var(--bg-primary)] border border-[var(--border-default)] rounded px-2 py-1"
          >
            {RANGE_OPTIONS.map(d => (
              <option key={d} value={d}>{t('drift_trend.range_days', { count: d, defaultValue: '{{count}} days' })}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-40" />
      ) : !data || data.series.length === 0 ? (
        <p className="text-sm text-[var(--text-tertiary)] py-12 text-center">
          {t('drift_trend.empty', 'No drift history yet — run a /monitor/check to start tracking.')}
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data.series} margin={{ top: 5, right: 10, bottom: 5, left: 5 }}>
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
              axisLine={{ stroke: 'var(--border-default)' }}
              minTickGap={20}
            />
            <YAxis
              domain={[0, (max: number) => Math.max(max, alertThresholdPct + 5)]}
              tickFormatter={(v: number) => `${v}%`}
              tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
              axisLine={{ stroke: 'var(--border-default)' }}
              width={36}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={alertThresholdPct}
              stroke={COLORS.critical}
              strokeDasharray="4 4"
              label={{
                value: t('drift_trend.alert_threshold', { pct: alertThresholdPct, defaultValue: 'Alert: {{pct}}%' }),
                fontSize: 9,
                fill: COLORS.critical,
                position: 'right',
              }}
            />
            {showWarning && (
              <Line
                type="monotone"
                dataKey="warning_pct"
                stroke={COLORS.warning}
                strokeWidth={1.5}
                dot={false}
                activeDot={{ r: 4 }}
              />
            )}
            <Line
              type="monotone"
              dataKey="critical_pct"
              stroke={COLORS.critical}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
