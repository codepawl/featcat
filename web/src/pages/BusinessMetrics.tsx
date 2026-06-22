import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ExternalLink, Grid3X3, RefreshCw, Table2, Upload } from 'lucide-react'
import {
  api,
  invalidateCache,
  type BusinessMetricCsvImportResult,
  type BusinessMetricDTO,
} from '../api'
import { canWrite, useAuthMaybe } from '../auth'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink, FilterSelect } from '../components/filters'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

type BusinessMetricRow = BusinessMetricDTO & { mapped_feature_count: number }
type ViewMode = 'registry' | 'matrix'

const STATUS_VARIANTS: Record<string, string> = {
  draft: 'default',
  validated: 'success',
  production: 'info',
  deprecated: 'danger',
}

const IMPLEMENTATION_VARIANTS: Record<string, string> = {
  done: 'success',
  processing: 'info',
  not_started: 'default',
  unknown: 'default',
}

const DOMAIN_ROWS = [
  { key: 'product', label: 'Product', description: 'Products, packages, service lifecycle' },
  { key: 'service', label: 'Service', description: 'Support, technical service, incidents' },
  { key: 'customer', label: 'Customer', description: 'Behavior, contact, satisfaction' },
  { key: 'market_sales', label: 'Market/Sales', description: 'Campaigns, channels, sales motion' },
]

const STAGE_COLUMNS = [
  { key: 'awareness', label: 'Awareness', stages: ['awareness', 'customer_profile'] },
  { key: 'consume', label: 'Consume', stages: ['consume', 'manage', 'pay'] },
  { key: 'leave', label: 'Leave', stages: ['renew', 'recommend', 'leave'] },
]

function statusLabel(status: string, t: any): string {
  return t(`status.${status}`, { defaultValue: status })
}

function implementationLabel(status: string, t: any): string {
  return t(`implementation_status.${status}`, { defaultValue: status || 'unknown' })
}

function normalizeMetric(row: BusinessMetricDTO): BusinessMetricRow {
  return {
    ...row,
    mapped_features: row.mapped_features ?? [],
    allowed_use_cases: row.allowed_use_cases ?? [],
    external_id: row.external_id ?? '',
    source_systems: row.source_systems ?? [],
    implementation_status: row.implementation_status ?? 'unknown',
    source_view: row.source_view ?? '',
    mapped_feature_count: row.mapped_features?.length ?? 0,
  }
}

function metricLevelClass(metric: BusinessMetricDTO): string {
  if (metric.metric_level === 'device') return 'bg-emerald-50 text-emerald-700 border-emerald-200'
  if (metric.metric_level === 'contract') return 'bg-indigo-50 text-indigo-700 border-indigo-200'
  if (metric.metric_level === 'customer') return 'bg-amber-50 text-amber-700 border-amber-200'
  return 'bg-slate-100 text-slate-700 border-slate-200'
}

function metricInBucket(metric: BusinessMetricDTO, domain: string, stages: string[]): boolean {
  return metric.metric_domain === domain && stages.includes(metric.lifecycle_stage)
}

export function BusinessMetrics() {
  const { t } = useTranslation('businessMetrics')
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { name } = useParams<{ name?: string }>()
  const auth = useAuthMaybe()
  const canMutate = canWrite(auth?.auth?.user)

  const [metrics, setMetrics] = useState<BusinessMetricRow[]>([])
  const [detail, setDetail] = useState<BusinessMetricRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('search') ?? '')
  const [metricDomain, setMetricDomain] = useState('')
  const [lifecycleStage, setLifecycleStage] = useState('')
  const [metricLevel, setMetricLevel] = useState('')
  const [businessObjective, setBusinessObjective] = useState('')
  const [owner, setOwner] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('registry')
  const [importOpen, setImportOpen] = useState(false)
  const [importNotice, setImportNotice] = useState<BusinessMetricCsvImportResult | null>(null)

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
        const items = Array.isArray(rows) ? rows.map(normalizeMetric) : []
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
      .then((row) => setDetail(normalizeMetric(row)))
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false))
  }, [name])

  const hasFilters = useMemo(
    () => !!(searchQuery || metricDomain || lifecycleStage || metricLevel || businessObjective || owner),
    [searchQuery, metricDomain, lifecycleStage, metricLevel, businessObjective, owner],
  )

  const filterOptions = useMemo(() => {
    const domains = Array.from(new Set(metrics.map((metric) => metric.metric_domain).filter(Boolean))).sort()
    const stages = Array.from(new Set(metrics.map((metric) => metric.lifecycle_stage).filter(Boolean))).sort()
    const levels = Array.from(new Set(metrics.map((metric) => metric.metric_level).filter(Boolean))).sort()
    return { domains, stages, levels }
  }, [metrics])

  const kpis = useMemo(() => {
    const total = metrics.length
    const completed = metrics.filter((metric) => metric.implementation_status === 'done').length
    return {
      total,
      completed,
      completion: total > 0 ? Math.round((completed / total) * 100) : 0,
      device: metrics.filter((metric) => metric.metric_level === 'device').length,
      contract: metrics.filter((metric) => metric.metric_level === 'contract').length,
      customer: metrics.filter((metric) => metric.metric_level === 'customer').length,
    }
  }, [metrics])

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

  const handleImportComplete = (result: BusinessMetricCsvImportResult) => {
    setImportNotice(result)
    setImportOpen(false)
    refresh()
  }

  return (
    <div>
      <PageHeader
        title={t('page.title')}
        subtitle={t('page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('page.count', { count: metrics.length })}</span>
            <div className="inline-flex rounded-lg border border-[var(--border-default)] overflow-hidden">
              <button
                type="button"
                onClick={() => setViewMode('registry')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  viewMode === 'registry' ? 'bg-[var(--bg-secondary)] text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'
                }`}
              >
                <Table2 size={14} />
                {t('views.registry')}
              </button>
              <button
                type="button"
                onClick={() => setViewMode('matrix')}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border-l border-[var(--border-default)] transition-colors ${
                  viewMode === 'matrix' ? 'bg-[var(--bg-secondary)] text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'
                }`}
              >
                <Grid3X3 size={14} />
                {t('views.matrix')}
              </button>
            </div>
            {canMutate && (
              <button
                type="button"
                onClick={() => setImportOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] transition-colors"
              >
                <Upload size={14} />
                {t('actions.import_csv')}
              </button>
            )}
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

      {importNotice && (
        <Alert
          severity={importNotice.errors.length > 0 ? 'warning' : 'success'}
          className="mb-4"
          dismissible
          onDismiss={() => setImportNotice(null)}
          message={t('import.result', {
            total: importNotice.total,
            created: importNotice.created,
            updated: importNotice.updated,
            skipped: importNotice.skipped,
          })}
        />
      )}

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
            ...filterOptions.domains.map((value) => ({ value, label: value })),
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_stages')}
          value={lifecycleStage}
          onChange={setLifecycleStage}
          options={[
            { value: '', label: t('filters.all_stages') },
            ...filterOptions.stages.map((value) => ({ value, label: value })),
          ]}
        />
        <FilterSelect
          ariaLabel={t('filters.all_levels')}
          value={metricLevel}
          onChange={setMetricLevel}
          options={[
            { value: '', label: t('filters.all_levels') },
            ...filterOptions.levels.map((value) => ({ value, label: value })),
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

      {viewMode === 'matrix' ? (
        <CxMatrix metrics={metrics} kpis={kpis} loading={loading} onSelect={selectMetric} t={t} />
      ) : (
        <RegistryLayout
          metrics={metrics}
          loading={loading}
          name={name}
          detailLoading={detailLoading}
          selectedMetric={selectedMetric}
          onSelect={selectMetric}
          t={t}
        />
      )}

      <ImportCsvModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={handleImportComplete}
        t={t}
      />
    </div>
  )
}

function RegistryLayout({
  metrics,
  loading,
  name,
  detailLoading,
  selectedMetric,
  onSelect,
  t,
}: {
  metrics: BusinessMetricRow[]
  loading: boolean
  name?: string
  detailLoading: boolean
  selectedMetric: BusinessMetricRow | null
  onSelect: (metric: BusinessMetricDTO) => void
  t: any
}) {
  return (
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
            onRowClick={onSelect}
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
              {
                key: 'implementation_status',
                label: t('columns.implementation'),
                sortable: false,
                render: (row) => (
                  <Badge variant={IMPLEMENTATION_VARIANTS[row.implementation_status] || 'default'}>
                    {implementationLabel(row.implementation_status, t)}
                  </Badge>
                ),
              },
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
          <MetricDetail metric={selectedMetric} t={t} />
        ) : (
          <div className="h-full min-h-[420px] flex items-center justify-center text-sm text-[var(--text-tertiary)]">
            {t('detail.select_hint')}
          </div>
        )}
      </div>
    </div>
  )
}

function MetricDetail({ metric, t }: { metric: BusinessMetricRow; t: any }) {
  return (
    <div data-testid="business-metric-detail" className="space-y-4">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold break-words">{metric.business_metric_name}</h2>
          <div className="text-xs text-[var(--text-tertiary)] break-words">{metric.name}</div>
        </div>
        <Badge variant={STATUS_VARIANTS[metric.lifecycle_status] || 'default'}>
          {statusLabel(metric.lifecycle_status, t)}
        </Badge>
      </div>

      <div className="flex flex-wrap gap-2">
        {metric.external_id && <Badge variant="default">{metric.external_id}</Badge>}
        <Badge variant="info">{metric.metric_domain}</Badge>
        <Badge variant="default">{metric.lifecycle_stage}</Badge>
        <Badge variant="default">{metric.metric_level}</Badge>
        <Badge variant={IMPLEMENTATION_VARIANTS[metric.implementation_status] || 'default'}>
          {implementationLabel(metric.implementation_status, t)}
        </Badge>
        {metric.metric_group && <Badge variant="default">{metric.metric_group}</Badge>}
        {metric.owner && <Badge variant="default">{metric.owner}</Badge>}
      </div>

      <section className="space-y-1">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
          {t('detail.definition')}
        </div>
        <p className="text-sm text-[var(--text-secondary)]">{metric.business_definition || '-'}</p>
      </section>

      <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <DetailValue label={t('detail.technical_grain')} value={metric.entity_grain || '-'} mono />
        <DetailValue label={t('detail.aggregation')} value={metric.aggregation_rule || '-'} />
        <DetailValue label={t('detail.group')} value={metric.metric_group || '-'} />
        <DetailValue label={t('detail.source_view')} value={metric.source_view || '-'} />
        <DetailValue label={t('detail.source_systems')} value={metric.source_systems.join(', ') || '-'} />
      </section>

      <section>
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
            {t('detail.mapped_features')}
          </div>
          <span className="text-xs text-[var(--text-tertiary)]">
            {t('detail.mapped_count', { count: metric.mapped_features.length })}
          </span>
        </div>
        {metric.mapped_features.length === 0 ? (
          <p className="text-sm text-[var(--text-tertiary)]">{t('detail.no_features')}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {metric.mapped_features.map((feature) => (
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
        {metric.allowed_use_cases.length === 0 ? (
          <p className="text-sm text-[var(--text-tertiary)]">-</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {metric.allowed_use_cases.map((useCase) => (
              <Badge key={useCase} variant="default">{useCase}</Badge>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function DetailValue({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <p className={`text-sm text-[var(--text-secondary)] ${mono ? 'font-mono' : ''}`}>{value}</p>
    </div>
  )
}

function CxMatrix({
  metrics,
  kpis,
  loading,
  onSelect,
  t,
}: {
  metrics: BusinessMetricRow[]
  kpis: { total: number; completed: number; completion: number; device: number; contract: number; customer: number }
  loading: boolean
  onSelect: (metric: BusinessMetricDTO) => void
  t: any
}) {
  if (loading && metrics.length === 0) {
    return <Skeleton className="h-64" />
  }
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard value={kpis.total} label={t('matrix.total')} sub={t('matrix.completion', { percent: kpis.completion, count: kpis.completed })} />
        <KpiCard value={kpis.device} label={t('matrix.device')} />
        <KpiCard value={kpis.contract} label={t('matrix.contract')} />
        <KpiCard value={kpis.customer} label={t('matrix.customer')} />
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--text-secondary)]">
        <span className="font-medium text-[var(--text-primary)]">{t('matrix.legend')}</span>
        <LegendPill className="bg-emerald-50 text-emerald-700 border-emerald-200" label="Device" />
        <LegendPill className="bg-indigo-50 text-indigo-700 border-indigo-200" label="Contract" />
        <LegendPill className="bg-amber-50 text-amber-700 border-amber-200" label="Customer" />
        <LegendPill className="bg-slate-100 text-slate-700 border-slate-200" label="Mixed" />
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]">
        <table className="w-full min-w-[980px] border-collapse text-sm">
          <thead>
            <tr>
              <th className="w-48 bg-[var(--bg-secondary)] px-4 py-3 text-left text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                {t('matrix.domain_stage')}
              </th>
              {STAGE_COLUMNS.map((stage) => (
                <th key={stage.key} className="px-4 py-3 text-left text-xs uppercase tracking-wide text-[var(--text-tertiary)] border-l border-[var(--border-subtle)]">
                  {stage.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DOMAIN_ROWS.map((domain) => (
              <tr key={domain.key} className="border-t border-[var(--border-subtle)]">
                <td className="px-4 py-4 align-top bg-[var(--bg-secondary)]">
                  <div className="font-semibold">{domain.label}</div>
                  <div className="mt-1 text-xs text-[var(--text-tertiary)]">{domain.description}</div>
                </td>
                {STAGE_COLUMNS.map((stage) => {
                  const bucket = metrics.filter((metric) => metricInBucket(metric, domain.key, stage.stages))
                  return (
                    <td key={stage.key} className="px-4 py-4 align-top border-l border-[var(--border-subtle)]">
                      {bucket.length === 0 ? (
                        <span className="text-xs text-[var(--text-tertiary)]">-</span>
                      ) : (
                        <div className="flex flex-wrap gap-2">
                          {bucket.map((metric) => (
                            <button
                              key={metric.name}
                              type="button"
                              onClick={() => onSelect(metric)}
                              title={`${metric.external_id || metric.name}: ${metric.business_definition || ''}`}
                              className={`max-w-[220px] truncate rounded-full border px-2.5 py-1 text-xs font-medium hover:brightness-95 transition ${metricLevelClass(metric)}`}
                            >
                              {metric.business_metric_name}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function KpiCard({ value, label, sub }: { value: number; label: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-sm text-[var(--text-secondary)]">{label}</div>
      {sub && <div className="mt-2 inline-flex rounded-full bg-[var(--success-subtle-bg)] px-2 py-0.5 text-xs font-medium text-[var(--success)]">{sub}</div>}
    </div>
  )
}

function LegendPill({ className, label }: { className: string; label: string }) {
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 font-medium ${className}`}>{label}</span>
}

function ImportCsvModal({
  open,
  onClose,
  onImported,
  t,
}: {
  open: boolean
  onClose: () => void
  onImported: (result: BusinessMetricCsvImportResult) => void
  t: any
}) {
  const [csvText, setCsvText] = useState('')
  const [fileName, setFileName] = useState('')
  const [namespace, setNamespace] = useState('cx360')
  const [owner, setOwner] = useState('cx360-import')
  const [preview, setPreview] = useState<BusinessMetricCsvImportResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) {
      setCsvText('')
      setFileName('')
      setNamespace('cx360')
      setOwner('cx360-import')
      setPreview(null)
      setError('')
      setBusy(false)
    }
  }, [open])

  const readFile = (file: File | undefined) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      setCsvText(String(reader.result ?? ''))
      setFileName(file.name)
      setPreview(null)
      setError('')
    }
    reader.onerror = () => setError(t('import.read_error'))
    reader.readAsText(file, 'UTF-8')
  }

  const dryRun = async () => {
    if (!csvText.trim()) {
      setError(t('import.missing_file'))
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await api.businessMetrics.importCsv({ csv_text: csvText, namespace, owner, dry_run: true })
      setPreview(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const commit = async () => {
    if (!csvText.trim()) {
      setError(t('import.missing_file'))
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = await api.businessMetrics.importCsv({ csv_text: csvText, namespace, owner, dry_run: false })
      onImported(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={t('import.title')} maxWidth="max-w-2xl">
      <div className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{t('import.namespace')}</span>
            <input
              value={namespace}
              onChange={(e) => {
                setNamespace(e.target.value)
                setPreview(null)
              }}
              className="mt-1 w-full h-10 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-sm outline-none focus:border-brand"
            />
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{t('import.owner')}</span>
            <input
              value={owner}
              onChange={(e) => {
                setOwner(e.target.value)
                setPreview(null)
              }}
              className="mt-1 w-full h-10 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-sm outline-none focus:border-brand"
            />
          </label>
        </div>

        <label className="block rounded-lg border border-dashed border-[var(--border-default)] bg-[var(--bg-secondary)] px-4 py-5 text-center cursor-pointer hover:border-brand transition-colors">
          <Upload size={20} className="mx-auto text-[var(--text-tertiary)]" />
          <span className="mt-2 block text-sm font-medium text-[var(--text-primary)]">
            {fileName || t('import.choose_file')}
          </span>
          <input
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(e) => readFile(e.target.files?.[0])}
          />
        </label>

        {error && <Alert severity="danger" message={error} />}

        {preview && (
          <div className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] p-3 text-sm">
            <div className="font-medium">{t('import.preview')}</div>
            <div className="mt-1 text-[var(--text-secondary)]">
              {t('import.result', {
                total: preview.total,
                created: preview.created,
                updated: preview.updated,
                skipped: preview.skipped,
              })}
            </div>
            {preview.errors.length > 0 && (
              <div className="mt-3 max-h-36 overflow-auto text-xs text-[var(--danger)]">
                {preview.errors.slice(0, 8).map((item) => (
                  <div key={`${item.row}-${item.metric_name}`}>{t('import.error_row', { row: item.row, error: item.error })}</div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="h-10 px-4 rounded-lg border border-[var(--border-default)] text-sm font-medium hover:bg-[var(--bg-secondary)] transition-colors"
          >
            {t('actions.cancel', { ns: 'common' })}
          </button>
          <button
            type="button"
            onClick={dryRun}
            disabled={busy}
            className="h-10 px-4 rounded-lg border border-[var(--border-default)] text-sm font-medium hover:bg-[var(--bg-secondary)] transition-colors disabled:opacity-50"
          >
            {busy ? t('import.working') : t('import.validate')}
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={busy || !preview}
            className="h-10 px-4 rounded-lg bg-brand text-white text-sm font-medium hover:brightness-110 transition disabled:opacity-50"
          >
            {busy ? t('import.working') : t('import.import')}
          </button>
        </div>
      </div>
    </Modal>
  )
}
