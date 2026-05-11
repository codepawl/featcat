import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { api, type DriftMatrixResponse } from '../../api'
import { Skeleton } from '../Skeleton'

interface GroupDriftHeatmapProps {
  groupName: string
  /** Window size in days. Backend caps at 90. Default 30. */
  days?: number
}

const SEVERITY_BG: Record<string, string> = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  healthy: 'bg-emerald-500',
  // 40% opacity slate for the no-data sentinel — reads as "absent" rather
  // than "neutral healthy" against the surrounding cells.
  unknown: 'bg-slate-700/40',
  error: 'bg-red-500',
}

function formatDateShort(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

export function GroupDriftHeatmap({ groupName, days = 30 }: GroupDriftHeatmapProps) {
  const { t } = useTranslation('groups')
  const [data, setData] = useState<DriftMatrixResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.groups.driftMatrix(groupName, days)
      .then(d => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [groupName, days])

  if (loading) return <Skeleton className="h-32" />
  if (!data || data.features.length === 0) {
    return (
      <p className="text-sm text-[var(--text-tertiary)] py-4 text-center border border-dashed border-[var(--border-default)] rounded-lg">
        {t('drift_heatmap.empty', { defaultValue: 'No monitored features in this group yet' })}
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide">
          {t('drift_heatmap.title', { defaultValue: 'Drift heatmap (last {{days}} days)', days })}
        </h4>
        <div className="flex items-center gap-3 text-[11px] text-[var(--text-tertiary)]">
          {(['critical', 'warning', 'healthy', 'unknown'] as const).map(s => (
            <span key={s} className="flex items-center gap-1 capitalize">
              <span className={`size-2 rounded-sm ${SEVERITY_BG[s]}`} />
              {s}
            </span>
          ))}
        </div>
      </div>

      {data.truncated && (
        <div className="flex items-start gap-2 px-3 py-2 text-[12px] bg-amber-500/10 border border-amber-500/30 rounded-lg text-[var(--text-secondary)]">
          <AlertTriangle size={14} className="text-amber-500 mt-0.5 shrink-0" />
          <span>
            {t('drift_heatmap.truncated', {
              shown: data.features.length,
              total: data.total_count,
              defaultValue: 'Showing top {{shown}} of {{total}} features by latest severity. Filter the group or split it to see all members.',
            })}
          </span>
        </div>
      )}

      <div className="overflow-x-auto border border-[var(--border-subtle)] rounded-lg">
        <table className="text-[11px] border-separate" style={{ borderSpacing: 0 }}>
          <thead>
            <tr>
              <th
                className="sticky left-0 z-20 bg-[var(--bg-primary)] border-r border-[var(--border-default)] px-2 py-1 text-left font-medium text-[var(--text-tertiary)]"
                style={{ minWidth: 200 }}
              >
                {t('drift_heatmap.feature_col', { defaultValue: 'Feature' })}
              </th>
              {data.date_range.map(d => (
                <th
                  key={d}
                  className="px-1 py-1 font-normal text-[var(--text-tertiary)] text-center"
                  style={{ minWidth: 24 }}
                >
                  {formatDateShort(d)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.features.map(feature => (
              <tr key={feature.id}>
                <th
                  className="sticky left-0 z-10 bg-[var(--bg-primary)] border-r border-t border-[var(--border-subtle)] px-2 py-1 text-left font-normal"
                  style={{ minWidth: 200 }}
                >
                  <a
                    href={`/monitoring?feature=${encodeURIComponent(feature.name)}`}
                    className="font-mono text-brand hover:underline truncate block"
                    title={feature.source ? `${feature.name} (${feature.source})` : feature.name}
                  >
                    {feature.name}
                  </a>
                </th>
                {feature.daily.map(cell => (
                  <td
                    key={cell.date}
                    className={`border-t border-[var(--border-subtle)] ${SEVERITY_BG[cell.severity] ?? SEVERITY_BG.unknown} hover:opacity-80 cursor-pointer`}
                    style={{ minWidth: 24, height: 22 }}
                    title={`${feature.name} · ${cell.date} · ${cell.severity}${cell.psi != null ? ` · PSI ${cell.psi.toFixed(3)}` : ''}`}
                    onClick={() => {
                      window.location.href = `/monitoring?feature=${encodeURIComponent(feature.name)}`
                    }}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
