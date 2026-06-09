import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, FileText, HardDrive, Plus, RefreshCw, Search as SearchIcon, Trash2 } from 'lucide-react'
import {
  api,
  invalidateCache,
  type DataSourceDTO,
  type ScanLog,
  type SourceCreate,
  type SourceImpact,
} from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FeatureSelector, toFeatureItems } from '../components/FeatureSelector'
import { MetricCard } from '../components/MetricCard'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { canDelete, canWrite, useAuth } from '../auth'

type TypeFilter = 'all' | 'local' | 's3'
type SortKey = 'name' | 'feature_count'

interface SourceRowStats {
  feature_count: number
  documented_count: number
}

/** Lightweight client-side path validator. Mirrors `validate_path_input` on
 *  the server (see `featcat/catalog/storage.py:46-78`) — disabling submit
 *  early avoids a round-trip for the common typo case (relative path,
 *  unsupported scheme). The server still re-validates authoritatively.
 */
function isValidPathInput(raw: string): boolean {
  const s = raw.trim()
  if (!s) return false
  if (s.startsWith('s3://')) return s.length > 's3://'.length
  return s.startsWith('/')
}

/** Derive a sensible default source name from a parquet path basename. */
function suggestNameFromPath(path: string): string {
  const trimmed = path.trim()
  if (!trimmed) return ''
  const cleaned = trimmed.replace(/\\+/g, '/')
  const last = cleaned.split('/').filter(Boolean).pop() || ''
  return last.replace(/\.(parquet|csv)$/i, '')
}

interface DetailState {
  source: DataSourceDTO
  features: Record<string, unknown>[]
  scanLogs: ScanLog[]
}

export function Sources() {
  const { t } = useTranslation('sources')
  const { auth } = useAuth()
  const navigate = useNavigate()
  const { name: routeName } = useParams<{ name: string }>()
  const [sources, setSources] = useState<DataSourceDTO[]>([])
  const [stats, setStats] = useState<Record<string, SourceRowStats>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [selectedName, setSelectedName] = useState<string | null>(routeName ?? null)
  const [createOpen, setCreateOpen] = useState(false)
  const [detail, setDetail] = useState<DetailState | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [selectedForScan, setSelectedForScan] = useState<Set<string>>(new Set())
  const [scanningRows, setScanningRows] = useState<Set<string>>(new Set())
  const canMutate = canWrite(auth?.user)
  const canRemove = canDelete(auth?.user)

  const load = () => {
    setLoading(true)
    setError(null)
    invalidateCache('/sources')
    invalidateCache('/stats/by-source')
    Promise.all([api.sources.list(), api.statsBySource()])
      .then(([srcs, byStats]) => {
        setSources(Array.isArray(srcs) ? srcs : [])
        const m: Record<string, SourceRowStats> = {}
        for (const s of byStats) {
          m[s.source_name] = {
            feature_count: s.feature_count,
            documented_count: s.documented_count,
          }
        }
        setStats(m)
      })
      .catch((e: unknown) => {
        setSources([])
        setError(e instanceof Error ? e.message : t('errors.load_failed'))
      })
      .finally(() => setLoading(false))
  }

  const loadDetail = (name: string) => {
    setDetailLoading(true)
    invalidateCache(`/sources/${encodeURIComponent(name)}`)
    Promise.all([
      api.sources.get(name),
      api.features.list({ source: name }),
      api.sources.scanLogs(name, 10),
    ])
      .then(([src, features, scanLogs]) => {
        setDetail({
          source: src,
          features: Array.isArray(features) ? features : [],
          scanLogs: Array.isArray(scanLogs) ? scanLogs : [],
        })
      })
      .catch((e: unknown) => {
        setDetail(null)
        setError(e instanceof Error ? e.message : t('errors.load_failed'))
      })
      .finally(() => setDetailLoading(false))
  }

  // Initial list load.
  useEffect(() => {
    load()
  }, [])

  // Refetch detail whenever the selected name changes (covers deep-link
  // landings and click-through alike).
  useEffect(() => {
    if (selectedName) {
      loadDetail(selectedName)
    } else {
      setDetail(null)
    }
  }, [selectedName])

  // Sync URL with selection so the deep-link survives reloads / sharing.
  // Skip when the URL already matches (avoids redundant pushes during the
  // initial route-driven select).
  useEffect(() => {
    const target = selectedName ? `/sources/${encodeURIComponent(selectedName)}` : '/sources'
    if (window.location.pathname !== target) {
      navigate(target, { replace: false })
    }
  }, [selectedName, navigate])

  const selectSource = (s: DataSourceDTO) => {
    setSelectedName(s.name)
  }

  const clearSelection = () => {
    setSelectedName(null)
  }

  const scanSelected = async () => {
    if (!selectedName) return
    setScanning(true)
    setError(null)
    try {
      await api.sources.scan(selectedName)
      invalidateCache('/sources')
      invalidateCache('/features')
      invalidateCache('/stats/by-source')
      // Refresh both list (for feature_count badge) and detail.
      load()
      loadDetail(selectedName)
    } catch (e) {
      setError(t('errors.scan_failed', { message: e instanceof Error ? e.message : String(e) }))
    } finally {
      setScanning(false)
    }
  }

  const onDeleted = () => {
    setDeleteOpen(false)
    clearSelection()
    load()
  }

  const toggleScanSelection = (name: string) => {
    setSelectedForScan((prev) => {
      const next = new Set(prev)
      if (next.has(name)) {
        next.delete(name)
      } else {
        next.add(name)
      }
      return next
    })
  }

  const deleteBulkConfirmed = async () => {
    const names = Array.from(selectedForScan)
    if (names.length === 0) return
    try {
      await api.sources.deleteBulk({ names, confirm: true })
    } catch (e) {
      setError(t('errors.delete_failed', { message: e instanceof Error ? e.message : String(e) }))
      return
    }
    invalidateCache('/sources')
    invalidateCache('/features')
    invalidateCache('/stats/by-source')
    setSelectedForScan(new Set())
    setBulkDeleteOpen(false)
    if (selectedName && names.includes(selectedName)) {
      setSelectedName(null)
      setDetail(null)
    }
    load()
  }

  const scanBulk = async () => {
    if (selectedForScan.size === 0) return
    const names = Array.from(selectedForScan)
    setError(null)
    // Mark every targeted row as scanning up-front so the spinner appears
    // immediately, then peel them off as each completes.
    setScanningRows(new Set(names))
    let firstError: string | null = null
    for (const name of names) {
      try {
        await api.sources.scan(name)
      } catch (e) {
        if (!firstError) {
          firstError = e instanceof Error ? e.message : String(e)
        }
      } finally {
        setScanningRows((prev) => {
          const next = new Set(prev)
          next.delete(name)
          return next
        })
      }
    }
    if (firstError) {
      setError(t('errors.scan_failed', { message: firstError }))
    }
    invalidateCache('/sources')
    invalidateCache('/features')
    invalidateCache('/stats/by-source')
    setSelectedForScan(new Set())
    load()
    if (selectedName) loadDetail(selectedName)
  }

  const filtered = useMemo(() => {
    let result = sources
    if (search.trim()) {
      const q = search.trim().toLowerCase()
      result = result.filter(
        (s) => s.name.toLowerCase().includes(q) || s.path.toLowerCase().includes(q),
      )
    }
    if (typeFilter !== 'all') {
      result = result.filter((s) => s.storage_type === typeFilter)
    }
    const sorted = [...result]
    if (sortKey === 'feature_count') {
      sorted.sort(
        (a, b) => (stats[b.name]?.feature_count ?? 0) - (stats[a.name]?.feature_count ?? 0),
      )
    } else {
      sorted.sort((a, b) => a.name.localeCompare(b.name))
    }
    return sorted
  }, [sources, stats, search, typeFilter, sortKey])

  const filtersActive = search.trim() !== '' || typeFilter !== 'all'

  return (
    <div>
      <PageHeader
        title={t('page.title')}
        actions={
          <button
            onClick={() => setCreateOpen(true)}
            disabled={!canMutate}
            className="flex items-center gap-1.5 px-4 py-2 bg-brand text-white rounded-lg text-[13px] font-medium hover:bg-brand-emphasis transition-colors"
          >
            <Plus size={16} />
            {t('actions.new_source')}
          </button>
        }
      />

      {error && (
        <Alert
          severity="danger"
          message={error}
          dismissible
          onDismiss={() => setError(null)}
          className="mb-4"
        />
      )}

      <div className="flex flex-col md:flex-row gap-4" style={{ minHeight: '500px' }}>
        {/* Left: source list */}
        <div className="w-full md:w-1/3 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-3 flex flex-col">
          {/* Bulk-action banner — appears only when at least one row is checked. */}
          {selectedForScan.size > 0 && (
            <div className="mb-3 flex items-center justify-between gap-2 rounded-lg border border-brand bg-brand-muted px-3 py-2 text-[12px]">
              <span className="text-[var(--text-primary)]">
                {t('actions.scan_selected', { count: selectedForScan.size })}
              </span>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setSelectedForScan(new Set())}
                  disabled={scanningRows.size > 0}
                  className="px-2 py-1 text-[11px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:opacity-50"
                >
                  {t('actions.cancel', { ns: 'common' })}
                </button>
                <button
                  onClick={() => setBulkDeleteOpen(true)}
                  disabled={scanningRows.size > 0 || !canRemove}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-[var(--danger)] border border-[var(--danger)] rounded hover:bg-[var(--danger-subtle-bg)] disabled:opacity-50"
                >
                  <Trash2 size={12} />
                  {t('actions.delete_selected')}
                </button>
                <button
                  onClick={scanBulk}
                  disabled={scanningRows.size > 0 || !canMutate}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium bg-brand text-white rounded disabled:opacity-50"
                >
                  <RefreshCw size={12} className={scanningRows.size > 0 ? 'animate-spin' : ''} />
                  {scanningRows.size > 0 ? t('actions.scanning') : t('actions.scan_now')}
                </button>
              </div>
            </div>
          )}

          {/* Filters */}
          <div className="space-y-2 mb-3">
            <div className="relative">
              <SearchIcon
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]"
              />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('filters.search_placeholder')}
                className="w-full bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-lg pl-9 pr-3 py-2 text-[13px] focus:border-brand outline-none"
              />
            </div>
            <div className="flex gap-2 text-xs">
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
                className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-lg px-2 py-1.5 text-[12px] focus:border-brand outline-none"
              >
                <option value="all">{t('filters.all_types')}</option>
                <option value="local">{t('filters.type_local')}</option>
                <option value="s3">{t('filters.type_s3')}</option>
              </select>
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-lg px-2 py-1.5 text-[12px] focus:border-brand outline-none"
              >
                <option value="name">{t('sort.name')}</option>
                <option value="feature_count">{t('sort.feature_count')}</option>
              </select>
            </div>
          </div>

          {/* List */}
          <div className="space-y-2 flex-1 overflow-y-auto">
            {loading ? (
              <Skeleton className="h-32" />
            ) : sources.length === 0 ? (
              <div className="text-center py-8 px-3">
                <HardDrive
                  size={32}
                  className="mx-auto mb-2 text-[var(--text-tertiary)]"
                  strokeWidth={1.5}
                />
                <p className="text-sm text-[var(--text-secondary)] mb-3">{t('list.empty_title')}</p>
                <button
                  onClick={() => setCreateOpen(true)}
                  disabled={!canMutate}
                  className="text-xs text-brand hover:underline"
                >
                  {t('list.empty_cta')}
                </button>
              </div>
            ) : filtered.length === 0 ? (
              <p className="text-[var(--text-tertiary)] text-sm py-4 text-center">
                {filtersActive ? t('list.no_match') : t('list.empty_title')}
              </p>
            ) : (
              filtered.map((s) => (
                <SourceListRow
                  key={s.id}
                  source={s}
                  featureCount={stats[s.name]?.feature_count ?? 0}
                  selected={selectedName === s.name}
                  checked={selectedForScan.has(s.name)}
                  scanning={scanningRows.has(s.name)}
                  onToggle={() => toggleScanSelection(s.name)}
                  onClick={() => selectSource(s)}
                />
              ))
            )}
          </div>
        </div>

        {/* Right: detail panel */}
        <div className="w-full md:flex-1 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl">
          {!selectedName ? (
            <div className="h-full flex items-center justify-center p-10 text-sm text-[var(--text-tertiary)]">
              {t('detail.select_hint')}
            </div>
          ) : detailLoading && !detail ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-8 w-1/3" />
              <Skeleton className="h-20" />
              <Skeleton className="h-32" />
            </div>
          ) : detail ? (
              <SourceDetail
                key={detail.source.name}
                detail={detail}
                scanning={scanning}
                canScan={canMutate}
                canDelete={canRemove}
                onScan={scanSelected}
                onDelete={() => setDeleteOpen(true)}
              />
          ) : (
            <div className="h-full flex items-center justify-center p-10 text-sm text-[var(--text-tertiary)]">
              {t('detail.select_hint')}
            </div>
          )}
        </div>
      </div>

      <CreateSourceModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false)
          load()
        }}
      />

      {selectedName && (
        <DeleteSourceModal
          open={deleteOpen}
          name={selectedName}
          onClose={() => setDeleteOpen(false)}
          onDeleted={onDeleted}
        />
      )}

      <ConfirmDialog
        open={bulkDeleteOpen}
        onClose={() => setBulkDeleteOpen(false)}
        title={t('bulk_delete_modal.title', { count: selectedForScan.size })}
        message={t('bulk_delete_modal.body')}
        warning={t('bulk_delete_modal.warning')}
        confirmLabel={t('bulk_delete_modal.confirm')}
        pendingLabel={t('bulk_delete_modal.deleting')}
        onConfirm={deleteBulkConfirmed}
      />
    </div>
  )
}

function SourceListRow({
  source,
  featureCount,
  selected,
  checked,
  scanning,
  onToggle,
  onClick,
}: {
  source: DataSourceDTO
  featureCount: number
  selected: boolean
  checked: boolean
  scanning: boolean
  onToggle: () => void
  onClick: () => void
}) {
  const { t } = useTranslation('sources')
  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-lg border cursor-pointer transition-all flex gap-2 ${
        selected
          ? 'bg-brand-muted border-brand'
          : 'bg-[var(--bg-secondary)] border-[var(--border-subtle)] hover:border-[var(--border-default)]'
      }`}
    >
      {/* Bulk-scan checkbox; click absorbed so the row select doesn't fire. */}
      <label
        onClick={(e) => e.stopPropagation()}
        className="shrink-0 self-start mt-0.5 cursor-pointer"
        aria-label={`Select ${source.name} for bulk scan`}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={scanning}
          onChange={onToggle}
          className="cursor-pointer"
        />
      </label>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="font-medium text-[13px] truncate">{source.name}</span>
          <div className="flex items-center gap-1.5 shrink-0">
            {scanning && (
              <RefreshCw
                size={12}
                className="animate-spin text-[var(--text-tertiary)]"
                aria-label="scanning"
              />
            )}
            <Badge variant={source.storage_type === 's3' ? 'info' : 'default'}>
              {source.storage_type}
            </Badge>
          </div>
        </div>
        <p
          className="text-[11px] text-[var(--text-tertiary)] truncate font-mono"
          title={source.path}
        >
          {source.path}
        </p>
        <p className="text-[11px] text-[var(--text-tertiary)] mt-1">
          {featureCount > 0 ? t('list.feature_count', { count: featureCount }) : t('row.no_features')}
        </p>
      </div>
    </div>
  )
}

function CreateSourceModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: () => void
}) {
  const { t } = useTranslation('sources')
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [description, setDescription] = useState('')
  const [scanAfter, setScanAfter] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Reset form whenever the modal reopens.
  useEffect(() => {
    if (open) {
      setName('')
      setPath('')
      setDescription('')
      setScanAfter(true)
      setSubmitting(false)
      setScanning(false)
      setSubmitError(null)
    }
  }, [open])

  // Auto-suggest name once the path is filled and the user hasn't typed a
  // name yet. Tracked via local edit-flag so we don't overwrite a name the
  // user explicitly typed.
  const [nameTouched, setNameTouched] = useState(false)
  useEffect(() => {
    if (!nameTouched && path) {
      const suggested = suggestNameFromPath(path)
      if (suggested) setName(suggested)
    }
  }, [path, nameTouched])

  const pathValid = isValidPathInput(path)
  const nameValid = name.trim().length > 0
  const canSubmit = !submitting && !scanning && pathValid && nameValid

  const submit = async () => {
    setSubmitError(null)
    setSubmitting(true)
    try {
      const body: SourceCreate = {
        name: name.trim(),
        path: path.trim(),
        description: description.trim(),
      }
      await api.sources.add(body)
      invalidateCache('/sources')
      invalidateCache('/stats/by-source')
      if (scanAfter) {
        setScanning(true)
        try {
          await api.sources.scan(body.name)
        } catch (e) {
          // Source created successfully; scan failure is shown inline but we
          // still close the modal so the user sees the new source in the list.
          setSubmitError(
            t('errors.scan_failed', { message: e instanceof Error ? e.message : String(e) }),
          )
          // Brief pause so the user sees the error, then close.
          setTimeout(onCreated, 1500)
          return
        }
        invalidateCache('/features')
      }
      onCreated()
    } catch (e) {
      setSubmitError(t('errors.add_failed', { message: e instanceof Error ? e.message : String(e) }))
    } finally {
      setSubmitting(false)
      setScanning(false)
    }
  }

  const submitLabel = scanning
    ? t('add_modal.scanning_after_add')
    : submitting
      ? t('add_modal.adding')
      : t('add_modal.submit')

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('add_modal.title')}
      actions={
        <>
          <button
            onClick={onClose}
            disabled={submitting || scanning}
            className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg disabled:opacity-50"
          >
            {t('actions.cancel', { ns: 'common' })}
          </button>
          <button
            onClick={submit}
            disabled={!canSubmit}
            className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50"
          >
            {submitLabel}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium mb-1">
            {t('add_modal.fields.path')} <span className="text-[var(--danger)]">*</span>
          </label>
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder={t('add_modal.fields.path_placeholder')}
            className={`w-full bg-[var(--bg-primary)] border rounded-lg px-3 py-2 text-[13px] font-mono outline-none ${
              path && !pathValid
                ? 'border-[var(--danger)] focus:border-[var(--danger)]'
                : 'border-[var(--border-default)] focus:border-brand'
            }`}
          />
          {path && !pathValid && (
            <p className="text-[11px] text-[var(--danger)] mt-1">{t('errors.path_invalid')}</p>
          )}
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">
            {t('add_modal.fields.name')} <span className="text-[var(--danger)]">*</span>
          </label>
          <input
            value={name}
            onChange={(e) => {
              setNameTouched(true)
              setName(e.target.value)
            }}
            placeholder={t('add_modal.fields.name_placeholder')}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium mb-1">{t('add_modal.fields.description')}</label>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={t('add_modal.fields.description_placeholder')}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
          />
        </div>

        <label className="flex items-center gap-2 text-[13px] cursor-pointer select-none">
          <input
            type="checkbox"
            checked={scanAfter}
            onChange={(e) => setScanAfter(e.target.checked)}
            className="rounded"
          />
          {t('add_modal.fields.scan_after')}
        </label>

        {submitError && (
          <p className="text-[12px] text-[var(--danger)] bg-[var(--danger-subtle-bg)] rounded-lg px-3 py-2">
            {submitError}
          </p>
        )}
      </div>
    </Modal>
  )
}

function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return '-'
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return raw
  return d.toLocaleString()
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '-'
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const s = (seconds % 60).toFixed(0)
  return `${m}m ${s}s`
}

function SourceDetail({
  detail,
  scanning,
  canScan,
  canDelete,
  onScan,
  onDelete,
}: {
  detail: DetailState
  scanning: boolean
  canScan: boolean
  canDelete: boolean
  onScan: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation('sources')
  const { source, features, scanLogs } = detail

  const featureCount = features.length
  const documentedCount = features.filter((f) => !!f.has_doc).length
  const docCoverage = featureCount > 0 ? Math.round((documentedCount / featureCount) * 100) : 0
  const featureItems = useMemo(() => toFeatureItems(features), [features])
  const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(new Set())

  return (
    <div className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h2 className="text-lg font-semibold truncate">{source.name}</h2>
            <Badge variant={source.storage_type === 's3' ? 'info' : 'default'}>
              {source.storage_type}
            </Badge>
          </div>
          {source.description && (
            <p className="text-[12px] text-[var(--text-secondary)]">{source.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={onScan}
            disabled={scanning || !canScan}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50"
          >
            <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
            {scanning ? t('actions.scanning') : t('actions.scan_now')}
          </button>
          <button
            onClick={onDelete}
            disabled={scanning || !canDelete}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] border border-[var(--border-default)] rounded-lg text-[var(--danger)] hover:bg-[var(--danger-subtle-bg)] disabled:opacity-50"
          >
            <Trash2 size={14} />
            {t('actions.delete')}
          </button>
        </div>
      </div>

      {/* Metadata */}
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg p-4 text-[13px]">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-6">
          <MetaRow label={t('detail.metadata.path')}>
            <span className="font-mono text-[12px] break-all">{source.path}</span>
          </MetaRow>
          <MetaRow label={t('detail.metadata.format')}>{source.format}</MetaRow>
          <MetaRow label={t('detail.metadata.created')}>{formatTimestamp(source.created_at)}</MetaRow>
          <MetaRow label={t('detail.metadata.updated')}>{formatTimestamp(source.updated_at)}</MetaRow>
        </dl>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <MetricCard
          label={t('detail.stats.features')}
          value={featureCount}
          icon={FileText}
        />
        <MetricCard
          label={t('detail.stats.docs_coverage')}
          value={`${docCoverage}%`}
          progress={docCoverage}
        />
        <MetricCard
          label={t('detail.stats.scans')}
          value={scanLogs.length}
          icon={RefreshCw}
        />
      </div>

      {/* Extracted features */}
      <section>
        <h3 className="text-sm font-semibold mb-2">{t('detail.features_section')}</h3>
        {featureItems.length === 0 ? (
          <p className="text-sm text-[var(--text-tertiary)] py-4 text-center bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)]">
            {t('detail.features_empty')}
          </p>
        ) : (
          <FeatureSelector
            features={featureItems}
            selected={selectedFeatures}
            onChange={setSelectedFeatures}
            showAISuggest={false}
            maxHeight="280px"
          />
        )}
      </section>

      {/* Scan history */}
      <section>
        <h3 className="text-sm font-semibold mb-2">{t('detail.scan_history_section')}</h3>
        {scanLogs.length === 0 ? (
          <p className="text-sm text-[var(--text-tertiary)] py-4 text-center bg-[var(--bg-secondary)] rounded-lg border border-[var(--border-subtle)]">
            {t('detail.scan_history_empty')}
          </p>
        ) : (
          <ScanHistoryTable logs={scanLogs} />
        )}
      </section>
    </div>
  )
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)] mb-0.5">
        {label}
      </dt>
      <dd className="text-[var(--text-primary)]">{children}</dd>
    </div>
  )
}

function ScanHistoryTable({ logs }: { logs: ScanLog[] }) {
  const { t } = useTranslation('sources')
  return (
    <div className="overflow-x-auto bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded-lg">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-[11px] text-[var(--text-tertiary)] border-b border-[var(--border-subtle)]">
            <th className="text-left py-2 px-3 font-medium">{t('scan_log.started')}</th>
            <th className="text-left py-2 px-3 font-medium">{t('scan_log.status')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('scan_log.duration')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('scan_log.files')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('scan_log.added')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('scan_log.updated')}</th>
            <th className="text-left py-2 px-3 font-medium">{t('scan_log.triggered_by')}</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr
              key={log.id}
              className="border-b border-[var(--border-subtle)] last:border-b-0 hover:bg-[var(--bg-primary)]"
            >
              <td className="py-2 px-3 font-mono text-[11px]">{formatTimestamp(log.started_at)}</td>
              <td className="py-2 px-3">
                <Badge variant={log.status === 'success' ? 'success' : 'danger'}>
                  {log.status === 'success' ? t('scan_log.status_success') : t('scan_log.status_failed')}
                </Badge>
                {log.error_message && (
                  <span
                    title={log.error_message}
                    className="ml-1.5 inline-block text-[var(--danger)] align-middle"
                  >
                    <AlertTriangle size={12} />
                  </span>
                )}
              </td>
              <td className="py-2 px-3 text-right font-mono text-[11px]">
                {formatDuration(log.duration_seconds)}
              </td>
              <td className="py-2 px-3 text-right font-mono">{log.files_scanned}</td>
              <td className="py-2 px-3 text-right font-mono text-[var(--success)]">
                +{log.features_added}
              </td>
              <td className="py-2 px-3 text-right font-mono text-[var(--text-secondary)]">
                ~{log.features_updated}
              </td>
              <td className="py-2 px-3 text-[var(--text-tertiary)]">{log.triggered_by}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DeleteSourceModal({
  open,
  name,
  onClose,
  onDeleted,
}: {
  open: boolean
  name: string
  onClose: () => void
  onDeleted: () => void
}) {
  const { t } = useTranslation('sources')
  const [impact, setImpact] = useState<SourceImpact | null>(null)
  const [loading, setLoading] = useState(false)

  // Refresh impact every time the modal opens against a fresh name; the
  // catalog might have changed since the last open (group memberships, etc.).
  useEffect(() => {
    if (!open) return
    setImpact(null)
    setLoading(true)
    invalidateCache(`/sources/${encodeURIComponent(name)}/impact`)
    api.sources
      .impact(name)
      .then(setImpact)
      .finally(() => setLoading(false))
  }, [open, name])

  const submit = async () => {
    await api.sources.delete(name)
    invalidateCache('/sources')
    invalidateCache('/features')
    invalidateCache('/stats/by-source')
    onDeleted()
  }

  // Type-to-confirm kicks in for high-impact deletes (the audit's "real
  // consumer" call-out). Threshold matches GitHub repo-delete: > 10 features
  // counts as "significant enough to warrant typing".
  const requireMatch = impact && impact.features_count > 10
    ? { value: name, label: t('delete_modal.body_features_other', { count: impact.features_count }) }
    : undefined

  return (
    <ConfirmDialog
      open={open}
      onClose={onClose}
      title={t('delete_modal.title', { name })}
      confirmLabel={t('delete_modal.confirm')}
      pendingLabel={t('delete_modal.deleting')}
      warning={t('delete_modal.warning')}
      requireTextMatch={requireMatch}
      onConfirm={submit}
      message={
        loading ? (
          <p className="text-sm text-[var(--text-tertiary)]">{t('delete_modal.loading')}</p>
        ) : impact ? (
          <div className="space-y-3">
            <p className="text-sm">
              {impact.features_count === 0
                ? t('delete_modal.body_features_zero')
                : t('delete_modal.body_features_other', { count: impact.features_count })}
            </p>
            {impact.groups.length === 0 ? (
              <p className="text-[12px] text-[var(--text-tertiary)]">
                {t('delete_modal.body_groups_none')}
              </p>
            ) : (
              <div>
                <p className="text-[12px] text-[var(--text-secondary)] mb-1">
                  {t('delete_modal.body_groups', { count: impact.groups.length })}
                </p>
                <ul className="text-[12px] space-y-1 list-disc list-inside text-[var(--text-secondary)] max-h-32 overflow-y-auto">
                  {impact.groups.map((g) => (
                    <li key={g.name}>
                      <span className="font-medium">{g.name}</span>{' '}
                      <span className="text-[var(--text-tertiary)]">({g.feature_count})</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : null
      }
    />
  )
}
