import { useState, useMemo, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { SearchInput } from './SearchInput'

export interface FeatureItem {
  spec: string
  source: string
  column: string
  dtype: string
  has_doc: boolean
  health_grade?: string
}

interface FeatureSelectorProps {
  features: FeatureItem[]
  selected: Set<string>
  onChange: (selected: Set<string>) => void
  groupName?: string
  showAISuggest?: boolean
  maxHeight?: string
  placeholder?: string
}

const GRADE_COLORS: Record<string, string> = {
  A: 'text-green-500',
  B: 'text-teal-500',
  C: 'text-amber-500',
  D: 'text-red-500',
}

export function FeatureSelector({
  features,
  selected,
  onChange,
  groupName,
  showAISuggest,
  maxHeight = '320px',
  placeholder,
}: FeatureSelectorProps) {
  const { t } = useTranslation('modals')
  const effectivePlaceholder = placeholder ?? t('feature_selector.search_placeholder')
  const [searchQuery, setSearchQuery] = useState('')
  const [showSelectedOnly, setShowSelectedOnly] = useState(false)
  const [suggesting, setSuggesting] = useState(false)
  const [aiSuggested, setAiSuggested] = useState<Set<string>>(new Set())
  const [llmAvailable, setLlmAvailable] = useState(false)
  const lastChecked = useRef<string | null>(null)

  const enableAI = showAISuggest ?? !!groupName

  useEffect(() => {
    if (enableAI) {
      api.health()
        .then((d: Record<string, unknown>) => setLlmAvailable(!!d.llm))
        .catch(() => setLlmAvailable(false))
    }
  }, [enableAI])

  const filtered = useMemo(() => {
    const q = searchQuery.toLowerCase()
    return features.filter(f => {
      if (showSelectedOnly && !selected.has(f.spec)) return false
      if (q && !f.spec.toLowerCase().includes(q)) return false
      return true
    }).slice(0, 50)
  }, [features, searchQuery, showSelectedOnly, selected])

  const handleClick = (spec: string, e: React.MouseEvent) => {
    e.preventDefault()
    if (e.shiftKey && lastChecked.current) {
      const currentSpecs = filtered.map(f => f.spec)
      const a = currentSpecs.indexOf(lastChecked.current)
      const b = currentSpecs.indexOf(spec)
      if (a >= 0 && b >= 0) {
        const range = currentSpecs.slice(Math.min(a, b), Math.max(a, b) + 1)
        const next = new Set(selected)
        range.forEach(s => next.add(s))
        onChange(next)
        lastChecked.current = spec
        return
      }
    }
    const next = new Set(selected)
    if (next.has(spec)) next.delete(spec); else next.add(spec)
    onChange(next)
    lastChecked.current = spec
  }

  // Dominant source detection
  const sourceCounts = new Map<string, number>()
  for (const f of filtered) {
    sourceCounts.set(f.source, (sourceCounts.get(f.source) || 0) + 1)
  }
  const dominantSource = sourceCounts.size === 1 ? [...sourceCounts.keys()][0] : null
  const dominantCount = dominantSource ? sourceCounts.get(dominantSource) || 0 : 0

  const selectAllFromSource = (src: string) => {
    const next = new Set(selected)
    filtered.forEach(f => { if (f.source === src) next.add(f.spec) })
    onChange(next)
  }

  const handleAISuggest = async () => {
    if (!groupName) return
    setSuggesting(true)
    try {
      const result = await api.ai.discover(groupName) as Record<string, unknown>
      const existing = (result.existing_features || []) as { name: string }[]
      const specs = existing.map(f => f.name).filter(Boolean)
      onChange(new Set([...selected, ...specs]))
      setAiSuggested(new Set(specs))
    } catch {
      // silently fail
    } finally {
      setSuggesting(false)
    }
  }

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center gap-2 mb-2">
        <SearchInput placeholder={effectivePlaceholder} onSearch={setSearchQuery} delay={200} className="flex-1" />
        <button
          onClick={() => setShowSelectedOnly(prev => !prev)}
          className={`text-sm px-3 py-1.5 rounded border whitespace-nowrap ${
            showSelectedOnly
              ? 'border-accent bg-accent/20 text-accent'
              : 'border-[var(--border-default)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
          }`}
        >
          {t('feature_selector.selected_count', { count: selected.size })}
        </button>
        {enableAI && llmAvailable && (
          <button
            onClick={handleAISuggest}
            disabled={suggesting}
            className="text-sm px-3 py-1.5 rounded border border-[var(--accent-border)] text-[var(--accent)] hover:bg-[var(--accent-subtle-bg)] disabled:opacity-50 whitespace-nowrap"
          >
            {suggesting ? t('feature_selector.ai_suggesting') : t('feature_selector.ai_suggest')}
          </button>
        )}
      </div>

      {/* Source select + tip */}
      <div className="flex items-center justify-between mb-1">
        <p className="text-[10px] text-[var(--text-tertiary)]">
          {t('feature_selector.shift_tip')}
        </p>
        {dominantSource && (
          <button onClick={() => selectAllFromSource(dominantSource)}
            className="text-[10px] text-accent hover:underline whitespace-nowrap">
            {t('feature_selector.select_all_from_source', { source: dominantSource, count: dominantCount })}
          </button>
        )}
      </div>

      {/* Feature list */}
      <div className="overflow-y-auto overscroll-contain select-none space-y-0.5" style={{ maxHeight }}>
        {filtered.length === 0 ? (
          <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">
            {showSelectedOnly && selected.size === 0
              ? t('feature_selector.empty_selected')
              : showSelectedOnly
                ? t('feature_selector.selected_not_found')
                : t('feature_selector.no_matches')}
          </p>
        ) : filtered.map(f => (
          <div
            key={f.spec}
            onClick={e => handleClick(f.spec, e)}
            className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-[var(--bg-secondary)] cursor-pointer text-[13px]"
          >
            <input
              type="checkbox"
              checked={selected.has(f.spec)}
              readOnly
              tabIndex={-1}
              className="accent-accent pointer-events-none"
            />
            {aiSuggested.has(f.spec) && <span className="text-xs" title={t('feature_selector.ai_suggested_tooltip')}>{'\u2728'}</span>}
            <span className="font-medium flex-1">{f.spec}</span>
            <span className="text-xs text-[var(--text-tertiary)] font-mono">{f.dtype}</span>
            {f.health_grade && (
              <span className={`text-xs font-semibold ${GRADE_COLORS[f.health_grade] || 'text-[var(--text-tertiary)]'}`}>
                {f.health_grade}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <p className="text-[10px] text-[var(--text-tertiary)] mt-1.5">
        {t('feature_selector.n_of_m_selected', { n: selected.size, m: features.length })}
      </p>
    </div>
  )
}


/** Convert raw API feature data to FeatureItem[] for FeatureSelector */
export function toFeatureItems(features: Record<string, unknown>[]): FeatureItem[] {
  return features.map(f => ({
    spec: f.name as string,
    source: ((f.name as string) || '').split('.')[0],
    column: f.column_name as string || ((f.name as string) || '').split('.').pop() || '',
    dtype: f.dtype as string || '',
    has_doc: !!f.has_doc,
    health_grade: f.health_grade as string | undefined,
  }))
}
