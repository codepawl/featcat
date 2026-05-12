import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, XCircle, Clock, AlertTriangle, MessageSquare } from 'lucide-react'
import { api, invalidateCache, timeAgo, type ActionItem } from '../api'
import { FilterSelect } from '../components/filters'
import { Modal } from '../components/Modal'
import { PageHeader } from '../components/PageHeader'
import { RefreshButton } from '../components/RefreshButton'
import { Skeleton } from '../components/Skeleton'

const STATUS_KEYS = ['pending', 'applied', 'dismissed', 'snoozed', 'all'] as const

type ActionSource = 'drift_alert' | 'chat' | 'autodoc' | 'manual'
const SOURCE_KEYS: ActionSource[] = ['drift_alert', 'chat', 'autodoc', 'manual']
const SOURCE_ICONS: Record<ActionSource, typeof AlertTriangle> = {
  drift_alert: AlertTriangle,
  chat: MessageSquare,
  autodoc: CheckCircle2,
  manual: Clock,
}

export function Actions() {
  const { t } = useTranslation('actions')
  const navigate = useNavigate()
  const [items, setItems] = useState<ActionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState('pending')
  const [source, setSource] = useState('')
  const [confirm, setConfirm] = useState<{ item: ActionItem; mode: 'applied' | 'dismissed' } | null>(null)
  const [summary, setSummary] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/actions')
    api.actions
      .list({
        status: status === 'all' ? undefined : status,
        source: source || undefined,
        limit: 200,
      })
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [status, source])

  useEffect(() => {
    load()
  }, [load])

  async function applyMutation() {
    if (!confirm) return
    setBusy(true)
    try {
      await api.actions.update(confirm.item.id, {
        status: confirm.mode,
        change_summary: summary,
      })
      invalidateCache('/actions')
      setConfirm(null)
      setSummary('')
      load()
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(false)
    }
  }

  const itemsLabel = t('filters.items_count', { count: items.length, defaultValue: `${items.length} items` })

  const renderHistory = (it: ActionItem) => {
    if (it.status === 'pending') return null
    if (it.status === 'applied') {
      const when = it.applied_at ? timeAgo(it.applied_at) : ''
      const by = it.applied_by ? t('history.by_suffix', { user: it.applied_by }) : ''
      return t('history.applied', { when, by })
    }
    const summarySuffix = it.change_summary ? t('history.summary_suffix', { summary: it.change_summary }) : ''
    const statusKey = it.status as 'pending' | 'applied' | 'dismissed' | 'snoozed'
    const statusLabel = t(`filters.status.${statusKey}`)
    return t('history.other_status', { status: statusLabel, summary: summarySuffix })
  }

  return (
    <div>
      <PageHeader
        title={t('page.title')}
        subtitle={t('page.subtitle')}
        size="compact"
        actions={<RefreshButton onClick={load} loading={loading} label={t('actions_buttons.refresh')} />}
      />

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <FilterSelect
          ariaLabel={t('filters.status.all', { defaultValue: 'Status' })}
          value={status}
          onChange={setStatus}
          options={STATUS_KEYS.map((key) => ({ value: key, label: t(`filters.status.${key}`) }))}
        />
        <FilterSelect
          ariaLabel={t('filters.all_sources')}
          value={source}
          onChange={setSource}
          options={[
            { value: '', label: t('filters.all_sources') },
            ...SOURCE_KEYS.map((s) => ({ value: s, label: t(`sources.${s}`) })),
          ]}
        />
        <span className="text-[12px] text-[var(--text-tertiary)] ml-auto">{itemsLabel}</span>
      </div>

      {loading ? (
        <Skeleton className="h-40" />
      ) : items.length === 0 ? (
        <div className="border border-dashed border-[var(--border-default)] rounded-2xl p-12 text-center">
          <p className="text-sm text-[var(--text-tertiary)]">{t('empty')}</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {items.map((it) => {
            const sourceKey = (SOURCE_KEYS as string[]).includes(it.source) ? (it.source as ActionSource) : 'manual'
            const Icon = SOURCE_ICONS[sourceKey]
            const sourceLabel = t(`sources.${sourceKey}`)
            const isPending = it.status === 'pending'
            const historyText = renderHistory(it)
            return (
              <div
                key={it.id}
                className="border border-[var(--border-subtle)] rounded-2xl p-4 bg-[var(--bg-primary)] hover:border-[var(--border-default)] transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-[12px] text-[var(--text-tertiary)] mb-1">
                      <Icon size={12} />
                      <span>{sourceLabel}</span>
                      <span>·</span>
                      <button
                        className="font-mono text-brand hover:underline truncate"
                        onClick={() => navigate(`/features/${encodeURIComponent(it.feature_name)}`)}
                      >
                        {it.feature_name}
                      </button>
                      <span>·</span>
                      <span>{timeAgo(it.created_at)}</span>
                    </div>
                    <h3 className="text-sm font-semibold mb-1">{it.title}</h3>
                    <p className="text-[13px] text-[var(--text-secondary)] whitespace-pre-wrap">
                      {it.recommendation}
                    </p>
                    {historyText && (
                      <p className="text-[11px] text-[var(--text-tertiary)] mt-2">{historyText}</p>
                    )}
                  </div>
                  {isPending && (
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => setConfirm({ item: it, mode: 'applied' })}
                        className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium border border-green-500/40 text-green-700 dark:text-green-400 rounded-lg hover:bg-green-500/10"
                      >
                        <CheckCircle2 size={12} /> {t('actions_buttons.apply')}
                      </button>
                      <button
                        onClick={() => setConfirm({ item: it, mode: 'dismissed' })}
                        className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]"
                      >
                        <XCircle size={12} /> {t('actions_buttons.dismiss')}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <Modal
        open={!!confirm}
        onClose={() => {
          setConfirm(null)
          setSummary('')
        }}
        title={confirm?.mode === 'applied' ? t('modal.title_apply') : t('modal.title_dismiss')}
        actions={
          <>
            <button
              onClick={() => {
                setConfirm(null)
                setSummary('')
              }}
              className="px-4 py-2 text-[13px] font-medium border border-[var(--border-default)] rounded-lg"
            >
              {t('actions_buttons.cancel')}
            </button>
            <button
              onClick={applyMutation}
              disabled={busy}
              className="px-4 py-2 text-[13px] font-medium bg-brand text-[var(--bg-primary)] rounded-lg disabled:opacity-50"
            >
              {busy ? t('actions_buttons.saving') : t('actions_buttons.confirm')}
            </button>
          </>
        }
      >
        {confirm && (
          <div className="space-y-3">
            <div className="text-[13px]">
              <span className="text-[var(--text-tertiary)]">{t('modal.feature_label')}:</span>{' '}
              <span className="font-mono text-brand">{confirm.item.feature_name}</span>
            </div>
            <div className="text-[13px]">
              <span className="text-[var(--text-tertiary)]">{t('modal.title_label')}:</span> {confirm.item.title}
            </div>
            <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
              {confirm.mode === 'applied' ? t('modal.summary_label_apply') : t('modal.summary_label_dismiss')}
              <textarea
                rows={3}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder={
                  confirm.mode === 'applied'
                    ? t('modal.summary_placeholder_apply')
                    : t('modal.summary_placeholder_dismiss')
                }
                className="mt-1 w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-2 text-[13px]"
              />
            </label>
          </div>
        )}
      </Modal>
    </div>
  )
}
