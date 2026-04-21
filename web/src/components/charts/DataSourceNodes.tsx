import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { timeAgo } from '../../api'
import { Skeleton } from '../Skeleton'
import { Badge } from '../Badge'

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
  return '…/' + segments.slice(-2).join('/')
}

export function DataSourceNodes({ data, loading }: DataSourceNodesProps) {
  const { t } = useTranslation('dashboard')
  const navigate = useNavigate()

  if (loading) {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-1">{t('sources.title')}</h3>
        <p className="text-xs text-[var(--text-tertiary)] mb-3">{t('sources.subtitle')}</p>
        <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-36" />)}
        </div>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div>
        <h3 className="text-sm font-semibold mb-3">{t('sources.title')}</h3>
        <div className="border border-dashed border-[var(--border-default)] rounded-lg p-8 text-center">
          <p className="text-[var(--text-tertiary)]">{t('sources.empty')}</p>
          <p className="text-[var(--text-tertiary)] text-sm mt-1">{t('sources.empty_hint')}</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <h3 className="text-sm font-semibold mb-1">{t('sources.title')}</h3>
      <p className="text-xs text-[var(--text-tertiary)] mb-3">{t('sources.subtitle')}</p>
      <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
        {data.map(s => {
          const docPct = s.feature_count > 0 ? Math.round((s.documented_count / s.feature_count) * 100) : 0
          const isClean = s.drift_alerts === 0 && s.critical_alerts === 0

          return (
            <div
              key={s.source_name}
              onClick={() => navigate(`/features?source=${encodeURIComponent(s.source_name)}`)}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg cursor-pointer transition-colors hover:border-[var(--border-muted)]"
            >
              {/* Header */}
              <div className="px-3 pt-3 pb-2 flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <span className="font-mono text-sm font-semibold text-[var(--text-primary)] truncate block">{s.source_name}</span>
                  <p className="text-[11px] text-[var(--text-tertiary)] font-mono truncate mt-0.5" title={s.path}>
                    {truncatePath(s.path)}
                  </p>
                </div>
                {s.critical_alerts > 0 ? (
                  <Badge variant="danger">{t('sources.badge_critical', { count: s.critical_alerts })}</Badge>
                ) : s.drift_alerts > 0 ? (
                  <Badge variant="warning">{t('sources.badge_alert', { count: s.drift_alerts })}</Badge>
                ) : null}
              </div>

              {/* Stats */}
              <div className="border-t border-[var(--border-subtle)] px-3 py-2.5 space-y-1.5">
                <div className="text-[13px]">
                  <span className="font-medium">{s.feature_count}</span>
                  <span className="text-[var(--text-secondary)]"> {t('sources.feature', { count: s.feature_count })}</span>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent)] rounded-full"
                      style={{ width: `${docPct}%` }}
                    />
                  </div>
                  <span className="text-[11px] text-[var(--text-secondary)] w-12 text-right">{t('sources.docs_percent', { pct: docPct })}</span>
                </div>

                {isClean && <Badge variant="success">{t('sources.all_clear')}</Badge>}
              </div>

              {/* Footer */}
              <div className="border-t border-[var(--border-subtle)] px-3 py-2">
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  {t('sources.scanned_prefix', { time: timeAgo(s.last_scanned) })}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
