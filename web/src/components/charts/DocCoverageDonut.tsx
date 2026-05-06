import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '../Skeleton'

interface DocCoverageDonutProps {
  totalFeatures: number
  documentedFeatures: number
  featuresWithHints: number
  loading: boolean
}

const COLORS = {
  documented: '#1D9E75',
  hintsOnly: '#F59E0B',
  noDoc: '#94A3B8',
}

const CARD = 'bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5'

export function DocCoverageDonut({ totalFeatures, documentedFeatures, featuresWithHints, loading }: DocCoverageDonutProps) {
  const { t } = useTranslation('dashboard')
  const navigate = useNavigate()

  if (loading) {
    return (
      <div className={CARD}>
        <h3 className="text-sm font-semibold mb-4">{t('donut.title')}</h3>
        <Skeleton className="h-24" />
      </div>
    )
  }

  if (totalFeatures === 0) {
    return (
      <div className={CARD}>
        <h3 className="text-sm font-semibold mb-4">{t('donut.title')}</h3>
        <div className="text-sm text-[var(--text-tertiary)]">{t('donut.empty')}</div>
      </div>
    )
  }

  const hintsOnly = Math.max(0, featuresWithHints - documentedFeatures)
  const noDoc = Math.max(0, totalFeatures - documentedFeatures - hintsOnly)
  const docPct = Math.round((documentedFeatures / totalFeatures) * 100)

  const segments = [
    { name: t('donut.segments.documented'), value: documentedFeatures, color: COLORS.documented },
    { name: t('donut.segments.hints_only'), value: hintsOnly, color: COLORS.hintsOnly },
    { name: t('donut.segments.no_doc'), value: noDoc, color: COLORS.noDoc },
  ].filter(s => s.value > 0)

  return (
    <div
      className={`${CARD} cursor-pointer transition-colors hover:border-[var(--border-muted)]`}
      onClick={() => navigate('/features?filter=undocumented')}
    >
      <h3 className="text-sm font-semibold mb-4">{t('donut.title')}</h3>

      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-2xl font-semibold text-[var(--text-primary)] leading-none">{docPct}%</span>
        <span className="text-xs text-[var(--text-secondary)]">{t('donut.documented')}</span>
      </div>

      <div className="flex h-2 w-full rounded-full overflow-hidden bg-[var(--bg-tertiary)] mb-3">
        {segments.map(s => (
          <div
            key={s.name}
            style={{ width: `${(s.value / totalFeatures) * 100}%`, background: s.color }}
            className="h-full"
          />
        ))}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {segments.map(s => (
          <div key={s.name} className="flex items-center gap-1.5 text-xs">
            <span className="inline-block w-2 h-2 rounded-full" style={{ background: s.color }} />
            <span className="text-[var(--text-secondary)]">
              {s.name} <span className="text-[var(--text-tertiary)]">({s.value})</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
