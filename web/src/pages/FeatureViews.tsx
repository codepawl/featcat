import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { api, invalidateCache, type FeatureViewDTO } from '../api'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink, FilterSelect } from '../components/filters'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

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
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()

  const [items, setItems] = useState<FeatureViewDTO[]>([])
  const [detail, setDetail] = useState<FeatureViewDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [entity, setEntity] = useState('')
  const [owner, setOwner] = useState('')
  const [status, setStatus] = useState<LifecycleStatus>('')

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

  return (
    <div>
      <PageHeader
        title={t('featureViews.page.title')}
        subtitle={t('featureViews.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('featureViews.page.count', { count: items.length })}</span>
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
    </div>
  )
}
