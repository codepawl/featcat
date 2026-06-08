import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { api, invalidateCache, type FeatureSetDTO } from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink } from '../components/filters'
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

export function FeatureSets() {
  const { t } = useTranslation('featureRegistry')
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()

  const [items, setItems] = useState<FeatureSetDTO[]>([])
  const [detail, setDetail] = useState<FeatureSetDTO | null>(null)
  const [featureDetails, setFeatureDetails] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [targetEntity, setTargetEntity] = useState('')
  const [owner, setOwner] = useState('')
  const [status, setStatus] = useState<LifecycleStatus>('')

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/feature-sets')
    api.featureSets
      .list({
        target_entity: targetEntity || undefined,
        owner: owner || undefined,
      })
      .then((rows) => {
        const filtered = Array.isArray(rows)
          ? rows.filter((row) => {
              const matchesStatus = status ? row.lifecycle_status === status : true
              const q = searchQuery.trim().toLowerCase()
              const matchesSearch = !q || [
                row.name,
                row.target_entity,
                row.use_case,
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
  }, [owner, searchQuery, status, targetEntity])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!name) {
      setDetail(null)
      setFeatureDetails([])
      return
    }
    setDetailLoading(true)
    api.featureSets
      .get(name)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [name])

  useEffect(() => {
    if (!detail?.feature_names?.length) {
      setFeatureDetails([])
      return
    }
    Promise.all(detail.feature_names.map((featureName) => api.features.get(featureName).catch(() => null)))
      .then((rows) => setFeatureDetails(rows.filter(Boolean)))
      .catch(() => setFeatureDetails([]))
  }, [detail])

  const hasFilters = useMemo(() => !!(searchQuery || targetEntity || owner || status), [searchQuery, targetEntity, owner, status])

  const clearFilters = () => {
    setSearchQuery('')
    setTargetEntity('')
    setOwner('')
    setStatus('')
  }

  const selected = detail ?? items.find((row) => row.name === name) ?? null
  const validationWarnings = useMemo(() => {
    if (!selected) return [] as string[]
    const warnings: string[] = []
    if (selected.lifecycle_status === 'production') {
      const highLeakage = featureDetails.filter((feature) => feature?.leakage_risk === 'high').map((feature) => feature.name)
      if (highLeakage.length > 0) {
        warnings.push(
          t('featureSets.validation.high_leakage', {
            count: highLeakage.length,
            features: highLeakage.join(', '),
          }),
        )
      }
    }
    return warnings
  }, [featureDetails, selected, t])

  return (
    <div>
      <PageHeader
        title={t('featureSets.page.title')}
        subtitle={t('featureSets.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('featureSets.page.count', { count: items.length })}</span>
            <button
              onClick={load}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {t('featureSets.actions.refresh')}
            </button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <SearchInput placeholder={t('featureSets.filters.search_placeholder')} onSearch={setSearchQuery} className="w-full sm:max-w-xs" />
        <input
          value={targetEntity}
          onChange={(e) => setTargetEntity(e.target.value)}
          placeholder={t('featureSets.filters.entity_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <input
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          placeholder={t('featureSets.filters.owner_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as LifecycleStatus)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        >
          <option value="">{t('filters.all_statuses', { defaultValue: 'All statuses' })}</option>
          {LIFECYCLE_STATUSES.map((value) => (
            <option key={value} value={value}>{t(`featureSets.status.${value}`)}</option>
          ))}
        </select>
        <FilterClearLink show={hasFilters} onClick={clearFilters} />
      </div>

      <div className="flex flex-col lg:flex-row gap-4" style={{ minHeight: '520px' }}>
        <div className="lg:w-[58%] bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-3">
          {loading && items.length === 0 ? (
            <Skeleton className="h-48" />
          ) : items.length === 0 ? (
            <div className="py-16 text-center text-sm text-[var(--text-tertiary)]">
              <p>{t('featureSets.empty.title')}</p>
              <p className="mt-1">{t('featureSets.empty.hint')}</p>
            </div>
          ) : (
            <DataTable
              data={items}
              pageSize={18}
              onRowClick={(row) => navigate(`/feature-sets/${encodeURIComponent(row.name)}`)}
              columns={[
                {
                  key: 'name',
                  label: t('featureSets.columns.name'),
                  render: (row) => (
                    <div>
                      <div className="font-medium text-brand">{row.name}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{row.use_case}</div>
                    </div>
                  ),
                },
                { key: 'target_entity', label: t('featureSets.columns.target_entity') },
                { key: 'use_case', label: t('featureSets.columns.use_case') },
                { key: 'owner', label: t('featureSets.columns.owner') },
                {
                  key: 'feature_count',
                  label: t('featureSets.columns.features'),
                  sortable: false,
                  render: (row) => <span className="font-mono text-xs">{row.feature_names?.length ?? 0}</span>,
                },
                {
                  key: 'lifecycle_status',
                  label: t('featureSets.columns.status'),
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
              {t('featureSets.detail.select_hint')}
            </div>
          ) : detailLoading && !selected ? (
            <Skeleton className="h-48" />
          ) : selected ? (
            <div className="space-y-4">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold break-words">{selected.name}</h2>
                  <div className="text-xs text-[var(--text-tertiary)] break-words">{selected.target_entity}</div>
                </div>
                <Badge variant={STATUS_VARIANTS[selected.lifecycle_status] || 'default'}>{statusLabel(selected.lifecycle_status, t)}</Badge>
              </div>

              <div className="flex flex-wrap gap-2">
                {selected.owner && <Badge variant="default">{selected.owner}</Badge>}
                <Link
                  to={`/features?search=${encodeURIComponent(selected.name)}`}
                  className="inline-flex items-center gap-1 text-xs text-brand hover:underline"
                >
                  {t('featureSets.detail.feature_link')}
                  <ExternalLink size={12} />
                </Link>
              </div>

              {selected.lifecycle_status === 'production' && (
                <Alert
                  severity={validationWarnings.length > 0 ? 'warning' : 'success'}
                  message={
                    validationWarnings.length > 0
                      ? validationWarnings[0]
                      : t('featureSets.validation.ok')
                  }
                />
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('featureSets.detail.use_case')}</div>
                  <div className="mt-1">{selected.use_case || '-'}</div>
                </div>
                <div>
                  <div className="text-[11px] text-[var(--text-tertiary)] uppercase tracking-wide">{t('featureSets.detail.description')}</div>
                  <div className="mt-1 break-words">{selected.description || '-'}</div>
                </div>
              </div>

              <div>
                <div className="text-sm font-medium mb-2">{t('featureSets.detail.rollup_rules')}</div>
                {Object.keys(selected.rollup_rules || {}).length ? (
                  <div className="space-y-2">
                    {Object.entries(selected.rollup_rules).map(([featureName, rule]) => (
                      <div key={featureName} className="flex flex-wrap gap-2 items-start justify-between rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm">
                        <Link to={`/features/${encodeURIComponent(featureName)}`} className="text-brand hover:underline">
                          {featureName}
                        </Link>
                        <span className="text-[var(--text-secondary)] break-words">{rule}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-[var(--text-tertiary)]">-</div>
                )}
              </div>

              <div>
                <div className="text-sm font-medium mb-2">{t('featureSets.detail.features')}</div>
                {selected.feature_names?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {selected.feature_names.map((featureName) => (
                      <Link key={featureName} to={`/features/${encodeURIComponent(featureName)}`} className="text-xs px-2.5 py-1 rounded-full border border-[var(--border-default)] hover:bg-[var(--bg-secondary)]">
                        {featureName}
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-[var(--text-tertiary)]">{t('featureSets.detail.no_features')}</div>
                )}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
