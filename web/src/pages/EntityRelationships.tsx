import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Pencil, Plus, RefreshCw, ExternalLink } from 'lucide-react'
import { api, invalidateCache, type EntityRelationshipDTO } from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink, FilterSelect } from '../components/filters'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Select } from '../components/Select'
import { Skeleton } from '../components/Skeleton'
import { formatPrettyJson, parseJsonValue } from '../components/registryFormUtils'
import { canWrite, useAuthMaybe } from '../auth'

const RELATION_TYPES = ['one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'] as const
type RelationType = (typeof RELATION_TYPES)[number]
const STATUS_VARIANTS: Record<string, string> = {
  draft: 'default',
  validated: 'success',
  production: 'info',
  deprecated: 'danger',
}

function statusLabel(status: string, t: any): string {
  return t(`status.${status}`, { defaultValue: status })
}

export function EntityRelationships() {
  const { t } = useTranslation('featureRegistry')
  const auth = useAuthMaybe()
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()
  const [searchParams] = useSearchParams()
  const canMutate = canWrite(auth?.auth?.user)

  const [items, setItems] = useState<EntityRelationshipDTO[]>([])
  const [detail, setDetail] = useState<EntityRelationshipDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('search') ?? '')
  const [leftEntity, setLeftEntity] = useState('')
  const [rightEntity, setRightEntity] = useState('')
  const [relationType, setRelationType] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<'create' | 'edit'>('create')
  const [editorError, setEditorError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/entity-relationships')
    api.entityRelationships
      .list({
        left_entity: leftEntity || undefined,
        right_entity: rightEntity || undefined,
        relation_type: relationType || undefined,
      })
      .then((rows) => {
        const filtered = Array.isArray(rows)
          ? rows.filter((row) => {
              const q = searchQuery.trim().toLowerCase()
              return !q || [row.name, row.left_entity, row.right_entity, row.owner, row.description].some((value) =>
                String(value ?? '').toLowerCase().includes(q),
              )
            })
          : []
        setItems(filtered)
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [leftEntity, relationType, rightEntity, searchQuery])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!name) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    api.entityRelationships
      .get(name)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [name])

  const hasFilters = useMemo(() => !!(searchQuery || leftEntity || rightEntity || relationType), [searchQuery, leftEntity, rightEntity, relationType])

  const clearFilters = () => {
    setSearchQuery('')
    setLeftEntity('')
    setRightEntity('')
    setRelationType('')
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
  const onSaved = async (relationshipName: string) => {
    closeEditor()
    await load()
    navigate(`/entity-relationships/${encodeURIComponent(relationshipName)}`)
  }

  return (
    <div>
      <PageHeader
        title={t('relationships.page.title')}
        subtitle={t('relationships.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('relationships.page.count', { count: items.length })}</span>
            {canMutate && (
              <button onClick={openCreate} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors">
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
        <SearchInput placeholder={t('relationships.filters.search_placeholder')} onSearch={setSearchQuery} className="w-full sm:max-w-xs" />
        <input
          value={leftEntity}
          onChange={(e) => setLeftEntity(e.target.value)}
          placeholder={t('relationships.filters.left_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <input
          value={rightEntity}
          onChange={(e) => setRightEntity(e.target.value)}
          placeholder={t('relationships.filters.right_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <FilterSelect
          ariaLabel={t('relationships.columns.type')}
          value={relationType}
          onChange={setRelationType}
          options={[
            { value: '', label: t('filters.all_types', { defaultValue: 'All types' }) },
            ...RELATION_TYPES.map((value) => ({ value, label: value })),
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
              <p>{t('relationships.empty.title')}</p>
              <p className="mt-1">{t('relationships.empty.hint')}</p>
              {canMutate && (
                <button onClick={openCreate} className="mt-4 inline-flex items-center gap-1.5 text-xs text-brand hover:underline">
                  <Plus size={12} />
                  {t('actions.create', { defaultValue: 'Create relationship' })}
                </button>
              )}
            </div>
          ) : (
            <DataTable
              data={items}
              pageSize={18}
              onRowClick={(row) => navigate(`/entity-relationships/${encodeURIComponent(row.name)}`)}
              columns={[
                {
                  key: 'name',
                  label: t('relationships.columns.name'),
                  render: (row) => (
                    <div>
                      <div className="font-medium text-brand">{row.name}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{row.left_entity} → {row.right_entity}</div>
                    </div>
                  ),
                },
                { key: 'left_entity', label: t('relationships.columns.left') },
                { key: 'right_entity', label: t('relationships.columns.right') },
                { key: 'relation_type', label: t('relationships.columns.type') },
                {
                  key: 'lifecycle_status',
                  label: t('relationships.columns.status'),
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
              {t('relationships.detail.select_hint')}
            </div>
          ) : detailLoading && !selected ? (
            <Skeleton className="h-48" />
          ) : selected ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold break-words">{selected.name}</h2>
                  <div className="text-xs text-[var(--text-tertiary)] break-words">{selected.left_entity} → {selected.right_entity}</div>
                </div>
                <Badge variant={STATUS_VARIANTS[selected.lifecycle_status] || 'default'}>{statusLabel(selected.lifecycle_status, t)}</Badge>
              </div>

              <div className="flex flex-wrap gap-2">
                <Badge variant="info">{selected.relation_type}</Badge>
                {selected.owner && <Badge variant="default">{selected.owner}</Badge>}
                <Link to={`/entities/${encodeURIComponent(selected.left_entity)}`} className="inline-flex items-center gap-1 text-xs text-brand hover:underline">
                  {t('relationships.detail.left_link')}
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
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('relationships.detail.join_keys')}</div>
                  <div className="mt-1 space-y-1">
                    {selected.join_keys.map((key) => (
                      <div key={`${key.left_key}-${key.right_key}`} className="font-mono text-xs break-words">
                        {key.left_key} → {key.right_key}
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('relationships.detail.temporal')}</div>
                  <div className="mt-1 break-words">
                    {selected.valid_from || selected.valid_to || selected.event_time
                      ? [selected.valid_from, selected.valid_to, selected.event_time].filter(Boolean).join(' | ')
                      : '-'}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('relationships.detail.description')}</div>
                  <div className="mt-1 break-words">{selected.description || '-'}</div>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <EntityRelationshipEditorModal
        open={editorOpen}
        mode={editorMode}
        relationship={editorMode === 'edit' ? selected : null}
        onClose={closeEditor}
        onSaved={onSaved}
        canMutate={canMutate}
        error={editorError}
        setError={setEditorError}
      />
    </div>
  )
}

function EntityRelationshipEditorModal({
  open,
  mode,
  relationship,
  onClose,
  onSaved,
  canMutate,
  error,
  setError,
}: {
  open: boolean
  mode: 'create' | 'edit'
  relationship: EntityRelationshipDTO | null
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
    left_entity: '',
    right_entity: '',
    relation_type: 'one_to_one' as RelationType,
    join_keys: '[]',
    valid_from: '',
    valid_to: '',
    event_time: '',
    description: '',
    owner: '',
    lifecycle_status: 'draft',
  })

  useEffect(() => {
    if (!open) return
    setError(null)
    if (mode === 'edit' && relationship) {
      setForm({
        name: relationship.name,
        left_entity: relationship.left_entity,
        right_entity: relationship.right_entity,
        relation_type: relationship.relation_type as RelationType,
        join_keys: formatPrettyJson(relationship.join_keys),
        valid_from: relationship.valid_from ?? '',
        valid_to: relationship.valid_to ?? '',
        event_time: relationship.event_time ?? '',
        description: relationship.description ?? '',
        owner: relationship.owner ?? '',
        lifecycle_status: relationship.lifecycle_status ?? 'draft',
      })
    } else {
      setForm({
        name: '',
        left_entity: '',
        right_entity: '',
        relation_type: 'one_to_one',
        join_keys: '[]',
        valid_from: '',
        valid_to: '',
        event_time: '',
        description: '',
        owner: '',
        lifecycle_status: 'draft',
      })
    }
  }, [mode, open, relationship, setError])

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
      await api.entityRelationships.upsert({
        name,
        left_entity: form.left_entity.trim(),
        right_entity: form.right_entity.trim(),
        relation_type: form.relation_type,
        join_keys: form.join_keys.trim() ? parseJsonValue<Array<{ left_key: string; right_key: string }>>(form.join_keys) : [],
        valid_from: form.valid_from.trim() || null,
        valid_to: form.valid_to.trim() || null,
        event_time: form.event_time.trim() || null,
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
      title={mode === 'edit' ? t('actions.edit', { defaultValue: 'Edit relationship' }) : t('actions.create', { defaultValue: 'Create relationship' })}
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
            {t('relationships.columns.name')} <span className="text-[var(--danger)]">*</span>
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
            <label className="block text-xs font-medium mb-1">{t('relationships.columns.left')}</label>
            <input
              value={form.left_entity}
              onChange={(e) => setForm((current) => ({ ...current, left_entity: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('relationships.columns.right')}</label>
            <input
              value={form.right_entity}
              onChange={(e) => setForm((current) => ({ ...current, right_entity: e.target.value }))}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('relationships.columns.type')}</label>
            <Select
              value={form.relation_type}
              onChange={(value) => setForm((current) => ({ ...current, relation_type: value }))}
              options={RELATION_TYPES.map((value) => ({ value, label: value }))}
              size="md"
              ariaLabel={t('relationships.columns.type')}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('relationships.columns.status')}</label>
            <Select
              value={form.lifecycle_status as 'draft' | 'validated' | 'production' | 'deprecated'}
              onChange={(value) => setForm((current) => ({ ...current, lifecycle_status: value }))}
              options={[
                { value: 'draft', label: t('relationships.status.draft') },
                { value: 'validated', label: t('relationships.status.validated') },
                { value: 'production', label: t('relationships.status.production') },
                { value: 'deprecated', label: t('relationships.status.deprecated') },
              ]}
              size="md"
              ariaLabel={t('relationships.columns.status')}
              className="w-full"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">{t('relationships.detail.join_keys')}</label>
          <textarea
            value={form.join_keys}
            onChange={(e) => setForm((current) => ({ ...current, join_keys: e.target.value }))}
            rows={5}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] font-mono focus:border-brand outline-none"
            placeholder={`[
  { "left_key": "customer_id", "right_key": "customer_id" }
]`}
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">{t('relationships.detail.temporal')}</label>
            <div className="grid grid-cols-1 gap-2">
              <input
                value={form.valid_from}
                onChange={(e) => setForm((current) => ({ ...current, valid_from: e.target.value }))}
                placeholder="valid from"
                className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
              />
              <input
                value={form.valid_to}
                onChange={(e) => setForm((current) => ({ ...current, valid_to: e.target.value }))}
                placeholder="valid to"
                className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
              />
              <input
                value={form.event_time}
                onChange={(e) => setForm((current) => ({ ...current, event_time: e.target.value }))}
                placeholder="event time"
                className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">{t('relationships.detail.description')}</label>
            <textarea
              value={form.description}
              onChange={(e) => setForm((current) => ({ ...current, description: e.target.value }))}
              rows={5}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        </div>
        <div>
          <label className="block text-xs font-medium mb-1">Owner</label>
          <input
            value={form.owner}
            onChange={(e) => setForm((current) => ({ ...current, owner: e.target.value }))}
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
          />
        </div>
      </div>
    </Modal>
  )
}
