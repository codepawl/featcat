import { useEffect, useMemo, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle2, XCircle, Clock, RefreshCw, AlertTriangle, MessageSquare } from 'lucide-react'
import { api, invalidateCache, timeAgo, type ActionItem } from '../api'
import { Skeleton } from '../components/Skeleton'
import { Modal } from '../components/Modal'

const STATUS_OPTIONS = [
  { value: 'pending', label: 'Pending' },
  { value: 'applied', label: 'Applied' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'snoozed', label: 'Snoozed' },
  { value: 'all', label: 'All' },
]

const SOURCE_LABELS: Record<string, { label: string; icon: typeof AlertTriangle }> = {
  drift_alert: { label: 'Drift alert', icon: AlertTriangle },
  chat: { label: 'Chat', icon: MessageSquare },
  autodoc: { label: 'Auto-doc', icon: CheckCircle2 },
  manual: { label: 'Manual', icon: Clock },
}

export function Actions() {
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

  const sources = useMemo(() => {
    const seen = new Set(items.map((i) => i.source))
    return Array.from(seen)
  }, [items])

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

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-xl font-semibold">Action Items</h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-0.5">
            Recommendations from monitoring, AI, and manual entries — close the loop by applying or dismissing.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]"
        >
          <option value="">All sources</option>
          {Object.keys(SOURCE_LABELS).map((s) => (
            <option key={s} value={s}>
              {SOURCE_LABELS[s].label}
            </option>
          ))}
        </select>
        <span className="text-[12px] text-[var(--text-tertiary)] ml-auto">
          {items.length} item{items.length === 1 ? '' : 's'}
        </span>
      </div>

      {loading ? (
        <Skeleton className="h-40" />
      ) : items.length === 0 ? (
        <div className="border border-dashed border-[var(--border-default)] rounded-2xl p-12 text-center">
          <p className="text-sm text-[var(--text-tertiary)]">No action items match these filters.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {items.map((it) => {
            const meta = SOURCE_LABELS[it.source] ?? SOURCE_LABELS.manual
            const Icon = meta.icon
            const isPending = it.status === 'pending'
            return (
              <div
                key={it.id}
                className="border border-[var(--border-subtle)] rounded-2xl p-4 bg-[var(--bg-primary)] hover:border-[var(--border-default)] transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-[12px] text-[var(--text-tertiary)] mb-1">
                      <Icon size={12} />
                      <span>{meta.label}</span>
                      <span>·</span>
                      <button
                        className="font-mono text-accent hover:underline truncate"
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
                    {it.status !== 'pending' && (
                      <p className="text-[11px] text-[var(--text-tertiary)] mt-2">
                        {it.status === 'applied'
                          ? `Applied ${it.applied_at ? timeAgo(it.applied_at) : ''}${it.applied_by ? ` by ${it.applied_by}` : ''}`
                          : `${it.status[0].toUpperCase()}${it.status.slice(1)}${it.change_summary ? `: ${it.change_summary}` : ''}`}
                      </p>
                    )}
                  </div>
                  {isPending && (
                    <div className="flex gap-2 shrink-0">
                      <button
                        onClick={() => setConfirm({ item: it, mode: 'applied' })}
                        className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium border border-green-500/40 text-green-700 dark:text-green-400 rounded-lg hover:bg-green-500/10"
                      >
                        <CheckCircle2 size={12} /> Apply
                      </button>
                      <button
                        onClick={() => setConfirm({ item: it, mode: 'dismissed' })}
                        className="flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]"
                      >
                        <XCircle size={12} /> Dismiss
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
        title={confirm?.mode === 'applied' ? 'Apply action' : 'Dismiss action'}
        actions={
          <>
            <button
              onClick={() => {
                setConfirm(null)
                setSummary('')
              }}
              className="px-4 py-2 text-[13px] font-medium border border-[var(--border-default)] rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={applyMutation}
              disabled={busy}
              className="px-4 py-2 text-[13px] font-medium bg-accent text-[var(--bg-primary)] rounded-lg disabled:opacity-50"
            >
              {busy ? 'Saving…' : 'Confirm'}
            </button>
          </>
        }
      >
        {confirm && (
          <div className="space-y-3">
            <div className="text-[13px]">
              <span className="text-[var(--text-tertiary)]">Feature:</span>{' '}
              <span className="font-mono text-accent">{confirm.item.feature_name}</span>
            </div>
            <div className="text-[13px]">
              <span className="text-[var(--text-tertiary)]">Title:</span> {confirm.item.title}
            </div>
            <label className="block text-[12px] font-medium text-[var(--text-secondary)]">
              {confirm.mode === 'applied' ? 'Change summary (what did you do?)' : 'Reason'}
              <textarea
                rows={3}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                placeholder={
                  confirm.mode === 'applied'
                    ? 'e.g. updated transformation in dbt model X, re-baselined the feature'
                    : 'e.g. expected drift due to seasonality'
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
