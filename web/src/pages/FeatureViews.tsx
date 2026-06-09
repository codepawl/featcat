import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Pencil, Plus, ExternalLink, RefreshCw } from 'lucide-react'
import { api, invalidateCache, type FeatureViewDTO } from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink, FilterSelect } from '../components/filters'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Select } from '../components/Select'
import { Skeleton } from '../components/Skeleton'
import { formatLines, parseLines } from '../components/registryFormUtils'
import { canWrite, useAuthMaybe } from '../auth'

const LIFECYCLE_STATUSES = ['draft', 'validated', 'production', 'deprecated'] as const
type LifecycleStatus = (typeof LIFECYCLE_STATUSES)[number] | ''

const STATUS_VARIANTS: Record<string, string> = {
  draft: 'default',
  validated: 'success',
  production: 'info',
  deprecated: 'danger',
}

function statusLabel(status: string, t: any): string {
  return t(`status.${status}`, { defaultValue: status })
}

export function FeatureViews() {
  const { t } = useTranslation('featureRegistry')
  const auth = useAuthMaybe()
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()
  const canMutate = canWrite(auth?.auth?.user)

  const [items, setItems] = useState<FeatureViewDTO[]>([])
  const [detail, setDetail] = useState<FeatureViewDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [entity, setEntity] = useState('')
  const [owner, setOwner] = useState('')
  const [status, setStatus] = useState<LifecycleStatus>('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create')
  const [editorError, setEditorError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/feature-views')
    api.featureViews
      .list({
        entity: entity || undefined,
        owner: owner || undefined,
      })
      .then((rows) => {
        const filtered = Array.isArray(rows)
          ? rows.filter((row) => {
              const matchesStatus = status ? row.lifecycle_status === status : true
              const q = searchQuery.trim().toLowerCase()
              const matchesSearch = !q || [
                row.name,
                row.entity,
                row.source_name,
                row.owner,
                row.description,
              ].some((value) => String(value ?? '').toLowerCase().includes(q))
              return matchesStatus && matchesSearch
            })
          : []
        setItems(filtered)
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [entity, owner, searchQuery, status])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!name) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    api.featureViews
      .get(name)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [name])

  const hasFilters = useMemo(() => !!(searchQuery || entity || owner || status), [searchQuery, entity, owner, status])

  const clearFilters = () => {
    setSearchQuery('')
    setEntity('')
    setOwner('')
    setStatus('')
  }

  const selected = detail ?? items.find((row) => row.name === name) ?? null
  const openCreate = () => {
    setEditorMode('create')
    setEditorError(null)
    setEditorOpen(true)
  }
  const openEdit = () => {
    if (!selected) return
    setEditorMode('edit')
    setEditorError(null)
    setEditorOpen(true)
  }
  const closeEditor = () => {
    setEditorOpen(false)
    setEditorError(null)
  }
  const onSaved = async (viewName: string) => {
    closeEditor()
    await load()
    navigate(`/feature-views/${encodeURIComponent(viewName)}`)
  }

  return (
    <div>
      <PageHeader
        title={t('featureViews.page.title')}
        subtitle={t('featureViews.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('featureViews.page.count', { count: items.length })}</span>
            {canMutate && (
              <button onClick={openCreate} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors">
                <Plus size={14} />
                {t('actions.new', { defaultValue: 'New' })}
              </button>
            )}
            <button
              onClick={load}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {t('featureViews.actions.refresh')}
            </button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <SearchInput placeholder={t('featureViews.filters.search_placeholder')} onSearch={setSearchQuery} className="w-full sm:max-w-xs" />
        <input
          value={entity}
          onChange={(e) => setEntity(e.target.value)}
          placeholder={t('featureViews.filters.entity_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <input
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          placeholder={t('featureViews.filters.owner_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <FilterSelect
          ariaLabel={t('featureViews.columns.status')}
          value={status}
          onChange={setStatus}
          options={[
            { value: '', label: t('filters.all_statuses', { defaultValue: 'All statuses' }) },
            ...LIFECYCLE_STATUSES.map((value) => ({ value, label: t(`featureViews.status.${value}`) })),
          ]}
        />
        <FilterClearLink show={hasFilters} onClick={clearFilters} />
      </div>

      <div className="flex flex-col lg:flex-row gap-4" style={{ minHeight: '520px' }}>
        <div className="lg:w-[58%] bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-3">
          {loading && items.length === 0 ? (
            <Skeleton className="h-48" />
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-sm text-[var(--text-tertiary)]">
              <p>{t('featureViews.empty.title')}</p>
              <p className="mt-1">{t('featureViews.empty.hint')}</p>
              {canMutate && (
                <button onClick={openCreate} className="mt-4 inline-flex items-center gap-1.5 text-xs text-brand hover:underline">
                  <Plus size={12} />
                  {t('actions.create', { defaultValue: 'Create feature view' })}
                </button>
              )}
            </div>
          ) : (
            <DataTable
              data={items}
              pageSize={18}
              onRowClick={(row) => navigate(`/feature-views/${encodeURIComponent(row.name)}`)}
              columns={[
                {
                  key: 'name',
                  label: t('featureViews.columns.name'),
                  render: (row) => (
                    <div>
                      <div className="font-medium text-brand">{row.name}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{row.source_name}</div>
                    </div>
                  ),
                },
                { key: 'entity', label: t('featureViews.columns.entity') },
                { key: 'source_name', label: t('featureViews.columns.source') },
                { key: 'owner', label: t('featureViews.columns.owner') },
                {
                  key: 'feature_count',
                  label: t('featureViews.columns.features'),
                  sortable: false,
                  render: (row) => <span className="font-mono text-xs">{row.feature_names?.length ?? 0}</span>,
                },
                {
                  key: 'lifecycle_status',
                  label: t('featureViews.columns.status'),
                  sortable: false,
                  render: (row) => <Badge variant={STATUS_VARIANTS[row.lifecycle_status] || 'default'}>{statusLabel(row.lifecycle_status, t)}</Badge>,
                },
              ]}
            />
          )}
        </div>

        <div className="flex-1 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
          {!name ? (
            <div className="h-full min-h-[420px] flex items-center justify-center text-sm text-[var(--text-tertiary)]">
              {t('featureViews.detail.select_hint')}
            </div>
          ) : detailLoading && !selected ? (
            <Skeleton className="h-48" />
          ) : selected ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold break-words">{selected.name}</h2>
                  <div className="text-xs text-[var(--text-tertiary)] break-words">{selected.source_name}</div>
                </div>
                <Badge variant={STATUS_VARIANTS[selected.lifecycle_status] || 'default'}>{statusLabel(selected.lifecycle_status, t)}</Badge>
              </div>

              <div className="flex flex-wrap gap-2">
                <Badge variant="info">{selected.entity}</Badge>
                {selected.owner && <Badge variant="default">{selected.owner}</Badge>}
                <Link
                  to={`/features?search=${encodeURIComponent(selected.name)}`}
                  className="inline-flex items-center gap-1 text-xs text-brand hover:underline"
                >
                  {t('featureViews.detail.feature_link')}
                  <ExternalLink size={12} />
                </Link>
                {canMutate && (
                  <button onClick={openEdit} className="inline-flex items-center gap-1 text-xs text-brand hover:underline">
                    <Pencil size={12} />
                    {t('actions.edit', { defaultValue: 'Edit' })}
                  </button>
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('featureViews.detail.source_entity')}</div>
                  <div className="mt-1">{selected.source_entity || '-'}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('featureViews.detail.relationship')}</div>
                  <div className="mt-1 break-words">{selected.relationship || '-'}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('featureViews.detail.aggregation')}</div>
                  <div className="mt-1 break-words">{selected.aggregation || '-'}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('featureViews.detail.description')}</div>
                  <div className="mt-1 break-words">{selected.description || '-'}</div>
                </div>
              </div>

              <div>
                <div className="text-sm font-medium mb-2">{t('featureViews.detail.features')}</div>
                {selected.feature_names?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {selected.feature_names.map((featureName) => (
                      <Link key={featureName} to={`/features/${encodeURIComponent(featureName)}`} className="text-xs px-2.5 py-1 rounded-full border border-[var(--border-default)] hover:bg-[var(--bg-secondary)]">
                        {featureName}
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-[var(--text-tertiary)]">{t('featureViews.detail.no_features')}</div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <FeatureViewEditorModal
        open={editorOpen}
        mode={editorMode}
        view={editorMode === 'edit' ? selected : null}
        onClose={closeEditor}
        onSaved={onSaved}
        canMutate={canMutate}
        error={editorError}
        setError={setEditorError}
      />
    </div>
  )
}

function FeatureViewEditorModal({
  open,
  mode,
  view,
  onClose,
  onSaved,
  canMutate,
  error,
  setError,
}: {
  open: boolean
  mode: 'create' | 'edit'
  view: FeatureViewDTO | null
  onClose: () => void
  onSaved: (name: string) => Promise<void>
  canMutate: boolean
  error: string | null
  setError: (value: string | null) => void
}) {
  const { t } = useTranslation('featureRegistry')
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState({
    name: '',
    entity: '',
    source_name: '',
    source_entity: '',
    relationship: '',
    aggregation: '',
    feature_names: '',
    description: '',
    owner: '',
    lifecycle_status: 'draft',
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    if (mode === 'edit' && view) {
      setForm({
        name: view.name,
        entity: view.entity,
        source_name: view.source_name,
        source_entity: view.source_entity ?? '',
        relationship: view.relationship ?? '',
        aggregation: view.aggregation ?? '',
        feature_names: formatLines(view.feature_names),
        description: view.description ?? '',
        owner: view.owner ?? '',
        lifecycle_status: view.lifecycle_status ?? 'draft',
      })
    } else {
      setForm({
        name: '',
        entity: '',
        source_name: '',
        source_entity: '',
        relationship: '',
        aggregation: '',
        feature_names: '',
        description: '',
        owner: '',
        lifecycle_status: 'draft',
      })
    }
  }, [mode, open, setError, view])

  const submit = async () => {
    if (!canMutate || saving) return
    const name = form.name.trim()
    if (!name || !form.entity.trim() || !form.source_name.trim()) {
      setError(t('errors.required_fields', { defaultValue: 'Name, entity, and source name are required.' }))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.featureViews.upsert({
        name,
        entity: form.entity.trim(),
        source_name: form.source_name.trim(),
        source_entity: form.source_entity.trim() || null,
        relationship: form.relationship.trim() || null,
        aggregation: form.aggregation.trim() || null,
        feature_names: parseLines(form.feature_names),
        description: form.description.trim(),
        owner: form.owner.trim(),
        lifecycle_status: form.lifecycle_status,
      })
      await onSaved(name)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('errors.save_failed', { defaultValue: 'Save failed.' }))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === 'edit' ? t('actions.edit', { defaultValue: 'Edit feature view' }) : t('actions.create', { defaultValue: 'Create feature view' })}
      maxWidth="max-w-3xl"
      actions={
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">
            {t('actions.cancel', { defaultValue: 'Cancel' })}
          </button>
          <button onClick={submit} disabled={!canMutate || saving} className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50">
            {saving ? t('actions.saving', { defaultValue: 'Saving...' }) : t('actions.save', { defaultValue: 'Save' })}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        {error && <Alert severity="danger" message={error} />}
        <div>
          <label className="block text-xs font-medium mb-1">
            {t('featureViews.columns.name')} <span className="text-[var(--danger)]">*</span>
          </label>
          <input
            value={form.name}
            onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
            disabled={mode === 'edit'}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none disabled:opacity-60"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.columns.entity')}</label>
            <input
              value={form.entity}
              onChange={(e) => setForm((current) => ({ ...current, entity: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.columns.source')}</label>
            <input
              value={form.source_name}
              onChange={(e) => setForm((current) => ({ ...current, source_name: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.detail.source_entity')}</label>
            <input
              value={form.source_entity}
              onChange={(e) => setForm((current) => ({ ...current, source_entity: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.detail.relationship')}</label>
            <input
              value={form.relationship}
              onChange={(e) => setForm((current) => ({ ...current, relationship: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.detail.aggregation')}</label>
            <input
              value={form.aggregation}
              onChange={(e) => setForm((current) => ({ ...current, aggregation: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.columns.status')}</label>
            <Select
              value={form.lifecycle_status as 'draft' | 'validated' | 'production' | 'deprecated'}
              onChange={(value) => setForm((current) => ({ ...current, lifecycle_status: value }))}
              options={[
                { value: 'draft', label: t('featureViews.status.draft') },
                { value: 'validated', label: t('featureViews.status.validated') },
                { value: 'production', label: t('featureViews.status.production') },
                { value: 'deprecated', label: t('featureViews.status.deprecated') },
              ]}
              size="md"
              ariaLabel={t('featureViews.columns.status')}
              className="w-full"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">{t('featureViews.detail.features')}</label>
          <textarea
            value={form.feature_names}
            onChange={(e) => setForm((current) => ({ ...current, feature_names: e.target.value }))}
            rows={4}
            placeholder={`billing.payment_delay_count_30d\nbilling.contract_age_days`}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] font-mono focus:border-brand outline-none"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.columns.owner')}</label>
            <input
              value={form.owner}
              onChange={(e) => setForm((current) => ({ ...current, owner: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('featureViews.detail.description')}</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
              rows={3}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        </div>
      </div>
    </Modal>
  )
}
