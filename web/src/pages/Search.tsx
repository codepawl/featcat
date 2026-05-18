import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search as SearchIcon, X } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { Skeleton } from '../components/Skeleton'

interface SearchHit {
  id: string
  name: string
  dtype: string
  source: string
  rank: number
  snippet?: string
}

interface FacetBucket {
  name: string
  count: number
}

interface FacetResponse {
  sources: FacetBucket[]
  tags: FacetBucket[]
  dtypes: FacetBucket[]
  has_doc: { true: number; false: number }
}

const FACET_KEYS = ['source', 'tag', 'dtype'] as const
type FacetKey = (typeof FACET_KEYS)[number]

/** Read all values for a repeated query-string key (?source=a&source=b). */
function readMulti(params: URLSearchParams, key: string): string[] {
  return params.getAll(key)
}

export function Search() {
  const { t } = useTranslation('search')
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()

  const q = params.get('q') ?? ''
  const docOnly = params.get('has_doc') === 'true'
  const undocOnly = params.get('has_doc') === 'false'
  const sourceFilter = useMemo(() => readMulti(params, 'source'), [params])
  const tagFilter = useMemo(() => readMulti(params, 'tag'), [params])
  const dtypeFilter = useMemo(() => readMulti(params, 'dtype'), [params])

  const [results, setResults] = useState<SearchHit[]>([])
  const [facets, setFacets] = useState<FacetResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const hasDocParam = docOnly ? true : undocOnly ? false : null

  const updateParams = useCallback((mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    // Cache must invalidate so toggling a facet refetches with the new filter
    // set (api.ts caches GETs for 10s).
    invalidateCache('/search')
    setParams(next, { replace: true })
  }, [params, setParams])

  const toggleFacet = useCallback((key: FacetKey, value: string) => {
    updateParams((next) => {
      const current = next.getAll(key)
      next.delete(key)
      if (current.includes(value)) {
        for (const v of current) if (v !== value) next.append(key, v)
      } else {
        for (const v of current) next.append(key, v)
        next.append(key, value)
      }
    })
  }, [updateParams])

  const setHasDoc = useCallback((value: boolean | null) => {
    updateParams((next) => {
      if (value == null) next.delete('has_doc')
      else next.set('has_doc', String(value))
    })
  }, [updateParams])

  const clearAll = useCallback(() => {
    updateParams((next) => {
      for (const k of FACET_KEYS) next.delete(k)
      next.delete('has_doc')
    })
  }, [updateParams])

  // Fetch results + facets whenever query/filters change.
  useEffect(() => {
    if (!q) {
      setResults([])
      setFacets(null)
      return
    }
    let cancelled = false
    setLoading(true)
    Promise.all([
      api.search.query({
        q,
        source: sourceFilter,
        tag: tagFilter,
        dtype: dtypeFilter,
        has_doc: hasDocParam,
        limit: 100,
      }).catch(() => [] as SearchHit[]),
      api.search.facets({
        q,
        source: sourceFilter[0],
        tag: tagFilter[0],
        dtype: dtypeFilter[0],
        has_doc: hasDocParam,
      }).catch(() => null),
    ])
      .then(([hits, fac]) => {
        if (cancelled) return
        // Backend filters by single value per key — narrow client-side when
        // multiple values are selected for the same facet (OR semantics).
        let filtered = hits as SearchHit[]
        if (sourceFilter.length > 1) {
          filtered = filtered.filter((h) => sourceFilter.includes(h.source))
        }
        if (dtypeFilter.length > 1) {
          filtered = filtered.filter((h) => dtypeFilter.includes(h.dtype))
        }
        setResults(filtered)
        setFacets(fac)
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, sourceFilter.join(','), tagFilter.join(','), dtypeFilter.join(','), hasDocParam])

  const activeFilterCount =
    sourceFilter.length + tagFilter.length + dtypeFilter.length + (hasDocParam != null ? 1 : 0)

  return (
    <div>
      <h1 className="text-2xl font-semibold mb-6">{t('page.title')}</h1>

      {!q ? (
        <div className="text-center py-16 text-[var(--text-tertiary)]">
          <SearchIcon size={32} className="mx-auto mb-3 opacity-50" />
          <p className="text-sm">{t('empty.prompt')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-6">
          {/* Facet sidebar */}
          <aside className="space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                {t('facets.title')}
              </h2>
              {activeFilterCount > 0 && (
                <button
                  onClick={clearAll}
                  className="text-[11px] text-brand hover:underline"
                >
                  {t('facets.clear')}
                </button>
              )}
            </div>

            <FacetSection
              title={t('facets.source')}
              buckets={facets?.sources ?? []}
              selected={sourceFilter}
              onToggle={(v) => toggleFacet('source', v)}
            />
            <FacetSection
              title={t('facets.dtype')}
              buckets={facets?.dtypes ?? []}
              selected={dtypeFilter}
              onToggle={(v) => toggleFacet('dtype', v)}
            />
            <FacetSection
              title={t('facets.tag')}
              buckets={facets?.tags ?? []}
              selected={tagFilter}
              onToggle={(v) => toggleFacet('tag', v)}
            />

            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)] mb-2">
                {t('facets.documentation')}
              </h3>
              <ul className="space-y-1">
                <FacetCheck
                  label={t('facets.documented')}
                  count={facets?.has_doc.true ?? 0}
                  checked={docOnly}
                  onToggle={() => setHasDoc(docOnly ? null : true)}
                />
                <FacetCheck
                  label={t('facets.undocumented')}
                  count={facets?.has_doc.false ?? 0}
                  checked={undocOnly}
                  onToggle={() => setHasDoc(undocOnly ? null : false)}
                />
              </ul>
            </div>
          </aside>

          {/* Results */}
          <section className="min-w-0">
            <div className="flex items-center justify-between mb-3 gap-3">
              <p className="text-sm text-[var(--text-secondary)]">
                {loading
                  ? t('header.loading')
                  : t('header.count', { count: results.length, query: q })}
              </p>
              {activeFilterCount > 0 && (
                <ActiveFilterChips
                  source={sourceFilter}
                  tag={tagFilter}
                  dtype={dtypeFilter}
                  hasDoc={hasDocParam}
                  onRemove={(key, value) => {
                    if (key === 'has_doc') setHasDoc(null)
                    else toggleFacet(key, value)
                  }}
                />
              )}
            </div>

            {loading && results.length === 0 ? (
              <Skeleton className="h-48" />
            ) : results.length === 0 ? (
              <div className="text-center py-16 border border-dashed border-[var(--border-subtle)] rounded-xl">
                <p className="text-sm text-[var(--text-secondary)] mb-2">{t('empty.no_match', { query: q })}</p>
                <p className="text-xs text-[var(--text-tertiary)]">{t('empty.suggest')}</p>
                {activeFilterCount > 0 && (
                  <button
                    onClick={clearAll}
                    className="mt-3 text-xs text-brand hover:underline"
                  >
                    {t('facets.clear')}
                  </button>
                )}
              </div>
            ) : (
              <ul className="space-y-2">
                {results.map((hit) => (
                  <li key={hit.id}>
                    <button
                      onClick={() => navigate(`/features/${encodeURIComponent(hit.name)}`)}
                      className="w-full text-left bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl px-4 py-3 hover:border-brand transition-colors"
                    >
                      <div className="flex items-center justify-between gap-3 mb-1">
                        <span className="font-mono text-sm font-medium text-brand truncate">{hit.name}</span>
                        <span className="text-[11px] text-[var(--text-tertiary)] shrink-0 tabular-nums">
                          {Math.round(hit.rank * 100)}%
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                        <span>{hit.source}</span>
                        <span>{'·'}</span>
                        <span className="font-mono">{hit.dtype}</span>
                      </div>
                      {hit.snippet && (
                        <p className="mt-1 text-xs text-[var(--text-secondary)] line-clamp-2">{hit.snippet}</p>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

/* -------- Facet building blocks -------- */

function FacetSection({
  title,
  buckets,
  selected,
  onToggle,
}: {
  title: string
  buckets: FacetBucket[]
  selected: string[]
  onToggle: (value: string) => void
}) {
  if (buckets.length === 0) return null
  return (
    <div>
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)] mb-2">
        {title}
      </h3>
      <ul className="space-y-1 max-h-56 overflow-y-auto pr-1">
        {buckets.slice(0, 50).map((b) => (
          <FacetCheck
            key={b.name}
            label={b.name}
            count={b.count}
            checked={selected.includes(b.name)}
            onToggle={() => onToggle(b.name)}
          />
        ))}
      </ul>
    </div>
  )
}

function FacetCheck({
  label,
  count,
  checked,
  onToggle,
}: {
  label: string
  count: number
  checked: boolean
  onToggle: () => void
}) {
  return (
    <li>
      <label className="flex items-center justify-between gap-2 cursor-pointer text-[13px] hover:text-[var(--text-primary)] text-[var(--text-secondary)] py-0.5">
        <span className="flex items-center gap-2 truncate">
          <input
            type="checkbox"
            checked={checked}
            onChange={onToggle}
            className="accent-brand shrink-0"
          />
          <span className="truncate">{label}</span>
        </span>
        <span className="text-[11px] font-mono text-[var(--text-tertiary)] tabular-nums shrink-0">
          {count}
        </span>
      </label>
    </li>
  )
}

function ActiveFilterChips({
  source,
  tag,
  dtype,
  hasDoc,
  onRemove,
}: {
  source: string[]
  tag: string[]
  dtype: string[]
  hasDoc: boolean | null
  onRemove: (key: FacetKey | 'has_doc', value: string) => void
}) {
  const { t } = useTranslation('search')
  const chips: { key: FacetKey | 'has_doc'; value: string; label: string }[] = []
  for (const v of source) chips.push({ key: 'source', value: v, label: v })
  for (const v of dtype) chips.push({ key: 'dtype', value: v, label: v })
  for (const v of tag) chips.push({ key: 'tag', value: v, label: v })
  if (hasDoc === true) chips.push({ key: 'has_doc', value: 'true', label: t('facets.documented') })
  if (hasDoc === false) chips.push({ key: 'has_doc', value: 'false', label: t('facets.undocumented') })
  return (
    <div className="flex flex-wrap gap-1 justify-end">
      {chips.map((c) => (
        <button
          key={`${c.key}:${c.value}`}
          onClick={() => onRemove(c.key, c.value)}
          className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full bg-brand-muted text-brand hover:bg-brand/15"
        >
          {c.label}
          <X size={10} />
        </button>
      ))}
    </div>
  )
}

