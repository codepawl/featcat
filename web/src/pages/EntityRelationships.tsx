import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw, ExternalLink } from 'lucide-react'
import { api, invalidateCache, type EntityRelationshipDTO } from '../api'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink, FilterSelect } from '../components/filters'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

const RELATION_TYPES = ['one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'] as const
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
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()
  const [searchParams] = useSearchParams()

  const [items, setItems] = useState<EntityRelationshipDTO[]>([])
  const [detail, setDetail] = useState<EntityRelationshipDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('search') ?? '')
  const [leftEntity, setLeftEntity] = useState('')
  const [rightEntity, setRightEntity] = useState('')
  const [relationType, setRelationType] = useState('')

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

  return (
    <div>
      <PageHeader
        title={t('relationships.page.title')}
        subtitle={t('relationships.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('relationships.page.count', { count: items.length })}</span>
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
    </div>
  )
}
