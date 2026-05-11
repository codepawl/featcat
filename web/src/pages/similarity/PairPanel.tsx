import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { api, type SimilarityFeatureBrief, type SimilarityReasonCode } from '../../api'
import { Skeleton } from '../../components/Skeleton'

interface PairPanelProps {
  pair: { a: string; b: string } | null
  onClose: () => void
}

interface PairPayload {
  a: SimilarityFeatureBrief
  b: SimilarityFeatureBrief
  score: number
  reasons: { code: SimilarityReasonCode; detail: string }[]
}

const REASON_KEYS = {
  semantic_match: 'matrix.reasons.semantic_match',
  name_similarity: 'matrix.reasons.name_similarity',
  schema_match: 'matrix.reasons.schema_match',
  distribution_match: 'matrix.reasons.distribution_match',
} as const satisfies Record<SimilarityReasonCode, string>

export function PairPanel({ pair, onClose }: PairPanelProps) {
  const { t } = useTranslation('similarity')
  const [data, setData] = useState<PairPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!pair) {
      setData(null)
      setError(null)
      return
    }
    let active = true
    setLoading(true)
    setError(null)
    api.similarity
      .pair(pair.a, pair.b)
      .then((d) => {
        if (active) setData(d)
      })
      .catch((err: Error) => {
        if (active) {
          setError(err.message)
          setData(null)
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [pair])

  useEffect(() => {
    if (!pair) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [pair, onClose])

  if (!pair) return null

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={t('matrix.panel.aria_label')}
        className="fixed inset-y-0 right-0 w-96 max-w-full bg-[var(--bg-primary)] border-l border-[var(--border-default)] shadow-2xl z-50 flex flex-col"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border-subtle)]">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            {t('matrix.panel.title')}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors p-1 rounded hover:bg-[var(--bg-secondary)]"
            aria-label={t('matrix.panel.close')}
          >
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {loading && !data ? (
            <Skeleton className="h-48" />
          ) : error ? (
            <div className="text-sm text-[var(--text-tertiary)]">{error}</div>
          ) : data ? (
            <PairBody data={data} />
          ) : null}
        </div>
      </aside>
    </>
  )
}

function PairBody({ data }: { data: PairPayload }) {
  const { t } = useTranslation('similarity')
  return (
    <>
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <div className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">
            {t('matrix.panel.score_label')}
          </div>
          <div className="text-2xl font-semibold text-brand tabular-nums">{data.score.toFixed(3)}</div>
        </div>
      </div>

      <div className="grid gap-3">
        <FeatureCard label={t('matrix.panel.feature_a')} feat={data.a} />
        <FeatureCard label={t('matrix.panel.feature_b')} feat={data.b} />
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)] mb-2">
          {t('matrix.panel.reasons_label')}
        </div>
        <ul className="space-y-2">
          {data.reasons.map((r) => (
            <li key={r.code} className="border border-[var(--border-subtle)] rounded-md px-3 py-2">
              <div className="text-[12px] font-semibold text-[var(--text-secondary)]">
                {t(REASON_KEYS[r.code])}
              </div>
              <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">{r.detail}</div>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}

function FeatureCard({ label, feat }: { label: string; feat: SimilarityFeatureBrief }) {
  return (
    <div className="border border-[var(--border-subtle)] rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="text-[13px] font-medium text-[var(--text-primary)] break-all">{feat.name}</div>
      <div className="text-[11px] text-[var(--text-tertiary)] flex gap-2 mt-1">
        <span>{feat.source || '—'}</span>
        <span className="font-mono">{feat.dtype || '—'}</span>
      </div>
    </div>
  )
}
