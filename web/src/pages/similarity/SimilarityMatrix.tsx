import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api, type SimilarityFeatureBrief } from '../../api'
import { FeatureSelector, toFeatureItems } from '../../components/FeatureSelector'
import { Skeleton } from '../../components/Skeleton'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { MatrixGrid } from './MatrixGrid'
import { PairPanel } from './PairPanel'

const DEFAULT_THRESHOLD = 0.3
const DEFAULT_FEATURE_COUNT = 30
const FEATURE_CAP = 100
const THRESHOLD_DEBOUNCE_MS = 400

interface RawFeature {
  id: string
  name: string
  column_name?: string
  dtype?: string
  has_doc?: boolean
  health_grade?: string
}

interface MatrixPayload {
  features: SimilarityFeatureBrief[]
  cells: { a: number; b: number; score: number }[]
  threshold: number
  cached_at: string | null
}

function bySourceThenName<T extends { name: string }>(a: T, b: T): number {
  const aSrc = a.name.split('.')[0] ?? ''
  const bSrc = b.name.split('.')[0] ?? ''
  if (aSrc !== bSrc) return aSrc.localeCompare(bSrc)
  return a.name.localeCompare(b.name)
}

export function SimilarityMatrix() {
  const { t } = useTranslation('similarity')

  const [allFeatures, setAllFeatures] = useState<RawFeature[]>([])
  const [loadingFeatures, setLoadingFeatures] = useState(true)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD)
  const debouncedThreshold = useDebouncedValue(threshold, THRESHOLD_DEBOUNCE_MS)

  const [matrixData, setMatrixData] = useState<MatrixPayload | null>(null)
  const [matrixLoading, setMatrixLoading] = useState(false)
  const [matrixError, setMatrixError] = useState<string | null>(null)
  const [activePair, setActivePair] = useState<{ a: string; b: string } | null>(null)

  // Load full feature list once.
  useEffect(() => {
    let active = true
    api.features.list()
      .then((feats) => {
        if (!active) return
        const arr = (feats as RawFeature[]) ?? []
        const sorted = [...arr].sort(bySourceThenName)
        setAllFeatures(sorted)
        // Auto-select first N to give the user something to look at on load.
        setSelected(new Set(sorted.slice(0, DEFAULT_FEATURE_COUNT).map((f) => f.name)))
      })
      .catch(() => {
        if (active) setAllFeatures([])
      })
      .finally(() => {
        if (active) setLoadingFeatures(false)
      })
    return () => {
      active = false
    }
  }, [])

  const featureItems = useMemo(
    () => toFeatureItems(allFeatures as unknown as Record<string, unknown>[]),
    [allFeatures],
  )

  const specToId = useMemo(() => {
    const m = new Map<string, string>()
    for (const f of allFeatures) m.set(f.name, f.id)
    return m
  }, [allFeatures])

  // Stable, source-grouped order of selected specs; then truncate to the cap.
  const selectedSorted = useMemo(() => {
    return [...selected].sort((a, b) => {
      const aSrc = a.split('.')[0] ?? ''
      const bSrc = b.split('.')[0] ?? ''
      if (aSrc !== bSrc) return aSrc.localeCompare(bSrc)
      return a.localeCompare(b)
    })
  }, [selected])

  const cappedSpecs = selectedSorted.slice(0, FEATURE_CAP)
  const cappedIds = useMemo(
    () => cappedSpecs.map((s) => specToId.get(s)).filter((x): x is string => Boolean(x)),
    [cappedSpecs, specToId],
  )
  const exceedsCap = selected.size > FEATURE_CAP

  // Fetch matrix whenever selection or debounced threshold changes.
  useEffect(() => {
    if (cappedIds.length < 2) {
      setMatrixData(null)
      setMatrixError(null)
      return
    }
    let active = true
    setMatrixLoading(true)
    setMatrixError(null)
    api.similarity
      .matrix(cappedIds, debouncedThreshold)
      .then((data) => {
        if (active) setMatrixData(data)
      })
      .catch((err: Error) => {
        if (active) {
          setMatrixError(err.message)
          setMatrixData(null)
        }
      })
      .finally(() => {
        if (active) setMatrixLoading(false)
      })
    return () => {
      active = false
    }
  }, [cappedIds, debouncedThreshold])

  const handleCellClick = (aId: string, bId: string) => {
    setActivePair({ a: aId, b: bId })
  }

  return (
    <div className="flex h-full min-h-0 gap-4 p-4">
      {/* Left column — feature picker */}
      <aside className="w-80 shrink-0 flex flex-col gap-3 border-r border-[var(--border-subtle)] pr-4">
        <div>
          <div className="text-[12px] font-semibold text-[var(--text-secondary)] mb-1">
            {t('matrix.feature_picker_label')}
          </div>
          <p className="text-[11px] text-[var(--text-tertiary)]">
            {t('matrix.feature_picker_hint', { cap: FEATURE_CAP })}
          </p>
        </div>
        {loadingFeatures ? (
          <Skeleton className="h-64" />
        ) : (
          <FeatureSelector
            features={featureItems}
            selected={selected}
            onChange={setSelected}
            maxHeight="calc(100vh - 280px)"
          />
        )}
      </aside>

      {/* Right column — controls + grid */}
      <section className="flex-1 min-w-0 flex flex-col gap-3">
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
            <span className="whitespace-nowrap">{t('matrix.threshold_label')}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={threshold}
              onChange={(e) => setThreshold(Number.parseFloat(e.target.value))}
              className="accent-brand"
            />
            <span className="font-mono text-[11px] tabular-nums w-9 text-right">
              {threshold.toFixed(2)}
            </span>
          </label>
          <span className="text-[11px] text-[var(--text-tertiary)]">
            {exceedsCap
              ? t('matrix.cap_warning', { showing: FEATURE_CAP, total: selected.size })
              : t('matrix.selected_count', { count: cappedIds.length })}
          </span>
          {matrixData?.cached_at && (
            <span className="text-[10px] text-[var(--text-tertiary)]">
              {t('matrix.cached_label')}
            </span>
          )}
        </div>

        <div className="flex-1 min-h-0 overflow-auto rounded border border-[var(--border-subtle)]">
          {cappedIds.length < 2 ? (
            <EmptyState
              title={t('matrix.empty.too_few.title')}
              subtitle={t('matrix.empty.too_few.subtitle')}
            />
          ) : matrixLoading && !matrixData ? (
            <div className="p-4">
              <Skeleton className="h-64" />
            </div>
          ) : matrixError ? (
            <EmptyState title={t('matrix.empty.error.title')} subtitle={matrixError} />
          ) : matrixData && matrixData.cells.length === 0 ? (
            <EmptyState
              title={t('matrix.empty.no_pairs.title')}
              subtitle={t('matrix.empty.no_pairs.subtitle', {
                threshold: debouncedThreshold.toFixed(2),
              })}
            />
          ) : matrixData ? (
            <MatrixGrid
              features={matrixData.features}
              cells={matrixData.cells}
              onCellClick={handleCellClick}
            />
          ) : null}
        </div>
      </section>

      <PairPanel pair={activePair} onClose={() => setActivePair(null)} />
    </div>
  )
}

function EmptyState({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <div className="font-medium text-[var(--text-secondary)] mb-1">{title}</div>
      <div className="text-sm text-[var(--text-tertiary)]">{subtitle}</div>
    </div>
  )
}
