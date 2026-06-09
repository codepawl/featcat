import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Pencil, Plus, RefreshCw, ExternalLink } from 'lucide-react'
import { api, invalidateCache, type EntityDTO } from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink } from '../components/filters'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Select } from '../components/Select'
import { Skeleton } from '../components/Skeleton'
import { formatLines, parseLines } from '../components/registryFormUtils'
import { canWrite, useAuthMaybe } from '../auth'

const STATUS_VARIANTS: Record<string, string> = {
  draft: 'default',
  validated: 'success',
  production: 'info',
  deprecated: 'danger',
}

function statusLabel(status: string, t: any): string {
  return t(`status.${status}`, { defaultValue: status })
}

export function Entities() {
  const { t } = useTranslation('featureRegistry')
  const auth = useAuthMaybe()
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()
  const canMutate = canWrite(auth?.auth?.user)

  const [items, setItems] = useState<EntityDTO[]>([])
  const [detail, setDetail] = useState<EntityDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [owner, setOwner] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create')
  const [editorError, setEditorError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/entities')
    api.entities
      .list()
      .then((rows) => {
        const filtered = Array.isArray(rows)
          ? rows.filter((row) => {
              const q = searchQuery.trim().toLowerCase()
              const matchesSearch = !q || [row.name, row.description, row.owner, row.source_of_truth].some((value) =>
                String(value ?? '').toLowerCase().includes(q),
              )
              const matchesOwner = !owner || row.owner.includes(owner)
              return matchesSearch && matchesOwner
            })
          : []
        setItems(filtered)
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [owner, searchQuery])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!name) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    api.entities
      .get(name)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [name])

  const hasFilters = useMemo(() => !!(searchQuery || owner), [searchQuery, owner])

  const clearFilters = () => {
    setSearchQuery('')
    setOwner('')
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
  const onSaved = async (entityName: string) => {
    closeEditor()
    await load()
    navigate(`/entities/${encodeURIComponent(entityName)}`)
  }

  return (
    <div>
      <PageHeader
        title={t('entities.page.title')}
        subtitle={t('entities.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('entities.page.count', { count: items.length })}</span>
            {canMutate && (
              <button
                onClick={openCreate}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors"
              >
                <Plus size={14} />
                {t('actions.new', { defaultValue: 'New' })}
              </button>
            )}
            <button onClick={load} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors">
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {t('actions.refresh', { defaultValue: 'Refresh' })}
            </button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <SearchInput placeholder={t('entities.filters.search_placeholder')} onSearch={setSearchQuery} className="w-full sm:max-w-xs" />
        <input
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          placeholder={t('entities.filters.owner_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <FilterClearLink show={hasFilters} onClick={clearFilters} />
      </div>

      <div className="flex flex-col lg:flex-row gap-4" style={{ minHeight: '520px' }}>
        <div className="lg:w-[58%] bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-3">
          {loading && items.length === 0 ? (
            <Skeleton className="h-48" />
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-sm text-[var(--text-tertiary)]">
              <p>{t('entities.empty.title')}</p>
              <p className="mt-1">{t('entities.empty.hint')}</p>
              {canMutate && (
                <button onClick={openCreate} className="mt-4 inline-flex items-center gap-1.5 text-xs text-brand hover:underline">
                  <Plus size={12} />
                  {t('actions.create', { defaultValue: 'Create entity' })}
                </button>
              )}
            </div>
          ) : (
            <DataTable
              data={items}
              pageSize={18}
              onRowClick={(row) => navigate(`/entities/${encodeURIComponent(row.name)}`)}
              columns={[
                {
                  key: 'name',
                  label: t('entities.columns.name'),
                  render: (row) => (
                    <div>
                      <div className="font-medium text-brand">{row.name}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{row.source_of_truth || '-'}</div>
                    </div>
                  ),
                },
                { key: 'owner', label: t('entities.columns.owner') },
                { key: 'primary_keys', label: t('entities.columns.primary_keys'), sortable: false, render: (row) => <span className="text-xs font-mono">{row.primary_keys.join(', ')}</span> },
                { key: 'join_keys', label: t('entities.columns.join_keys'), sortable: false, render: (row) => <span className="text-xs font-mono">{row.join_keys.join(', ') || '-'}</span> },
                {
                  key: 'lifecycle_status',
                  label: t('entities.columns.status'),
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
              {t('entities.detail.select_hint')}
            </div>
          ) : detailLoading && !selected ? (
            <Skeleton className="h-48" />
          ) : selected ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold break-words">{selected.name}</h2>
                  <div className="text-xs text-[var(--text-tertiary)] break-words">{selected.source_of_truth || '-'}</div>
                </div>
                <Badge variant={STATUS_VARIANTS[selected.lifecycle_status] || 'default'}>{statusLabel(selected.lifecycle_status, t)}</Badge>
              </div>

              <div className="flex flex-wrap gap-2">
                {selected.owner && <Badge variant="default">{selected.owner}</Badge>}
                <Link to={`/entity-relationships?search=${encodeURIComponent(selected.name)}`} className="inline-flex items-center gap-1 text-xs text-brand hover:underline">
                  {t('entities.detail.relationships_link')}
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
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('entities.detail.primary_keys')}</div>
                  <div className="mt-1 font-mono text-xs break-words">{selected.primary_keys.join(', ')}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('entities.detail.join_keys')}</div>
                  <div className="mt-1 font-mono text-xs break-words">{selected.join_keys.join(', ') || '-'}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('entities.detail.source_of_truth')}</div>
                  <div className="mt-1 break-words">{selected.source_of_truth || '-'}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('entities.detail.description')}</div>
                  <div className="mt-1 break-words">{selected.description || '-'}</div>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <EntityEditorModal
        open={editorOpen}
        mode={editorMode}
        entity={editorMode === 'edit' ? selected : null}
        onClose={closeEditor}
        onSaved={onSaved}
        canMutate={canMutate}
        error={editorError}
        setError={setEditorError}
      />
    </div>
  )
}

function EntityEditorModal({
  open,
  mode,
  entity,
  onClose,
  onSaved,
  canMutate,
  error,
  setError,
}: {
  open: boolean
  mode: 'create' | 'edit'
  entity: EntityDTO | null
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
    primary_keys: '',
    join_keys: '',
    description: '',
    owner: '',
    source_of_truth: '',
    lifecycle_status: 'draft',
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    if (mode === 'edit' && entity) {
      setForm({
        name: entity.name,
        primary_keys: formatLines(entity.primary_keys),
        join_keys: formatLines(entity.join_keys),
        description: entity.description ?? '',
        owner: entity.owner ?? '',
        source_of_truth: entity.source_of_truth ?? '',
        lifecycle_status: entity.lifecycle_status ?? 'draft',
      })
    } else {
      setForm({
        name: '',
        primary_keys: '',
        join_keys: '',
        description: '',
        owner: '',
        source_of_truth: '',
        lifecycle_status: 'draft',
      })
    }
  }, [entity, mode, open, setError])

  const submit = async () => {
    if (!canMutate || saving) return
    const name = form.name.trim()
    if (!name) {
      setError(t('errors.name_required', { defaultValue: 'Name is required.' }))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await api.entities.upsert({
        name,
        primary_keys: parseLines(form.primary_keys),
        join_keys: parseLines(form.join_keys),
        description: form.description.trim(),
        owner: form.owner.trim(),
        source_of_truth: form.source_of_truth.trim(),
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
      title={mode === 'edit' ? t('actions.edit', { defaultValue: 'Edit entity' }) : t('actions.create', { defaultValue: 'Create entity' })}
      maxWidth="max-w-2xl"
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
            {t('entities.columns.name')} <span className="text-[var(--danger)]">*</span>
          </label>
          <input
            value={form.name}
            onChange={(e) => setForm((current) => ({ ...current, name: e.target.value }))}
            disabled={mode === 'edit'}
            placeholder="customer"
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none disabled:opacity-60"
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('entities.detail.primary_keys')}</label>
            <textarea
              value={form.primary_keys}
              onChange={(e) => setForm((current) => ({ ...current, primary_keys: e.target.value }))}
              rows={4}
              placeholder="customer_id"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('entities.detail.join_keys')}</label>
            <textarea
              value={form.join_keys}
              onChange={(e) => setForm((current) => ({ ...current, join_keys: e.target.value }))}
              rows={4}
              placeholder="customer_id"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('entities.detail.source_of_truth')}</label>
            <input
              value={form.source_of_truth}
              onChange={(e) => setForm((current) => ({ ...current, source_of_truth: e.target.value }))}
              placeholder="crm"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('entities.columns.status')}</label>
            <Select
              value={form.lifecycle_status as 'draft' | 'validated' | 'production' | 'deprecated'}
              onChange={(value) => setForm((current) => ({ ...current, lifecycle_status: value }))}
              options={[
                { value: 'draft', label: t('entities.status.draft') },
                { value: 'validated', label: t('entities.status.validated') },
                { value: 'production', label: t('entities.status.production') },
                { value: 'deprecated', label: t('entities.status.deprecated') },
              ]}
              size="md"
              ariaLabel={t('entities.columns.status')}
              className="w-full"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">{t('entities.detail.description')}</label>
          <textarea
            value={form.description}
            onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
            rows={4}
            placeholder={t('entities.detail.description')}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
          />
        </div>
      </div>
    </Modal>
  )
}
