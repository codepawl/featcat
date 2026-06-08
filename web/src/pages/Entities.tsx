import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { RefreshCw, ExternalLink } from 'lucide-react'
import { api, invalidateCache, type EntityDTO } from '../api'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { FilterClearLink } from '../components/filters'
import { PageHeader } from '../components/PageHeader'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

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
  const navigate = useNavigate()
  const { name } = useParams<{ name?: string }>()

  const [items, setItems] = useState<EntityDTO[]>([])
  const [detail, setDetail] = useState<EntityDTO | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [owner, setOwner] = useState('')

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

  return (
    <div>
      <PageHeader
        title={t('entities.page.title')}
        subtitle={t('entities.page.subtitle')}
        actions={
          <>
            <span className="text-xs text-[var(--text-tertiary)]">{t('entities.page.count', { count: items.length })}</span>
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
    </div>
  )
}
