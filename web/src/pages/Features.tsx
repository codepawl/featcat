import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw, Check, AlertTriangle, Shield, FileText, FolderSearch, X, ChevronDown, ChevronRight, Pencil, Download, Tag as TagIcon, FolderPlus, Trash2 } from 'lucide-react'
import { PageHeader } from '../components/PageHeader'
import { RefreshButton } from '../components/RefreshButton'
import { Alert } from '../components/Alert'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FilterSelect, FilterClearLink, FilterCountChip } from '../components/filters'
import { api, invalidateCache, timeAgo } from '../api'
import { DataTable } from '../components/DataTable'
import { VirtualizedTable } from '../components/VirtualizedTable'
import { Badge } from '../components/Badge'
import { ExportModal } from '../components/ExportModal'
import { FeatureSelector, toFeatureItems } from '../components/FeatureSelector'
import { BatchProgressBanner, readActiveJob, writeActiveJob, type ActiveBatchJob } from '../components/BatchProgressBanner'
import { Tag } from '../components/Tag'
import { Modal } from '../components/Modal'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'
import { ScoreTooltip } from '../components/ScoreTooltip'
import { useDebouncedValue } from '../hooks/useDebouncedValue'

const PAGE_LIMIT = 50

type FeatureStatus = 'draft' | 'reviewed' | 'certified' | 'deprecated'

const FEATURE_STATUSES: readonly FeatureStatus[] = ['draft', 'reviewed', 'certified', 'deprecated'] as const

interface FeatureRow {
  name: string
  has_doc: boolean
  generation_hints: string | null
  dtype: string
  tags: string[]
  owner: string
  column_name: string
  stats: Record<string, number>
  created_at: string
  updated_at: string
  id: string
  data_source_id: string
  description: string
  definition: string | null
  definition_type: string | null
  status?: FeatureStatus
  status_changed_at?: string | null
  status_notes?: string | null
  health_score?: number
  health_grade?: string
  health_breakdown?: { documentation: number; drift: number; usage: number }
  search_score?: number
  highlight?: Record<string, string[]>
  short_description?: string
}

const GRADE_COLORS: Record<string, string> = {
  A: 'bg-green-500/15 text-green-600 dark:text-green-400',
  B: 'bg-teal-500/15 text-teal-600 dark:text-teal-400',
  C: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  D: 'bg-red-500/15 text-red-600 dark:text-red-400',
}

// Status pill semantics:
//   draft      → muted (no signal yet)
//   reviewed   → brand (peer-checked, in flight)
//   certified  → success (sign-off complete)
//   deprecated → danger (don't use; usually struck through too)
// Uses semantic CSS vars so dark/light modes pick up the right contrast.
const STATUS_PILL_CLASSES: Record<FeatureStatus, string> = {
  draft: 'bg-[var(--bg-tertiary)] text-[var(--text-tertiary)] border border-transparent',
  reviewed: 'bg-[var(--brand-subtle-bg)] text-[var(--brand)] border border-[var(--brand-subtle-bg)]',
  certified: 'bg-[var(--success-subtle-bg)] text-[var(--success)] border border-[var(--success-subtle-bg)]',
  deprecated: 'bg-[var(--danger-subtle-bg)] text-[var(--danger)] border border-[var(--danger-subtle-bg)] line-through',
}

function isFeatureStatus(v: string): v is FeatureStatus {
  return (FEATURE_STATUSES as readonly string[]).includes(v)
}

export function Features() {
  const { t } = useTranslation('features')
  const { name: paramName } = useParams()
  const navigate = useNavigate()
  const [features, setFeatures] = useState<FeatureRow[]>([])
  const [sources, setSources] = useState<{ name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [filtered, setFiltered] = useState<FeatureRow[]>([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [selected, setSelected] = useState<FeatureRow | null>(null)
  const [healthFilter, setHealthFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [dtypeFilter, setDtypeFilter] = useState('')
  const [docFilter, setDocFilter] = useState(false)
  const [tagFilter, setTagFilter] = useState('')
  const [searchParams, setSearchParams] = useSearchParams()
  const initialStatus = searchParams.get('status') ?? ''
  const [statusFilter, setStatusFilter] = useState<FeatureStatus | ''>(
    isFeatureStatus(initialStatus) ? initialStatus : ''
  )
  const [selectedForExport, setSelectedForExport] = useState<Set<string>>(new Set())
  const [exportOpen, setExportOpen] = useState(false)
  const [scanModalOpen, setScanModalOpen] = useState(false)
  const [genModalOpen, setGenModalOpen] = useState(false)
  // batchJob is the *trigger* — the banner takes over from here, handles
  // polling + localStorage persistence so a mid-run F5 doesn't lose progress
  // (UAT finding "Auto-generate progress lost on F5/reload"). Lazy init reads
  // localStorage so reloads pre-populate before the banner mounts.
  const [batchJob, setBatchJob] = useState<ActiveBatchJob | null>(() => readActiveJob())

  // Bulk-select toolbar state (T1.3b). `selectedForExport` is also used as
  // the master selection set for bulk-tag, bulk-group, and bulk-delete flows.
  const [bulkAddTagOpen, setBulkAddTagOpen] = useState(false)
  const [bulkAddGroupOpen, setBulkAddGroupOpen] = useState(false)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [bulkBanner, setBulkBanner] = useState<{ kind: 'success' | 'error'; message: string } | null>(null)
  // For shift+click range selection on table rows.
  const lastCheckedRef = useRef<string | null>(null)

  // Pagination state — only consulted in paginated mode (see isPaginated below).
  // pageTotal carries the server's reported total count for "1-50 of 5234".
  const [pageOffset, setPageOffset] = useState(0)
  const [pageTotal, setPageTotal] = useState(0)

  // SearchInput already debounces 300ms internally before firing onSearch, so
  // searchQuery is the post-debounce value — no second debounce needed here.
  // The useDebouncedValue hook stays available for non-debouncing inputs that
  // might want it later.
  void useDebouncedValue  // imported for re-export reference; tree-shaken if unused

  // Paginated mode is the default. The "needs attention" filter (grades C/D)
  // requires full-set health enrichment to filter, which the server's
  // paginated path doesn't do — fall back to the legacy unbounded list there.
  const isPaginated = healthFilter !== 'attention'

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/features')
    const params: Record<string, string> = {}
    if (sourceFilter) params.source = sourceFilter
    if (searchQuery) params.search = searchQuery
    if (dtypeFilter) params.dtype = dtypeFilter
    if (healthFilter === 'A') params.health_grade = 'A'
    if (docFilter) params.has_doc = 'false'
    if (tagFilter) params.tag = tagFilter

    const sourcesPromise = api.sources.list().catch(() => [])

    if (isPaginated) {
      const pagedParams: Record<string, string | number> = { ...params, limit: PAGE_LIMIT, offset: pageOffset }
      Promise.all([api.features.listPaginated(pagedParams), sourcesPromise])
        .then(([res, s]) => {
          const items = (res?.items ?? []) as FeatureRow[]
          // Status filter is applied client-side over the current page slice
          // because the backend list endpoint doesn't yet accept ?status=.
          // For the page-level UX (badge column + chip filter) this is fine
          // — Dashboard tile counts are derived server-wide via the
          // unbounded list to stay accurate.
          const visible = statusFilter ? items.filter(r => r.status === statusFilter) : items
          setFeatures(items)
          setFiltered(visible)
          setPageTotal(res?.total ?? items.length)
          setSources(Array.isArray(s) ? s : [])
        })
        .finally(() => setLoading(false))
      return
    }

    // Legacy unbounded path — used by the "needs attention" filter.
    Promise.all([
      api.features.list(Object.keys(params).length > 0 ? params : undefined),
      sourcesPromise,
    ])
      .then(([f, s]) => {
        let list = Array.isArray(f) ? (f as FeatureRow[]) : []
        list = list.filter((r) => r.health_grade === 'C' || r.health_grade === 'D')
        if (statusFilter) list = list.filter(r => r.status === statusFilter)
        setFeatures(list)
        setFiltered(list)
        setPageTotal(list.length)
        setSources(Array.isArray(s) ? s : [])
      })
      .finally(() => setLoading(false))
  }, [sourceFilter, searchQuery, dtypeFilter, healthFilter, docFilter, tagFilter, statusFilter, isPaginated, pageOffset])

  useEffect(() => { load() }, [load])

  // Whenever any filter changes, reset to page 1 — otherwise a filter that
  // returns fewer rows than the current offset would render an empty page.
  useEffect(() => {
    setPageOffset(0)
  }, [sourceFilter, searchQuery, dtypeFilter, healthFilter, docFilter, tagFilter, statusFilter])

  // Keep the URL ?status=… in sync so Dashboard click-throughs and
  // shareable links round-trip cleanly. Other filters live in component
  // state only — adding them here is out of scope for T3.1b.
  useEffect(() => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev)
        if (statusFilter) next.set('status', statusFilter)
        else next.delete('status')
        return next
      },
      { replace: true }
    )
  }, [statusFilter, setSearchParams])

  // BatchProgressBanner owns the polling loop and persists the active job id
  // to localStorage so a reload mid-run restores the UI. We just react to its
  // onComplete callback to refresh feature data once the batch settles.

  // Auto-open modal from URL param
  useEffect(() => {
    if (paramName && features.length > 0) {
      const decoded = decodeURIComponent(paramName)
      const feat = features.find((f) => f.name === decoded)
      if (feat) setSelected(feat)
    }
  }, [paramName, features])

  const hasActiveFilters = !!(sourceFilter || searchQuery || dtypeFilter || healthFilter || docFilter || tagFilter || statusFilter)

  const clearAllFilters = () => {
    setSourceFilter('')
    setSearchQuery('')
    setDtypeFilter('')
    setHealthFilter('')
    setDocFilter(false)
    setTagFilter('')
    setStatusFilter('')
  }

  const selectFeature = (f: FeatureRow) => {
    setSelected(f)
    navigate(`/features/${encodeURIComponent(f.name)}`, { replace: true })
  }

  const closeModal = () => {
    setSelected(null)
    navigate('/features', { replace: true })
  }

  const undocCount = features.filter((f) => !f.has_doc).length

  const toggleExportSelect = (name: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedForExport(prev => {
      const next = new Set(prev)
      // Shift+click range-select between lastCheckedRef and this row, using
      // the currently-rendered page's order (filtered).
      if (e.shiftKey && lastCheckedRef.current && lastCheckedRef.current !== name) {
        const order = filtered.map(f => f.name)
        const a = order.indexOf(lastCheckedRef.current)
        const b = order.indexOf(name)
        if (a >= 0 && b >= 0) {
          const range = order.slice(Math.min(a, b), Math.max(a, b) + 1)
          // Mirror FeatureSelector: shift-click adds to selection.
          range.forEach(n => next.add(n))
          lastCheckedRef.current = name
          return next
        }
      }
      if (next.has(name)) next.delete(name)
      else next.add(name)
      lastCheckedRef.current = name
      return next
    })
  }

  // Tri-state "select all on current page" header checkbox.
  const pageSelectedCount = filtered.reduce((n, r) => n + (selectedForExport.has(r.name) ? 1 : 0), 0)
  const pageAllSelected = filtered.length > 0 && pageSelectedCount === filtered.length
  const pageSomeSelected = pageSelectedCount > 0 && pageSelectedCount < filtered.length

  const togglePageAll = () => {
    setSelectedForExport(prev => {
      const next = new Set(prev)
      if (pageAllSelected) {
        // Deselect everything on this page (don't touch other pages).
        filtered.forEach(r => next.delete(r.name))
      } else {
        // Select everything on this page.
        filtered.forEach(r => next.add(r.name))
      }
      return next
    })
  }

  const clearSelection = () => {
    setSelectedForExport(new Set())
    lastCheckedRef.current = null
  }

  // Resolve selected names → ids. The bulk endpoints operate on `feature_ids`,
  // but the row state and selection are keyed by name (names are stable across
  // re-fetches; ids may not be present on every loaded row in the future).
  const resolveSelectedIds = (): string[] => {
    const byName = new Map(features.map(f => [f.name, f.id]))
    const ids: string[] = []
    selectedForExport.forEach(name => {
      const id = byName.get(name)
      if (id) ids.push(id)
    })
    return ids
  }

  const columns = [
    {
      key: '_select',
      label: '',
      sortable: false,
      headerRender: () => (
        <input
          type="checkbox"
          aria-label={t('bulk.select_all_on_page')}
          checked={pageAllSelected}
          ref={(el) => { if (el) el.indeterminate = pageSomeSelected }}
          onChange={togglePageAll}
          onClick={(e) => e.stopPropagation()}
          className="accent-accent"
        />
      ),
      render: (r: FeatureRow) => (
        <input
          type="checkbox"
          checked={selectedForExport.has(r.name)}
          onChange={() => undefined}
          onClick={(e) => toggleExportSelect(r.name, e)}
          className="accent-accent"
        />
      ),
    },
    { key: 'name', label: 'Name', render: (r: FeatureRow) => {
      const hl = (r as FeatureRow & { highlight?: Record<string, string[]> }).highlight
      const terms = hl ? [...new Set(Object.values(hl).flat())] : []
      return <span className="font-medium text-brand"><HighlightedText text={r.name} terms={terms} /></span>
    }},
    { key: 'source', label: 'Source', sortable: false, render: (r: FeatureRow) => <span className="text-[var(--text-secondary)]">{r.name?.split('.')[0] || ''}</span> },
    { key: 'dtype', label: 'Dtype', render: (r: FeatureRow) => <span className="font-mono text-xs">{r.dtype}</span> },
    { key: 'status', label: t('columns.status'), sortable: false, render: (r: FeatureRow) => {
      const s = (r.status && isFeatureStatus(r.status)) ? r.status : 'draft'
      return (
        <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium ${STATUS_PILL_CLASSES[s]}`}>
          {t(`status.${s}`)}
        </span>
      )
    }},
    { key: 'tags', label: 'Tags', sortable: false, render: (r: FeatureRow) => (
      <div className="flex gap-1 flex-wrap">{(r.tags || []).map((t: string, i: number) => <Tag key={i}>{t}</Tag>)}</div>
    )},
    { key: 'has_doc', label: 'Docs', render: (r: FeatureRow) => r.has_doc ? <Check size={14} className="text-[var(--success)]" /> : <span className="text-[var(--text-tertiary)]">-</span> },
    { key: 'health_score', label: 'Health', render: (r: FeatureRow) => {
      const searchScore = (r as FeatureRow & { search_score?: number }).search_score
      if (searchScore != null) {
        const pct = Math.round(searchScore * 100)
        return (
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
              <div className="h-full bg-brand rounded-full" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[11px] font-mono text-[var(--text-tertiary)]">{pct}%</span>
          </div>
        )
      }
      const grade = r.health_grade || '-'
      const score = r.health_score ?? '-'
      const cls = GRADE_COLORS[grade] || 'bg-[var(--bg-secondary)] text-[var(--text-tertiary)]'
      return <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold ${cls}`}>{grade} {score}</span>
    }},
    { key: 'owner', label: 'Owner' },
  ]

  return (
    <div>
      <PageHeader
        title={t('page.title')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('count_label', { count: pageTotal })}</span>
            <RefreshButton onClick={load} loading={loading} />
          </>
        }
      />

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <SearchInput placeholder={t('search_placeholder')} onSearch={setSearchQuery} className="w-full sm:max-w-xs" />
        <FilterSelect
          ariaLabel={t('filters.all_sources')}
          value={sourceFilter}
          onChange={setSourceFilter}
          options={[
            { value: '', label: t('filters.all_sources') },
            ...sources.map((s) => ({ value: s.name, label: s.name })),
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_types')}
          value={dtypeFilter}
          onChange={setDtypeFilter}
          options={[
            { value: '', label: t('filters.all_types') },
            { value: 'int64', label: 'int64' },
            { value: 'float64', label: 'float64' },
            { value: 'string', label: 'string' },
            { value: 'bool', label: 'bool' },
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_grades')}
          value={healthFilter}
          onChange={setHealthFilter}
          options={[
            { value: '', label: t('filters.all_grades') },
            { value: 'attention', label: t('filters.needs_attention') },
            { value: 'A', label: t('filters.grade_only', { grade: 'A' }) },
          ]}
        />
        <FilterSelect<FeatureStatus | ''>
          ariaLabel={t('filters.all_statuses')}
          value={statusFilter}
          onChange={(v) => setStatusFilter(isFeatureStatus(v) ? v : '')}
          options={[
            { value: '', label: t('filters.all_statuses') },
            ...FEATURE_STATUSES.map((s) => ({ value: s, label: t(`status.${s}`) })),
          ]}
        />
        <button
          onClick={() => setDocFilter(!docFilter)}
          className={`px-3 py-2 text-[13px] rounded-lg border transition-colors ${docFilter ? 'bg-brand text-white border-brand' : 'bg-[var(--bg-primary)] border-[var(--border-default)] hover:bg-[var(--bg-secondary)]'}`}
        >
          {t('actions.undocumented_only')}
        </button>
        <FilterClearLink show={hasActiveFilters} onClick={clearAllFilters} label={t('actions.clear_all_filters')} />
        {(undocCount > 0 || batchJob !== null) && (
          <button
            onClick={() => !batchJob && setGenModalOpen(true)}
            disabled={batchJob !== null}
            className="flex items-center gap-1.5 px-4 py-2 border border-[var(--border-default)] rounded-lg text-[13px] font-medium hover:bg-[var(--bg-secondary)] disabled:opacity-50 transition-colors"
          >
            {batchJob ? (
              <BatchProgressBanner
                job={batchJob}
                onComplete={() => {
                  setBatchJob(null)
                  invalidateCache('/features')
                  invalidateCache('/docs')
                  load()
                }}
              />
            ) : (
              <><FileText size={14} /> {t('actions.generate_docs_remaining', { count: undocCount })}</>
            )}
          </button>
        )}
        <button onClick={() => setScanModalOpen(true)} className="flex items-center gap-1.5 px-4 py-2 border border-[var(--border-default)] rounded-lg text-[13px] font-medium hover:bg-[var(--bg-secondary)] transition-colors">
          <FolderSearch size={16} /> {t('actions.bulk_scan')}
        </button>
        {selectedForExport.size > 0 && (
          <button onClick={() => setExportOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-brand text-white rounded-lg text-[13px] font-medium hover:bg-brand-emphasis transition-colors">
            <Download size={16} /> {t('actions.export_selected', { count: selectedForExport.size })}
          </button>
        )}
      </div>

      {bulkBanner && (
        <Alert
          severity={bulkBanner.kind === 'success' ? 'success' : 'danger'}
          message={bulkBanner.message}
          dismissible
          onDismiss={() => setBulkBanner(null)}
          className="mb-3"
        />
      )}

      {selectedForExport.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-brand/40 bg-brand/10 px-3 py-2">
          <span className="text-[13px] font-medium text-brand">
            {t('bulk.n_selected', { count: selectedForExport.size })}
          </span>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              onClick={() => setBulkAddTagOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-1.5 text-[12px] font-medium hover:bg-[var(--bg-secondary)]"
            >
              <TagIcon size={13} /> {t('bulk.add_tag')}
            </button>
            <button
              onClick={() => setBulkAddGroupOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-1.5 text-[12px] font-medium hover:bg-[var(--bg-secondary)]"
            >
              <FolderPlus size={13} /> {t('bulk.add_to_group')}
            </button>
            <button
              onClick={() => setBulkDeleteOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-[var(--danger)]/40 bg-[var(--bg-primary)] px-3 py-1.5 text-[12px] font-medium text-[var(--danger)] hover:bg-[var(--danger)]/10"
            >
              <Trash2 size={13} /> {t('bulk.delete')}
            </button>
            <button
              onClick={clearSelection}
              className="flex items-center gap-1 text-[12px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              <X size={12} /> {t('bulk.clear_selection')}
            </button>
          </div>
        </div>
      )}

      <div data-testid="features-list" className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden p-3">
        {loading && features.length === 0 ? (
          <Skeleton className="h-48" />
        ) : isPaginated ? (
          <VirtualizedTable
            columns={columns}
            data={filtered}
            onRowClick={selectFeature}
            total={pageTotal}
            limit={PAGE_LIMIT}
            offset={pageOffset}
            onPageChange={setPageOffset}
            loading={loading}
          />
        ) : (
          // "Needs attention" filter — falls back to client-side pagination
          // because health-grade filtering needs full-set enrichment that the
          // server's paginated path doesn't compute.
          <DataTable columns={columns} data={filtered} onRowClick={selectFeature} />
        )}
      </div>

      {selected && (
        <FeatureDetailModal feature={selected} onClose={closeModal} onDocGenerated={load} />
      )}

      <GenerateDocsModal
        open={genModalOpen}
        onClose={() => setGenModalOpen(false)}
        features={features}
        selectedSpecs={selectedForExport}
        onStarted={(jobId, total) => {
          setGenModalOpen(false)
          const next: ActiveBatchJob = { jobId, total }
          writeActiveJob(next)
          setBatchJob(next)
        }}
      />
      <BulkScanModal open={scanModalOpen} onClose={() => setScanModalOpen(false)} onDone={() => { setScanModalOpen(false); load() }} />
      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        title={t('count_label', { count: selectedForExport.size })}
        featureSpecs={[...selectedForExport]}
      />

      <BulkAddTagModal
        open={bulkAddTagOpen}
        onClose={() => setBulkAddTagOpen(false)}
        selectedCount={selectedForExport.size}
        onConfirm={async (tag) => {
          const ids = resolveSelectedIds()
          if (ids.length === 0) return
          try {
            const res = await api.bulk.tags({ feature_ids: ids, action: 'add', tags: [tag] })
            setBulkBanner({
              kind: 'success',
              message: t('bulk.banner.tag_success', { tag, updated: res.updated, requested: res.requested }),
            })
            setBulkAddTagOpen(false)
            invalidateCache('/features')
            load()
          } catch (e) {
            setBulkBanner({ kind: 'error', message: (e as Error).message })
          }
        }}
      />

      <BulkAddToGroupModal
        open={bulkAddGroupOpen}
        onClose={() => setBulkAddGroupOpen(false)}
        selectedCount={selectedForExport.size}
        onConfirm={async (group) => {
          const ids = resolveSelectedIds()
          if (ids.length === 0) return
          try {
            const res = await api.bulk.groups({
              feature_ids: ids,
              action: 'add_to',
              group_id: group.id,
            })
            setBulkBanner({
              kind: 'success',
              message: t('bulk.banner.group_success', {
                group: group.name,
                changed: res.changed,
                requested: res.requested,
              }),
            })
            setBulkAddGroupOpen(false)
            invalidateCache('/features')
            invalidateCache('/groups')
            load()
          } catch (e) {
            setBulkBanner({ kind: 'error', message: (e as Error).message })
          }
        }}
      />

      <BulkDeleteModal
        open={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        names={[...selectedForExport]}
        onConfirm={async () => {
          const ids = resolveSelectedIds()
          if (ids.length === 0) return
          try {
            const res = await api.bulk.delete({ feature_ids: ids, confirm: true })
            setBulkBanner({
              kind: 'success',
              message: t('bulk.banner.delete_success', { deleted: res.deleted, requested: res.requested }),
            })
            setBulkDeleteOpen(false)
            clearSelection()
            invalidateCache('/features')
            load()
          } catch (e) {
            setBulkBanner({ kind: 'error', message: (e as Error).message })
          }
        }}
      />
    </div>
  )
}


function FeatureDetailModal({ feature, onClose, onDocGenerated }: { feature: FeatureRow; onClose: () => void; onDocGenerated: () => void }) {
  const { t } = useTranslation('features')
  const [doc, setDoc] = useState<Record<string, unknown> | null>(null)
  const [docLoading, setDocLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [monitoring, setMonitoring] = useState<Record<string, unknown> | null>(null)
  const [monLoading, setMonLoading] = useState(true)
  const [blLoading, setBlLoading] = useState(false)
  const [definition, setDefinition] = useState<Record<string, unknown> | null>(null)
  const [defLoading, setDefLoading] = useState(true)
  const [defEditing, setDefEditing] = useState(false)
  const [defForm, setDefForm] = useState({ definition: '', definition_type: 'sql' })
  const [usageData, setUsageData] = useState<Record<string, unknown> | null>(null)
  const [usageLoading, setUsageLoading] = useState(true)
  const [hintData, setHintData] = useState<{ hints: string | null } | null>(null)
  const [hintEditing, setHintEditing] = useState(false)
  const [hintDraft, setHintDraft] = useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'history'>('overview')
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)

  useEffect(() => {
    setDocLoading(true)
    setMonLoading(true)
    setDefLoading(true)
    setUsageLoading(true)
    api.docs.get(feature.name).then(setDoc).catch(() => setDoc(null)).finally(() => setDocLoading(false))
    api.monitor.check({ feature_name: feature.name }).then(setMonitoring).catch(() => setMonitoring(null)).finally(() => setMonLoading(false))
    api.definitions.get(feature.name).then(setDefinition).catch(() => setDefinition(null)).finally(() => setDefLoading(false))
    api.usage.feature(feature.name, 30).then(setUsageData).catch(() => setUsageData(null)).finally(() => setUsageLoading(false))
    api.hints.get(feature.name).then(setHintData).catch(() => setHintData(null))
    setActiveTab('overview')
    setVersionsLoading(true)
    api.features.versions(feature.name).then(setVersions).catch(() => setVersions([])).finally(() => setVersionsLoading(false))
  }, [feature.name])

  const generateDoc = async () => {
    setGenerating(true)
    try {
      await api.docs.generate({ feature_name: feature.name })
      invalidateCache('/docs')
      invalidateCache('/features')
      const d = await api.docs.get(feature.name)
      setDoc(d)
      onDocGenerated()
    } catch { /* ignore */ }
    setGenerating(false)
  }

  const computeBaseline = async () => {
    setBlLoading(true)
    try {
      await api.monitor.baseline()
      invalidateCache('/monitor')
      const m = await api.monitor.check({ feature_name: feature.name })
      setMonitoring(m)
    } catch { /* ignore */ }
    setBlLoading(false)
  }

  const stats = feature.stats || {}
  const source = feature.name?.split('.')[0] || ''
  const statKeys = ['mean', 'std', 'min', 'max', 'null_ratio', 'unique_count']
  const hasStats = statKeys.some((k) => stats[k] != null)

  return (
    <Modal open={true} onClose={onClose} title={feature.name} maxWidth="max-w-2xl">
      {/* Tab bar */}
      <div className="flex gap-4 border-b border-[var(--border-subtle)] mb-5">
        <button
          onClick={() => setActiveTab('overview')}
          className={`pb-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'overview' ? 'border-brand text-brand' : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'}`}
        >{t('tabs.overview')}</button>
        <button
          onClick={() => setActiveTab('history')}
          className={`pb-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'history' ? 'border-brand text-brand' : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'}`}
        >{t('actions.history_tab', { count: versions.length })}</button>
      </div>

      {activeTab === 'history' ? (
        <VersionTimeline versions={versions} loading={versionsLoading} />
      ) : (<>

      {/* Header badges */}
      <div className="flex items-center gap-2 flex-wrap mb-5">
        <Badge variant="info">{source}</Badge>
        {(feature.tags || []).map((t: string, i: number) => <Tag key={i}>{t}</Tag>)}
      </div>

      {/* Health Score */}
      {feature.health_score != null && (
        <Section title={t('sections.health_score')} glossaryKey="health_score">
          <HealthBreakdown feature={feature} />
        </Section>
      )}

      {/* Metadata */}
      <Section title={t('sections.metadata')}>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4">
          <MetaItem label={t('meta.data_type')} value={feature.dtype} mono />
          <MetaItem label={t('meta.column')} value={feature.column_name} mono />
          <MetaItem label={t('meta.owner')} value={feature.owner || '-'} />
          {feature.created_at && <MetaItem label={t('meta.created')} value={timeAgo(feature.created_at)} />}
          {feature.updated_at && <MetaItem label={t('meta.updated')} value={timeAgo(feature.updated_at)} />}
        </div>
      </Section>

      {/* Statistics */}
      {hasStats && (
        <Section title={t('sections.statistics')}>
          <div className="grid grid-cols-3 gap-x-6 gap-y-4">
            {([
              { label: t('stats.mean'),         value: stats.mean,         format: 'decimal' as const },
              { label: t('stats.std'),          value: stats.std,          format: 'decimal' as const },
              { label: t('stats.min'),          value: stats.min,          format: 'decimal' as const },
              { label: t('stats.max'),          value: stats.max,          format: 'decimal' as const },
              { label: t('stats.null_ratio'),   value: stats.null_ratio,   format: 'decimal' as const },
              { label: t('stats.unique_count'), value: stats.unique_count, format: 'integer' as const },
            ])
              .filter(s => s.value !== null && s.value !== undefined)
              .map(s => (
                <div key={s.label}>
                  <div className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)] font-medium mb-1">
                    {s.label}
                  </div>
                  <div className="text-sm font-mono text-[var(--text-primary)] tabular-nums">
                    {s.format === 'integer'
                      ? Math.round(s.value as number).toLocaleString()
                      : (s.value as number).toFixed(4)}
                  </div>
                </div>
              ))}
          </div>
        </Section>
      )}

      {/* Specification (Definition) */}
      <Section title={t('sections.definition')}>
        {defLoading ? (
          <Skeleton className="h-10" />
        ) : defEditing ? (
          <div className="space-y-2">
            <select value={defForm.definition_type} onChange={(e) => setDefForm((f) => ({ ...f, definition_type: e.target.value }))}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2 py-1 text-xs">
              <option value="sql">SQL</option>
              <option value="python">{t('definition.types.python')}</option>
              <option value="manual">{t('definition.types.manual')}</option>
            </select>
            <textarea value={defForm.definition} onChange={(e) => setDefForm((f) => ({ ...f, definition: e.target.value }))}
              rows={4} className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-xs font-mono focus:border-brand outline-none" />
            <div className="flex gap-2">
              <button onClick={async () => {
                await api.definitions.save(feature.name, defForm)
                invalidateCache('/features')
                const d = await api.definitions.get(feature.name)
                setDefinition(d)
                setDefEditing(false)
              }} className="px-3 py-1.5 text-xs bg-brand text-white rounded-lg">{t('actions.save', { ns: 'common' })}</button>
              <button onClick={() => setDefEditing(false)} className="px-3 py-1.5 text-xs border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
            </div>
          </div>
        ) : definition?.definition ? (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="info">{String(definition.definition_type)}</Badge>
              <button onClick={() => { setDefForm({ definition: String(definition.definition), definition_type: String(definition.definition_type) }); setDefEditing(true) }}
                className="text-xs text-brand hover:underline">{t('actions.edit', { ns: 'common' })}</button>
            </div>
            <pre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap">{String(definition.definition)}</pre>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">{t('definition.empty')}</span>
            <button onClick={() => { setDefForm({ definition: '', definition_type: 'sql' }); setDefEditing(true) }}
              className="text-xs text-brand hover:underline">{t('definition.add')}</button>
          </div>
        )}
      </Section>

      {/* Data Profile (Documentation) */}
      <Section title={t('sections.documentation')}>
        {docLoading ? (
          <Skeleton className="h-12" />
        ) : doc ? (
          <div className="space-y-2 text-sm">
            <div className="mb-1 flex items-center gap-2 flex-wrap">
              <Badge variant="info">
                {t('documentation.ai_generated_label')}
                {doc.generated_at ? ` · ${timeAgo(String(doc.generated_at))}` : ''}
              </Badge>
              <button
                onClick={generateDoc}
                disabled={generating}
                className="inline-flex items-center gap-1 text-xs text-brand hover:underline disabled:opacity-50"
              >
                <RefreshCw size={11} className={generating ? 'animate-spin' : ''} />
                {generating ? t('actions.generating', { ns: 'common' }) : t('actions.regenerate', { ns: 'common' })}
              </button>
            </div>
            <p>{String(doc.short_description || '')}</p>
            {doc.long_description ? <p className="text-[var(--text-secondary)]">{String(doc.long_description)}</p> : null}
            {doc.expected_range ? (
              <p className="text-xs text-[var(--text-tertiary)]">
                <span className="font-medium">{t('documentation.expected_range')}</span> {String(doc.expected_range)}
              </p>
            ) : null}
            {doc.potential_issues ? (
              <p className="text-xs text-[var(--text-tertiary)]">
                <span className="font-medium">{t('documentation.potential_issues')}</span> {String(doc.potential_issues)}
              </p>
            ) : null}
            {(doc.context_features || doc.hints_used) ? (
              <div className="mt-2 pt-2 border-t border-[var(--border-subtle)] flex items-center gap-2 flex-wrap text-[11px] text-[var(--text-tertiary)]">
                {doc.hints_used ? <Badge variant="info">{t('documentation.hints_used')}</Badge> : null}
                {doc.context_features ? (
                  <span>{t('documentation.context', { count: JSON.parse(String(doc.context_features)).length })}</span>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div>
              <div className="text-sm text-[var(--text-tertiary)]">{t('documentation.empty')}</div>
              <div className="text-xs text-[var(--text-tertiary)] mt-0.5">{t('documentation.empty_hint')}</div>
            </div>
            <button onClick={generateDoc} disabled={generating} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-white rounded-lg disabled:opacity-50">
              <RefreshCw size={12} className={generating ? 'animate-spin' : ''} />
              {generating ? t('actions.generating', { ns: 'common' }) : t('actions.generate', { ns: 'common' })}
            </button>
          </div>
        )}
      </Section>

      {/* Generation Hints */}
      <Section title={t('sections.generation_hints')}>
        {hintEditing ? (
          <div className="space-y-2">
            <textarea value={hintDraft} onChange={(e) => setHintDraft(e.target.value)} rows={2}
              placeholder=""
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-xs focus:border-brand outline-none" />
            <div className="flex gap-2">
              <button onClick={async () => {
                await api.hints.save(feature.name, hintDraft)
                invalidateCache('/features')
                setHintData({ hints: hintDraft })
                setHintEditing(false)
              }} className="px-3 py-1.5 text-xs bg-brand text-white rounded-lg">{t('actions.save', { ns: 'common' })}</button>
              <button onClick={() => setHintEditing(false)} className="px-3 py-1.5 text-xs border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
            </div>
          </div>
        ) : hintData?.hints ? (
          <div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">{hintData.hints}</p>
            <button onClick={() => { setHintDraft(hintData.hints || ''); setHintEditing(true) }}
              className="text-xs text-brand hover:underline">{t('actions.edit', { ns: 'common' })}</button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">{t('hints.empty')}</span>
            <button onClick={() => { setHintDraft(''); setHintEditing(true) }}
              className="text-xs text-brand hover:underline">{t('hints.add')}</button>
            <span className="text-[10px] text-[var(--text-tertiary)]" title={t('hints.info_tooltip')}>ℹ</span>
          </div>
        )}
      </Section>

      {/* Usage */}
      <Section title={t('sections.usage')}>
        {usageLoading ? (
          <Skeleton className="h-10" />
        ) : usageData ? (
          <div>
            <p className="text-sm">
              <span className="font-medium">{Number(usageData.views || 0)}</span> {t('usage.views_label')}
              {' \u00b7 '}
              <span className="font-medium">{Number(usageData.queries || 0)}</span> {t('usage.queries_label')}
              <span className="text-[var(--text-tertiary)]"> {t('usage.last_30_days')}</span>
            </p>
            {(usageData.daily as { date: string; count: number }[] | undefined)?.length ? <MiniBarChart data={usageData.daily as { date: string; count: number }[]} /> : null}
            {usageData.last_seen ? (
              <p className="text-xs text-[var(--text-tertiary)] mt-1">{t('usage.last_seen', { time: timeAgo(String(usageData.last_seen)) })}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-[var(--text-tertiary)]">{t('usage.empty')}</p>
        )}
      </Section>

      {/* Monitoring */}
      <Section title={t('sections.monitoring')} last>
        {monLoading ? (
          <Skeleton className="h-10" />
        ) : (() => { const details = (monitoring?.details || []) as { severity: string; psi: number | null; checked_at?: string }[]; return details.length > 0 })() ? (
          <div className="flex items-center gap-4 flex-wrap">
            {(() => {
              const details = (monitoring?.details || []) as { severity: string; psi: number | null; checked_at?: string }[]
              const r = details[0]
              const status = r.severity || 'unknown'
              const variant = status === 'healthy' ? 'success' : status === 'warning' ? 'warning' : status === 'critical' ? 'critical' : 'info'
              return (
                <>
                  <Badge variant={variant} icon={status === 'healthy' ? Shield : AlertTriangle}>
                    {status}
                  </Badge>
                  {r.psi != null && <span className="text-xs text-[var(--text-secondary)]">PSI: {r.psi.toFixed(4)}</span>}
                  {r.checked_at && <span className="text-xs text-[var(--text-tertiary)]">{t('monitoring.checked', { time: timeAgo(r.checked_at) })}</span>}
                </>
              )
            })()}
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">{t('monitoring.empty')}</span>
            <button onClick={computeBaseline} disabled={blLoading} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-brand text-white rounded-lg disabled:opacity-50">
              {blLoading ? t('actions.computing') : t('actions.compute_baseline')}
            </button>
          </div>
        )}
      </Section>
      </>)}
    </Modal>
  )
}


function Section({ title, children, last, glossaryKey }: { title: string; children: React.ReactNode; last?: boolean; glossaryKey?: string }) {
  return (
    <div className={last ? '' : 'mb-4 pb-4 border-b border-[var(--border-subtle)]'}>
      <h4 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2.5 flex items-center gap-1">
        <span>{title}</span>
        {glossaryKey && <ScoreTooltip name={glossaryKey} iconOnly />}
      </h4>
      {children}
    </div>
  )
}


function MetaItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wide">{label}</div>
      <div className={`text-sm ${mono ? 'font-mono' : ''}`}>{value || '-'}</div>
    </div>
  )
}


function GenerateDocsModal({ open, onClose, features, selectedSpecs, onStarted }: {
  open: boolean
  onClose: () => void
  features: FeatureRow[]
  selectedSpecs?: Set<string>
  onStarted: (jobId: string, total: number) => void
}) {
  const { t } = useTranslation('features')
  const [scope, setScope] = useState<'undocumented' | 'all' | 'group' | 'selected'>('undocumented')
  const [globalHint, setGlobalHint] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [editingHint, setEditingHint] = useState<string | null>(null)
  const [hintDrafts, setHintDrafts] = useState<Record<string, string>>({})
  const [hintsOverrides, setHintsOverrides] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [groups, setGroups] = useState<{ name: string; member_count: number }[]>([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [groupMembers, setGroupMembers] = useState<string[]>([])
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set())

  const undocumented = features.filter(f => !f.has_doc)
  const hasTableSelection = (selectedSpecs?.size ?? 0) > 0

  let targetFeatures: FeatureRow[]
  if (scope === 'group') {
    targetFeatures = features.filter(f => groupMembers.includes(f.name))
  } else if (scope === 'selected') {
    targetFeatures = features.filter(f => manualSelected.has(f.name))
  } else if (scope === 'all') {
    targetFeatures = features
  } else {
    targetFeatures = undocumented
  }
  const targetCount = targetFeatures.length
  const canGenerate = targetCount > 0 && !(scope === 'group' && !selectedGroup)

  const getHint = (f: FeatureRow) => hintsOverrides[f.name] ?? f.generation_hints

  const saveHint = async (featureName: string) => {
    const draft = hintDrafts[featureName] ?? ''
    try {
      await api.hints.save(featureName, draft)
      setHintsOverrides(prev => ({ ...prev, [featureName]: draft }))
      setEditingHint(null)
    } catch { /* ignore */ }
  }

  const handleGenerate = async () => {
    if (!canGenerate) return
    setSubmitting(true)
    try {
      const specs = targetFeatures.map(f => f.name)
      const res = await api.docs.generateBatch({
        feature_specs: specs,
        regenerate_existing: scope === 'all',
        global_hint: globalHint.trim() || null,
      })
      onStarted(res.job_id, res.total)
    } catch { /* ignore */ }
    setSubmitting(false)
  }

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setScope(hasTableSelection ? 'selected' : 'undocumented')
      setGlobalHint('')
      setShowPreview(false)
      setEditingHint(null)
      setHintDrafts({})
      setHintsOverrides({})
      setSubmitting(false)
      setSelectedGroup('')
      setGroupMembers([])
      setManualSelected(new Set(selectedSpecs || []))
      api.groups.list().then(g => setGroups(Array.isArray(g) ? g : [])).catch(() => setGroups([]))
    }
  }, [open, hasTableSelection])

  // Fetch group members when group selection changes
  useEffect(() => {
    if (scope === 'group' && selectedGroup) {
      api.groups.get(selectedGroup)
        .then((g: Record<string, unknown>) => {
          const members = (g.members || []) as { name: string }[]
          setGroupMembers(members.map(m => m.name))
        })
        .catch(() => setGroupMembers([]))
    }
  }, [scope, selectedGroup])

  return (
    <Modal open={open} onClose={onClose} title={t('generate_modal.title')} maxWidth="max-w-2xl" actions={
      <>
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
        <button onClick={handleGenerate} disabled={submitting || !canGenerate}
          className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50">
          {submitting ? 'Starting...' : `Generate ${targetCount} Docs`}
        </button>
      </>
    }>
      <div className="space-y-5">
        {/* Scope selector */}
        <div>
          <label className="block text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">{t('generate_modal.scope_label')}</label>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="radio" name="scope" checked={scope === 'undocumented'} onChange={() => setScope('undocumented')} className="accent-accent" />
              All undocumented ({undocumented.length} features)
            </label>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="radio" name="scope" checked={scope === 'all'} onChange={() => setScope('all')} className="accent-accent" />
              All features — regenerate existing docs too ({features.length} features)
            </label>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="radio" name="scope" checked={scope === 'group'} onChange={() => setScope('group')} className="accent-accent" />
              By feature group
            </label>
            {scope === 'group' && (
              <div className="ml-6">
                <select
                  value={selectedGroup}
                  onChange={e => setSelectedGroup(e.target.value)}
                  className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
                >
                  <option value="">Select a group...</option>
                  {groups.map(g => (
                    <option key={g.name} value={g.name}>
                      {g.name} ({g.member_count ?? 0} features)
                    </option>
                  ))}
                </select>
                {!selectedGroup && (
                  <p className="text-[11px] text-[var(--text-tertiary)] mt-1">{t('generate_modal.select_group_hint')}</p>
                )}
                {selectedGroup && groupMembers.length > 0 && (
                  <p className="text-[11px] text-brand mt-1">
                    Will generate docs for {groupMembers.length} features in group {selectedGroup}
                  </p>
                )}
              </div>
            )}
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input
                type="radio"
                name="scope"
                checked={scope === 'selected'}
                onChange={() => setScope('selected')}
                className="accent-accent"
              />
              Selected features ({manualSelected.size})
            </label>
            {scope === 'selected' && (
              <div className="ml-6 mt-2">
                <FeatureSelector
                  features={toFeatureItems(features as unknown as Record<string, unknown>[])}
                  selected={manualSelected}
                  onChange={setManualSelected}
                  showAISuggest={false}
                  maxHeight="240px"
                />
              </div>
            )}
          </div>
        </div>

        {/* Global hint */}
        <div>
          <label className="block text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">{t('generate_modal.batch_hint_label')}</label>
          <textarea
            value={globalHint}
            onChange={(e) => setGlobalHint(e.target.value)}
            rows={2}
            placeholder="e.g. All features are computed from the last 30 days of usage data."
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none resize-none"
          />
          <p className="text-[11px] text-[var(--text-tertiary)] mt-1">Applied to all features in this batch. Individual feature hints take priority.</p>
        </div>

        {/* Preview table toggle */}
        <div>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="flex items-center gap-1.5 text-[13px] font-medium text-brand hover:underline"
          >
            {showPreview ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {showPreview ? 'Hide' : 'Show'} features to be documented ({targetCount})
          </button>

          {showPreview && (
            <div className="mt-2 max-h-60 overflow-y-auto overscroll-contain border border-[var(--border-subtle)] rounded-lg">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-[var(--text-tertiary)] border-b border-[var(--border-default)] bg-[var(--bg-secondary)] sticky top-0">
                    <th className="text-left py-1.5 px-2 font-medium">{t('generate_modal.table.feature')}</th>
                    <th className="text-left py-1.5 px-2 font-medium">{t('generate_modal.table.individual_hint')}</th>
                    <th className="text-center py-1.5 px-2 font-medium">{t('generate_modal.table.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {targetFeatures.map(f => {
                    const hint = getHint(f)
                    const isEditing = editingHint === f.name
                    return (
                      <tr key={f.name} className="border-b border-[var(--border-subtle)]">
                        <td className="py-1.5 px-2 font-mono text-[11px] max-w-[180px] truncate" title={f.name}>{f.name}</td>
                        <td className="py-1.5 px-2">
                          {isEditing ? (
                            <div className="space-y-1">
                              <textarea
                                value={hintDrafts[f.name] ?? hint ?? ''}
                                onChange={(e) => setHintDrafts(prev => ({ ...prev, [f.name]: e.target.value }))}
                                rows={2}
                                className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded px-2 py-1 text-[11px] focus:border-brand outline-none resize-none"
                                placeholder="Add a hint..."
                              />
                              <div className="flex gap-1">
                                <button onClick={() => saveHint(f.name)} className="px-2 py-0.5 text-[10px] bg-brand text-white rounded">{t('actions.save', { ns: 'common' })}</button>
                                <button onClick={() => setEditingHint(null)} className="px-2 py-0.5 text-[10px] border border-[var(--border-default)] rounded">{t('actions.cancel', { ns: 'common' })}</button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1">
                              {hint ? (
                                <span className="text-[11px] text-[var(--text-secondary)] truncate max-w-[150px]" title={hint}>{hint}</span>
                              ) : (
                                <span className="text-[11px] text-[var(--text-tertiary)]">none</span>
                              )}
                              <button
                                onClick={() => { setHintDrafts(prev => ({ ...prev, [f.name]: hint ?? '' })); setEditingHint(f.name) }}
                                className="text-[var(--text-tertiary)] hover:text-brand shrink-0 p-0.5"
                                title={t('generate_modal.edit_hint_title')}
                              >
                                <Pencil size={10} />
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="py-1.5 px-2 text-center">
                          {f.has_doc
                            ? <Badge variant="success">has doc</Badge>
                            : <Badge variant="warning">no doc</Badge>
                          }
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Summary */}
        <p className="text-sm text-[var(--text-secondary)]">
          Will generate docs for <span className="font-semibold">{targetCount}</span> feature{targetCount !== 1 ? 's' : ''}.
          {globalHint.trim() && ` Global hint will be applied to features without individual hints.`}
        </p>
      </div>
    </Modal>
  )
}


function BulkScanModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation('features')
  const [form, setForm] = useState({ path: '', recursive: true, owner: localStorage.getItem('featcat_user') || '', dry_run: false })
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const addTag = () => {
    const t = tagInput.trim()
    if (t && !tags.includes(t)) setTags([...tags, t])
    setTagInput('')
  }

  const submit = async () => {
    setScanning(true)
    try {
      const res = await api.scanBulk({ path: form.path, recursive: form.recursive, owner: form.owner, tags, dry_run: form.dry_run })
      setResult(res)
      if (!form.dry_run) {
        invalidateCache('/features')
        invalidateCache('/sources')
      }
    } catch { /* ignore */ }
    setScanning(false)
  }

  const reset = () => {
    setResult(null)
    setForm({ path: '', recursive: true, owner: localStorage.getItem('featcat_user') || '', dry_run: false })
    setTags([])
  }

  return (
    <Modal open={open} onClose={() => { reset(); onClose() }} title={t('bulk_scan_modal.title')} maxWidth="max-w-lg" actions={
      result ? (
        <button onClick={() => { reset(); onDone() }} className="px-4 py-2 text-sm bg-brand text-white rounded-lg">{t('actions.done', { ns: 'common' })}</button>
      ) : (
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
          <button onClick={submit} disabled={!form.path || scanning} className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50">
            {scanning ? 'Scanning...' : 'Scan'}
          </button>
        </>
      )
    }>
      {result ? (
        <div className="space-y-3">
          <p className="text-sm">
            Found <span className="font-medium">{result.found as number}</span> files.
            {form.dry_run ? ' (dry run)' : (
              <> Registered <span className="font-medium">{result.registered_sources as number}</span> new sources,{' '}
              <span className="font-medium">{result.registered_features as number}</span> new features.
              {(result.skipped as number) > 0 && <> Skipped <span className="font-medium">{result.skipped as number}</span> already registered.</>}</>
            )}
          </p>
          {((result.details || []) as { file: string; status: string; feature_count: number }[]).length > 0 && (
            <div className="max-h-48 overflow-y-auto overscroll-contain">
              <table className="w-full text-[13px]">
                <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                  <th className="text-left py-1">{t('bulk_scan_modal.table.file')}</th>
                  <th className="text-left py-1">{t('bulk_scan_modal.table.status')}</th>
                  <th className="text-right py-1">{t('bulk_scan_modal.table.features')}</th>
                </tr></thead>
                <tbody>
                  {((result.details || []) as { file: string; status: string; feature_count: number }[]).map((d, i) => (
                    <tr key={i} className="border-b border-[var(--border-subtle)]">
                      <td className="py-1 truncate max-w-[200px]">{d.file.split('/').pop()}</td>
                      <td className="py-1"><Badge variant={d.status === 'registered' || d.status === 'would_register' ? 'success' : d.status === 'skipped' ? 'warning' : 'error'}>{d.status}</Badge></td>
                      <td className="py-1 text-right font-mono">{d.feature_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('bulk_scan_modal.directory_path')} <span className="text-[var(--danger)]">*</span></label>
            <input value={form.path} onChange={(e) => setForm((f) => ({ ...f, path: e.target.value }))} placeholder="/path/to/data"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none" />
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="checkbox" checked={form.recursive} onChange={(e) => setForm((f) => ({ ...f, recursive: e.target.checked }))} className="accent-accent" />
              {t('bulk_scan_modal.recursive')}
            </label>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="checkbox" checked={form.dry_run} onChange={(e) => setForm((f) => ({ ...f, dry_run: e.target.checked }))} className="accent-accent" />
              {t('bulk_scan_modal.dry_run')}
            </label>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('bulk_scan_modal.owner')}</label>
            <input value={form.owner} onChange={(e) => setForm((f) => ({ ...f, owner: e.target.value }))} placeholder={t('bulk_scan_modal.owner_placeholder')}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('bulk_scan_modal.tags')}</label>
            <div className="flex gap-1 flex-wrap mb-1">
              {tags.map((t) => (
                <span key={t} className="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--bg-tertiary)] rounded text-xs font-mono">
                  {t} <button onClick={() => setTags(tags.filter((x) => x !== t))} className="hover:text-[var(--danger)]"><X size={10} /></button>
                </span>
              ))}
            </div>
            <input value={tagInput} onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag() } }}
              placeholder={t('bulk_scan_modal.tag_placeholder')}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none" />
          </div>
        </div>
      )}
    </Modal>
  )
}


function MiniBarChart({ data }: { data: { date: string; count: number }[] }) {
  if (!data || data.length === 0) return null
  const max = Math.max(...data.map((d) => d.count), 1)
  const w = data.length * 20
  return (
    <svg viewBox={`0 0 ${w} 40`} className="w-full max-w-[200px] h-8 mt-2">
      {data.map((d, i) => (
        <rect key={i} x={i * 20 + 2} y={40 - (d.count / max) * 36} width={16} height={Math.max((d.count / max) * 36, 1)}
          className="fill-brand/60" rx={2} />
      ))}
    </svg>
  )
}


function HealthBreakdown({ feature }: { feature: FeatureRow }) {
  const { t } = useTranslation('features')
  const score = feature.health_score ?? 0
  const grade = feature.health_grade ?? '-'
  const bd = feature.health_breakdown || { documentation: 0, drift: 0, usage: 0 }
  const cls = GRADE_COLORS[grade] || ''

  const tips: string[] = []
  if (bd.documentation < 25) tips.push(t('health_breakdown.tips.doc_under_25'))
  if (bd.documentation < 40 && bd.documentation >= 25) tips.push(t('health_breakdown.tips.doc_under_40'))
  if (bd.drift === 0) tips.push(t('health_breakdown.tips.drift_critical'))
  if (bd.usage === 0) tips.push(t('health_breakdown.tips.usage_zero'))

  const driftNote = bd.drift === 40 ? t('health_breakdown.notes.healthy') : bd.drift === 0 ? t('health_breakdown.notes.critical') : bd.drift === 20 ? t('health_breakdown.notes.warning') : t('health_breakdown.notes.unknown')
  const usageNote = bd.usage === 0 ? t('health_breakdown.notes.no_recent_usage') : undefined

  const docPct = (bd.documentation / 40) * 100
  const driftPct = (bd.drift / 40) * 100
  const usagePct = (bd.usage / 20) * 100

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl font-bold">{score}</span>
        <span className="text-[var(--text-tertiary)] text-sm">/ 100</span>
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${cls}`}>{grade}</span>
      </div>
      <div className="grid grid-cols-[112px_1fr_auto_auto] gap-x-3 gap-y-3 items-center">
        <span className="text-sm text-[var(--text-secondary)]">{t('health_breakdown.documentation')}</span>
        <div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
          <div className="h-full bg-[var(--brand)] transition-all" style={{ width: `${docPct}%` }} />
        </div>
        <span className="font-mono tabular-nums text-xs text-[var(--text-secondary)] whitespace-nowrap text-right">{bd.documentation}/40</span>
        <span />

        <span className="text-sm text-[var(--text-secondary)]">{t('health_breakdown.drift')}</span>
        <div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
          <div className="h-full bg-[var(--brand)] transition-all" style={{ width: `${driftPct}%` }} />
        </div>
        <span className="font-mono tabular-nums text-xs text-[var(--text-secondary)] whitespace-nowrap text-right">{bd.drift}/40</span>
        <span className="text-xs text-[var(--text-tertiary)] whitespace-nowrap">{driftNote}</span>

        <span className="text-sm text-[var(--text-secondary)]">{t('health_breakdown.usage')}</span>
        <div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
          <div className="h-full bg-[var(--brand)] transition-all" style={{ width: `${usagePct}%` }} />
        </div>
        <span className="font-mono tabular-nums text-xs text-[var(--text-secondary)] whitespace-nowrap text-right">{bd.usage}/20</span>
        {usageNote ? (
          <span className="text-xs text-[var(--text-tertiary)] whitespace-nowrap">{usageNote}</span>
        ) : (
          <span />
        )}
      </div>
      {tips.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[var(--border-subtle)] space-y-1">
          {tips.map((tip, i) => (
            <p key={i} className="text-xs text-[var(--text-tertiary)]">{'\u{1F4A1}'} {tip}</p>
          ))}
        </div>
      )}
    </div>
  )
}


const TYPE_DOT_COLORS: Record<string, string> = {
  doc: 'bg-teal-500',
  hints: 'bg-purple-500',
  tags: 'bg-slate-400',
  definition: 'bg-amber-500',
  metadata: 'bg-gray-400',
}


function VersionTimeline({ versions, loading }: { versions: Record<string, unknown>[]; loading: boolean }) {
  const { t } = useTranslation('features')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (loading) return <Skeleton className="h-32" />

  if (versions.length === 0) {
    return (
      <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
        {t('versions.empty')}
      </p>
    )
  }

  const toggle = (v: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(v)) next.delete(v)
      else next.add(v)
      return next
    })
  }

  return (
    <div className="space-y-0">
      {versions.map((v, i) => {
        const version = v.version as number
        const dotColor = TYPE_DOT_COLORS[v.change_type as string] || 'bg-gray-400'
        const isExpanded = expanded.has(version)
        const prev = v.previous_value as Record<string, unknown> | null
        const next = v.new_value as Record<string, unknown> | null

        return (
          <div key={i} className="flex gap-3 relative">
            {/* Timeline line */}
            {i < versions.length - 1 && (
              <div className="absolute left-[7px] top-[18px] bottom-0 w-px bg-[var(--border-subtle)]" />
            )}
            {/* Dot */}
            <div className={`w-[15px] h-[15px] rounded-full ${dotColor} shrink-0 mt-0.5 border-2 border-[var(--bg-primary)]`} />
            {/* Content */}
            <div className="flex-1 pb-4">
              <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                <span className="font-semibold text-[var(--text-primary)]">v{version}</span>
                <span>{v.created_at ? timeAgo(v.created_at as string) : ''}</span>
                <span>{v.changed_by as string}</span>
              </div>
              <p className="text-sm text-[var(--text-secondary)] mt-0.5">{v.change_summary as string}</p>
              {prev && next && (
                <button onClick={() => toggle(version)} className="text-[11px] text-brand hover:underline mt-1">
                  {isExpanded ? 'Hide diff' : 'Show diff'}
                </button>
              )}
              {isExpanded && prev && next && (
                <div className="mt-2 bg-[var(--bg-secondary)] rounded-lg p-2.5 text-xs font-mono space-y-1">
                  {Object.keys(next).map(key => (
                    <div key={key}>
                      <span className="text-[var(--text-tertiary)]">{key}:</span>
                      <div className="text-[var(--danger)]">- {String(prev[key] ?? '(empty)')}</div>
                      <div className="text-[var(--success)]">+ {String(next[key] ?? '(empty)')}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}


function HighlightedText({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length) return <span>{text}</span>
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  const parts = text.split(regex)
  return (
    <span>
      {parts.map((part, i) =>
        terms.some(t => t.toLowerCase() === part.toLowerCase())
          ? <mark key={i} className="bg-[var(--brand-subtle-bg)] text-[var(--brand)] rounded px-0.5">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </span>
  )
}


// ---- Bulk-action modals (T1.3b) ----

function BulkAddTagModal({
  open,
  onClose,
  selectedCount,
  onConfirm,
}: {
  open: boolean
  onClose: () => void
  selectedCount: number
  onConfirm: (tag: string) => Promise<void>
}) {
  const { t } = useTranslation('features')
  const [tag, setTag] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      setTag('')
      setSubmitting(false)
    }
  }, [open])

  const submit = async () => {
    const value = tag.trim()
    if (!value) return
    setSubmitting(true)
    try {
      await onConfirm(value)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('bulk.add_tag_modal.title', { count: selectedCount })}
      maxWidth="max-w-md"
      actions={
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
            {t('actions.cancel', { ns: 'common' })}
          </button>
          <button
            onClick={submit}
            disabled={!tag.trim() || submitting}
            className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50"
          >
            {submitting ? t('actions.loading', { ns: 'common' }) : t('actions.apply', { ns: 'common' })}
          </button>
        </>
      }
    >
      <div className="space-y-2">
        <label className="block text-xs font-medium">{t('bulk.add_tag_modal.label')}</label>
        <input
          autoFocus
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
          }}
          placeholder={t('bulk.add_tag_modal.placeholder')}
          className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
        />
        <p className="text-[11px] text-[var(--text-tertiary)]">
          {t('bulk.add_tag_modal.hint', { count: selectedCount })}
        </p>
      </div>
    </Modal>
  )
}


function BulkAddToGroupModal({
  open,
  onClose,
  selectedCount,
  onConfirm,
}: {
  open: boolean
  onClose: () => void
  selectedCount: number
  onConfirm: (group: { id: string; name: string }) => Promise<void>
}) {
  const { t } = useTranslation('features')
  const [groups, setGroups] = useState<{ id: string; name: string; member_count?: number }[]>([])
  const [groupId, setGroupId] = useState('')
  const [loadingGroups, setLoadingGroups] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open) {
      setGroupId('')
      setSubmitting(false)
      setLoadingGroups(true)
      api.groups
        .list()
        .then((g) => setGroups(Array.isArray(g) ? (g as { id: string; name: string; member_count?: number }[]) : []))
        .catch(() => setGroups([]))
        .finally(() => setLoadingGroups(false))
    }
  }, [open])

  const submit = async () => {
    const group = groups.find((g) => g.id === groupId)
    if (!group) return
    setSubmitting(true)
    try {
      await onConfirm({ id: group.id, name: group.name })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('bulk.add_to_group_modal.title', { count: selectedCount })}
      maxWidth="max-w-md"
      actions={
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
            {t('actions.cancel', { ns: 'common' })}
          </button>
          <button
            onClick={submit}
            disabled={!groupId || submitting}
            className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50"
          >
            {submitting ? t('actions.loading', { ns: 'common' }) : t('actions.apply', { ns: 'common' })}
          </button>
        </>
      }
    >
      <div className="space-y-2">
        <label className="block text-xs font-medium">{t('bulk.add_to_group_modal.label')}</label>
        {loadingGroups ? (
          <p className="text-sm text-[var(--text-tertiary)]">{t('actions.loading', { ns: 'common' })}</p>
        ) : groups.length === 0 ? (
          <p className="text-sm text-[var(--text-tertiary)]">{t('bulk.add_to_group_modal.empty')}</p>
        ) : (
          <select
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
          >
            <option value="">{t('bulk.add_to_group_modal.placeholder')}</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
                {typeof g.member_count === 'number' ? ` (${g.member_count})` : ''}
              </option>
            ))}
          </select>
        )}
        <p className="text-[11px] text-[var(--text-tertiary)]">
          {t('bulk.add_to_group_modal.hint', { count: selectedCount })}
        </p>
      </div>
    </Modal>
  )
}


function BulkDeleteModal({
  open,
  onClose,
  names,
  onConfirm,
}: {
  open: boolean
  onClose: () => void
  names: string[]
  onConfirm: () => Promise<void>
}) {
  const { t } = useTranslation('features')
  const preview = names.slice(0, 50)
  const overflow = Math.max(0, names.length - preview.length)

  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      title={t('bulk.delete_modal.title', { count: names.length })}
      warning={t('bulk.delete_modal.warning', { count: names.length })}
      confirmLabel={t('bulk.delete_modal.confirm_button', { count: names.length })}
      pendingLabel={t('actions.loading', { ns: 'common' })}
      requireCheckbox={t('bulk.delete_modal.acknowledge')}
      onConfirm={onConfirm}
      message={
        <div className="space-y-3">
          <p className="text-xs text-[var(--text-tertiary)]">{t('bulk.delete_modal.cleanup_note')}</p>
          <div className="max-h-48 overflow-y-auto overscroll-contain rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-2">
            <ul className="space-y-0.5 text-[12px] font-mono">
              {preview.map((n) => (
                <li key={n} className="truncate">{n}</li>
              ))}
            </ul>
            {overflow > 0 && (
              <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">
                {t('bulk.delete_modal.and_more', { count: overflow })}
              </p>
            )}
          </div>
        </div>
      }
    />
  )
}
