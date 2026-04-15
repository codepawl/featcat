import { useNavigate } from 'react-router-dom'
import { timeAgo } from '../../api'
import { Skeleton } from '../Skeleton'

interface SourceStat {
  source_name: string
  path: string
  feature_count: number
  documented_count: number
  drift_alerts: number
  critical_alerts: number
  last_scanned: string | null
  top_drifting_feature: string | null
}

interface DataSourceNodesProps {
  data: SourceStat[]
  loading: boolean
}

function truncatePath(path: string): string {
  const segments = path.replace(/\\/g, '/').split('/').filter(Boolean)
  if (segments.length <= 2) return path
  return '\u2026/' + segments.slice(-2).join('/')
}

type HealthLevel = 'healthy' | 'warning' | 'critical'

function getHealth(s: SourceStat): HealthLevel {
  if (s.critical_alerts > 0) return 'critical'
  if (s.drift_alerts > 0) return 'warning'
  return 'healthy'
}

const DOT_COLORS: Record<HealthLevel, [string, string, string]> = {
  healthy:  ['bg-green-500', 'bg-green-500', 'bg-green-500'],
  warning:  ['bg-green-500', 'bg-amber-500', 'bg-[var(--bg-tertiary)]'],
  critical: ['bg-green-500', 'bg-amber-500', 'bg-red-500'],
}

const CARD_BORDER: Record<HealthLevel, string> = {
  healthy:  'border-[var(--border-subtle)]',
  warning:  'border-amber-500/40 border-l-4 border-l-amber-500',
  critical: 'border-red-500/40 border-l-4 border-l-red-500',
}

export function DataSourceNodes({ data, loading }: DataSourceNodesProps) {
  const navigate = useNavigate()

  if (loading) {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-1">Data Sources</h3>
        <p className="text-xs text-[var(--text-tertiary)] mb-3">Click a source to explore its features</p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40" />)}
        </div>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-3">Data Sources</h3>
        <div className="border border-dashed border-[var(--border-default)] rounded-lg p-8 text-center">
          <p className="text-[var(--text-tertiary)]">No data sources registered yet.</p>
          <p className="text-[var(--text-tertiary)] text-sm mt-1">Use "Add Source" or run featcat scan-bulk to get started.</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h3 className="text-sm font-semibold mb-1">Data Sources</h3>
      <p className="text-xs text-[var(--text-tertiary)] mb-3">Click a source to explore its features</p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {data.map(s => {
          const health = getHealth(s)
          const docPct = s.feature_count > 0 ? Math.round((s.documented_count / s.feature_count) * 100) : 0
          const dots = DOT_COLORS[health]

          return (
            <div
              key={s.source_name}
              onClick={() => navigate(`/features?source=${encodeURIComponent(s.source_name)}`)}
              className={`bg-[var(--bg-primary)] border rounded-xl cursor-pointer transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${CARD_BORDER[health]} ${health === 'critical' ? 'animate-pulse-subtle' : ''}`}
              style={{ maxWidth: 340 }}
            >
              {/* Header */}
              <div className="px-4 pt-3 pb-2">
                <div className="flex items-center gap-2 mb-1">
                  <div className="flex gap-1">
                    {dots.map((color, i) => (
                      <span key={i} className={`w-2 h-2 rounded-full ${color}`} />
                    ))}
                  </div>
                  <span className="font-mono text-sm font-semibold truncate">{s.source_name}</span>
                </div>
                <p className="text-[11px] text-[var(--text-tertiary)] font-mono truncate" title={s.path}>
                  {truncatePath(s.path)}
                </p>
              </div>

              {/* Stats */}
              <div className="border-t border-[var(--border-subtle)] px-4 py-2.5 space-y-1.5">
                <div className="text-[13px]">
                  <span className="font-medium">{s.feature_count}</span>
                  <span className="text-[var(--text-secondary)]"> feature{s.feature_count !== 1 ? 's' : ''}</span>
                </div>

                {/* Doc coverage bar */}
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full transition-all"
                      style={{ width: `${docPct}%` }}
                    />
                  </div>
                  <span className="text-[11px] text-[var(--text-secondary)] w-12 text-right">{docPct}% docs</span>
                </div>

                {/* Drift alerts */}
                {s.drift_alerts > 0 ? (
                  <div className={`text-[12px] ${s.critical_alerts > 0 ? 'text-red-500' : 'text-amber-500'}`}>
                    {s.drift_alerts} drift alert{s.drift_alerts !== 1 ? 's' : ''}
                  </div>
                ) : (
                  <div className="text-[12px] text-green-600 dark:text-green-400">No drift alerts</div>
                )}

                {/* Critical line */}
                {s.critical_alerts > 0 ? (
                  <div className="text-[12px] text-red-500 font-medium">
                    {s.critical_alerts} critical{s.top_drifting_feature ? `: ${s.top_drifting_feature.split('.').pop()}` : ''}
                  </div>
                ) : (
                  <div className="text-[12px] text-green-600 dark:text-green-400">No critical issues</div>
                )}
              </div>

              {/* Footer */}
              <div className="border-t border-[var(--border-subtle)] px-4 py-2">
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  Scanned {s.last_scanned ? timeAgo(s.last_scanned) : 'never'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
