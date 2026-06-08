import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw, ExternalLink } from 'lucide-react'
import { api, invalidateCache, type BusinessMetricDTO } from '../api'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink, FilterSelect } from '../components/filters'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

const METRIC_DOMAINS = [
  'network_quality',
  'device_intel',
  'customer_experience',
  'billing',
  'service_ops',
  'contact',
  'customer_profile',
] as const

const LIFECYCLE_STAGES = ['consume', 'manage', 'leave'] as const
const METRIC_LEVELS = ['device', 'contract', 'customer', 'mixed'] as const

type MetricDomain = (typeof METRIC_DOMAINS)[number] | ''
type LifecycleStage = (typeof LIFECYCLE_STAGES)[number] | ''
type MetricLevel = (typeof METRIC_LEVELS)[number] | ''

const STATUS_VARIANTS: Record<string, string> = {
  draft: 'default',
  validated: 'success',
  production: 'info',
  deprecated: 'danger',
}

function statusLabel(status: string, t: any): string {
  return t(`status.${status}`, { defaultValue: status })
}

export function BusinessMetrics() {
  const { t } = useTranslation('businessMetrics')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { name } = useParams<{ name?: string }>()

  const [metrics, setMetrics] = useState<(BusinessMetricDTO & { mapped_feature_count: number })[]>([])
  const [detail, setDetail] = useState<BusinessMetricDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('search') ?? '')
  const [metricDomain, setMetricDomain] = useState<MetricDomain>('')
  const [lifecycleStage, setLifecycleStage] = useState<LifecycleStage>('')
  const [metricLevel, setMetricLevel] = useState<MetricLevel>('')
  const [businessObjective, setBusinessObjective] = useState('')
  const [owner, setOwner] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/business-metrics')
    api.businessMetrics
      .list({
        metric_domain: metricDomain || undefined,
        lifecycle_stage: lifecycleStage || undefined,
        metric_level: metricLevel || undefined,
        business_objective: businessObjective || undefined,
        owner: owner || undefined,
        search: searchQuery || undefined,
      })
      .then((rows) => {
        const items = Array.isArray(rows)
          ? rows.map((row) => ({ ...row, mapped_feature_count: row.mapped_features?.length ?? 0 }))
          : []
        setMetrics(items)
      })
      .catch(() => setMetrics([]))
      .finally(() => setLoading(false))
  }, [businessObjective, lifecycleStage, metricDomain, metricLevel, owner, searchQuery])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!name) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    api.businessMetrics.get(name)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [name])

  const hasFilters = useMemo(
    () => !!(searchQuery || metricDomain || lifecycleStage || metricLevel || businessObjective || owner),
    [searchQuery, metricDomain, lifecycleStage, metricLevel, businessObjective, owner],
  )

  const clearFilters = () => {
    setSearchQuery('')
    setMetricDomain('')
    setLifecycleStage('')
    setMetricLevel('')
    setBusinessObjective('')
    setOwner('')
  }

  const selectedMetric = detail ?? metrics.find((metric) => metric.name === name) ?? null

  const selectMetric = (metric: BusinessMetricDTO) => {
    navigate(`/business-metrics/${encodeURIComponent(metric.name)}`)
  }

  const refresh = () => load()

  return (
    <div>
      <PageHeader
        title={t('page.title')}
        subtitle={t('page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('page.count', { count: metrics.length })}</span>
            <button
              onClick={refresh}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {t('actions.refresh', { defaultValue: 'Refresh' })}
            </button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <SearchInput
          placeholder={t('filters.search_placeholder')}
          onSearch={setSearchQuery}
          className="w-full sm:max-w-xs"
        />
        <FilterSelect
          ariaLabel={t('filters.all_domains')}
          value={metricDomain}
          onChange={setMetricDomain}
          options={[
            { value: '', label: t('filters.all_domains') },
            ...METRIC_DOMAINS.map((value) => ({ value, label: value })),
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_stages')}
          value={lifecycleStage}
          onChange={setLifecycleStage}
          options={[
            { value: '', label: t('filters.all_stages') },
            ...LIFECYCLE_STAGES.map((value) => ({ value, label: value })),
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_levels')}
          value={metricLevel}
          onChange={setMetricLevel}
          options={[
            { value: '', label: t('filters.all_levels') },
            ...METRIC_LEVELS.map((value) => ({ value, label: value })),
          ]}
        />
        <input
          value={businessObjective}
          onChange={(e) => setBusinessObjective(e.target.value)}
          placeholder={t('filters.objective_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-56"
        />
        <input
          value={owner}
          onChange={(e) => setOwner(e.target.value)}
          placeholder={t('filters.owner_placeholder')}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-brand w-full sm:w-44"
        />
        <FilterClearLink show={hasFilters} onClick={clearFilters} />
      </div>

      <div className="flex flex-col lg:flex-row gap-4" style={{ minHeight: '520px' }}>
        <div className="lg:w-[58%] bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-3">
          {loading && metrics.length === 0 ? (
            <Skeleton className="h-48" />
          ) : metrics.length === 0 ? (
            <div className="py-16 text-center text-sm text-[var(--text-tertiary)]">
              <p>{t('empty.title')}</p>
              <p className="mt-1">{t('empty.hint')}</p>
            </div>
          ) : (
            <DataTable
              data={metrics}
              pageSize={18}
              onRowClick={selectMetric}
              columns={[
                {
                  key: 'name',
                  label: t('columns.name'),
                  render: (row) => (
                    <div>
                      <div className="font-medium text-brand">{row.business_metric_name}</div>
                      <div className="text-[11px] text-[var(--text-tertiary)]">{row.name}</div>
                    </div>
                  ),
                },
                { key: 'metric_domain', label: t('columns.domain') },
                { key: 'lifecycle_stage', label: t('columns.stage') },
                { key: 'metric_level', label: t('columns.level') },
                { key: 'owner', label: t('columns.owner') },
                {
                  key: 'mapped_feature_count',
                  label: t('columns.features'),
                  sortable: false,
                  render: (row) => <span className="font-mono text-xs">{row.mapped_feature_count}</span>,
                },
                {
                  key: 'lifecycle_status',
                  label: t('columns.status'),
                  sortable: false,
                  render: (row) => (
                    <Badge variant={STATUS_VARIANTS[row.lifecycle_status] || 'default'}>
                      {statusLabel(row.lifecycle_status, t)}
                    </Badge>
                  ),
                },
              ]}
            />
          )}
        </div>

        <div className="flex-1 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
          {!name ? (
            <div className="h-full min-h-[420px] flex items-center justify-center text-sm text-[var(--text-tertiary)]">
              {t('detail.select_hint')}
            </div>
          ) : detailLoading && !selectedMetric ? (
            <Skeleton className="h-48" />
          ) : selectedMetric ? (
            <div data-testid="business-metric-detail" className="space-y-4">
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold break-words">{selectedMetric.business_metric_name}</h2>
                  <div className="text-xs text-[var(--text-tertiary)] break-words">{selectedMetric.name}</div>
                </div>
                <Badge variant={STATUS_VARIANTS[selectedMetric.lifecycle_status] || 'default'}>
                  {statusLabel(selectedMetric.lifecycle_status, t)}
                </Badge>
              </div>

              <div className="flex flex-wrap gap-2">
                <Badge variant="info">{selectedMetric.metric_domain}</Badge>
                <Badge variant="default">{selectedMetric.lifecycle_stage}</Badge>
                <Badge variant="default">{selectedMetric.metric_level}</Badge>
                {selectedMetric.metric_group && <Badge variant="default">{selectedMetric.metric_group}</Badge>}
                {selectedMetric.owner && <Badge variant="default">{selectedMetric.owner}</Badge>}
              </div>

              <section className="space-y-1">
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                  {t('detail.definition')}
                </div>
                <p className="text-sm text-[var(--text-secondary)]">{selectedMetric.business_definition || '-'}</p>
              </section>

              <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                    {t('detail.objective')}
                  </div>
                  <p className="text-sm text-[var(--text-secondary)]">{selectedMetric.business_definition || '-'}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                    {t('detail.technical_grain')}
                  </div>
                  <p className="text-sm font-mono text-[var(--text-secondary)]">{selectedMetric.entity_grain || '-'}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                    {t('detail.aggregation')}
                  </div>
                  <p className="text-sm text-[var(--text-secondary)]">{selectedMetric.aggregation_rule || '-'}</p>
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                    {t('detail.group')}
                  </div>
                  <p className="text-sm text-[var(--text-secondary)]">{selectedMetric.metric_group || '-'}</p>
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                    {t('detail.mapped_features')}
                  </div>
                  <span className="text-xs text-[var(--text-tertiary)]">
                    {t('detail.mapped_count', { count: selectedMetric.mapped_features.length })}
                  </span>
                </div>
                {selectedMetric.mapped_features.length === 0 ? (
                  <p className="text-sm text-[var(--text-tertiary)]">{t('detail.no_features')}</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {selectedMetric.mapped_features.map((feature) => (
                      <Link
                        key={feature}
                        to={`/features/${encodeURIComponent(feature)}`}
                        className="inline-flex items-center gap-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-secondary)] hover:text-brand hover:border-brand transition-colors"
                      >
                        <span className="font-mono">{feature}</span>
                        <ExternalLink size={11} />
                      </Link>
                    ))}
                  </div>
                )}
              </section>

              <section>
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)] mb-2">
                  {t('detail.use_cases')}
                </div>
                {selectedMetric.allowed_use_cases.length === 0 ? (
                  <p className="text-sm text-[var(--text-tertiary)]">-</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {selectedMetric.allowed_use_cases.map((useCase) => (
                      <Badge key={useCase} variant="default">{useCase}</Badge>
                    ))}
                  </div>
                )}
              </section>
            </div>
          ) : (
            <div className="h-full min-h-[420px] flex items-center justify-center text-sm text-[var(--text-tertiary)]">
              {t('detail.select_hint')}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
