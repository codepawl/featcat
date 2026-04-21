import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { motion, AnimatePresence } from 'motion/react'
import { RefreshCw } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { MetricCard } from '../components/MetricCard'
import { Badge } from '../components/Badge'
import { Modal } from '../components/Modal'
import { Skeleton } from '../components/Skeleton'
import { PsiTimeline } from '../components/charts/PsiTimeline'
import { DistributionShift } from '../components/charts/DistributionShift'

export function Monitoring() {
  const { t } = useTranslation('monitoring')
  const navigate = useNavigate()
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [baselineModal, setBaselineModal] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    invalidateCache('/monitor')
    api.monitor.check()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const runCheck = async () => {
    setChecking(true)
    setError(null)
    try {
      const d = await api.monitor.check()
      const details = (d as Record<string, unknown>)?.details as unknown[] | undefined
      if (!details || details.length === 0) {
        setError(t('errors.no_drift_data'))
      }
      setData(d)
    } catch (e) {
      setError(e instanceof Error ? e.message : t('errors.check_failed'))
    }
    setChecking(false)
  }

  const confirmBaseline = async () => {
    setError(null)
    try {
      await api.monitor.baseline()
      invalidateCache('/monitor')
      setBaselineModal(false)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : t('errors.baseline_failed'))
      setBaselineModal(false)
    }
  }

  const exportReport = async () => {
    try {
      const report = await api.monitor.report() as Record<string, unknown>
      const reportDetails = (report.details || []) as MonitoringDetailItem[]
      const lines = [
        '# Feature Quality Report', '',
        `Total: ${report.total_features}, Checked: ${report.checked}`,
        `Healthy: ${report.healthy}, Warnings: ${report.warnings}, Critical: ${report.critical}`, '',
        '| Feature | Severity | PSI |', '|---------|----------|-----|',
        ...reportDetails.map(d => `| ${d.feature} | ${d.severity} | ${d.psi?.toFixed(4) ?? '-'} |`),
      ]
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'monitoring-report.md'; a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }

  const details: MonitoringDetailItem[] = (data as Record<string, unknown>)?.details as MonitoringDetailItem[] || []
  const sorted = [...details].sort((a, b) => {
    const order: Record<string, number> = { critical: 0, error: 0, warning: 1, healthy: 2 }
    return (order[a.severity] ?? 3) - (order[b.severity] ?? 3)
  })

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[var(--text-tertiary)]">{data?.timestamp ? new Date(data.timestamp as string).toLocaleString() : ''}</span>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {t('actions.refresh', { ns: 'common' })}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)
        ) : (
          <>
            <MetricCard label={t('stats.healthy')} value={(data?.healthy as number) ?? 0} color="success" />
            <MetricCard label={t('stats.warnings')} value={(data?.warnings as number) ?? 0} color={(data?.warnings as number) > 0 ? 'warning' : 'default'} />
            <MetricCard label={t('stats.critical')} value={(data?.critical as number) ?? 0} color={(data?.critical as number) > 0 ? 'danger' : 'default'} />
            <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg p-4 flex flex-col items-center justify-center gap-1.5">
              <button onClick={runCheck} disabled={checking} className="px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium disabled:opacity-50">
                {checking ? t('actions.checking') : t('actions.run_check_now')}
              </button>
              {sorted.length === 0 && !loading && (
                <p className="text-[10px] text-[var(--text-tertiary)] text-center">{t('hints.run_baseline_first')}</p>
              )}
            </div>
          </>
        )}
      </div>

      {error && (
        <div className="bg-[var(--danger-subtle-bg)] border border-[var(--danger-subtle-bg)] rounded-lg p-3 text-[var(--danger)] text-sm mb-4 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[var(--danger)] hover:opacity-80 ml-2 shrink-0">&times;</button>
        </div>
      )}

      {/* Feature Drift Table */}
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-6">
        <h3 className="text-sm font-semibold mb-3">{t('drift_table.title')}</h3>
        {loading ? <Skeleton className="h-32" /> : sorted.length === 0 ? (
          <p className="text-[var(--text-tertiary)] text-sm py-4 text-center">{t('drift_table.empty')}</p>
        ) : (
          <div className="flex gap-4">
            <div className={`min-w-0 ${selectedIdx !== null ? 'flex-1' : 'w-full'}`}>
              <table className="w-full text-[13px]">
                <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                  <th className="text-left py-2 font-medium">{t('drift_table.columns.feature')}</th>
                  <th className="text-left py-2 font-medium">{t('drift_table.columns.severity')}</th>
                  <th className="text-left py-2 font-medium">{t('drift_table.columns.issue')}</th>
                  <th className="text-right py-2 font-medium">{t('drift_table.columns.psi')}</th>
                </tr></thead>
                <tbody>
                  {sorted.map((d, i: number) => (
                    <tr key={i}
                      className={`border-b border-[var(--border-subtle)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors ${selectedIdx === i ? 'bg-[var(--bg-secondary)]' : ''}`}
                      onClick={() => setSelectedIdx(selectedIdx === i ? null : i)}
                    >
                      <td className="py-2 font-medium">{d.feature}</td>
                      <td className="py-2"><Badge variant={d.severity}>{d.severity}</Badge></td>
                      <td className="py-2 text-[var(--text-secondary)]">{d.issues?.[0]?.message || '-'}</td>
                      <td className="py-2 text-right font-mono">{d.psi != null ? d.psi.toFixed(4) : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <AnimatePresence>
              {selectedIdx !== null && sorted[selectedIdx] && (
                <motion.div
                  key="side-panel"
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: 320, opacity: 1 }}
                  exit={{ width: 0, opacity: 0 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                  className="shrink-0 overflow-hidden"
                >
                  <FeatureDetail item={sorted[selectedIdx]} onNavigate={() => navigate(`/features/${encodeURIComponent(sorted[selectedIdx].feature)}`)} onClose={() => setSelectedIdx(null)} t={t} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button onClick={() => setBaselineModal(true)} className="px-4 py-2 text-[13px] border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)]">
          {t('actions.refresh_baseline')}
        </button>
        <button onClick={exportReport} className="px-4 py-2 text-[13px] border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)]">
          {t('actions.export_report')}
        </button>
      </div>

      <Modal open={baselineModal} onClose={() => setBaselineModal(false)} title={t('baseline_modal.title')} actions={
        <>
          <button onClick={() => setBaselineModal(false)} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
          <button onClick={confirmBaseline} className="px-4 py-2 text-sm bg-accent text-white rounded-lg">{t('actions.confirm', { ns: 'common' })}</button>
        </>
      }>
        <p className="text-sm text-[var(--text-secondary)]">
          {t('baseline_modal.body')}
        </p>
      </Modal>
    </div>
  )
}

function psiLabel(psi: number | null | undefined, t: TFunction<'monitoring'>): string {
  if (psi == null) return t('psi_labels.no_data')
  if (psi < 0.1) return t('psi_labels.no_change')
  if (psi < 0.25) return t('psi_labels.moderate')
  return t('psi_labels.significant')
}

const STAT_ROWS: { key: string; label: string; fmt: (v: any) => string }[] = [
  { key: 'mean', label: 'Mean', fmt: (v) => (typeof v === 'number' ? v.toFixed(4) : '-') },
  { key: 'std', label: 'Std', fmt: (v) => (typeof v === 'number' ? v.toFixed(4) : '-') },
  { key: 'min', label: 'Min', fmt: (v) => (typeof v === 'number' ? v.toFixed(4) : '-') },
  { key: 'max', label: 'Max', fmt: (v) => (typeof v === 'number' ? v.toFixed(4) : '-') },
  { key: 'null_ratio', label: 'Null %', fmt: (v) => (typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '-') },
]

interface MonitoringDetailItem {
  feature: string
  severity: string
  psi: number | null
  issues: { issue: string; message: string }[]
  baseline_stats: Record<string, number>
  current_stats: Record<string, number>
  llm_analysis?: { likely_cause: string; recommended_actions?: string[] }
}

function FeatureDetail({ item, onNavigate, onClose, t }: { item: MonitoringDetailItem; onNavigate: () => void; onClose: () => void; t: TFunction<'monitoring'> }) {
  const [history, setHistory] = useState<{ checked_at: string; psi: number | null; severity: string }[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const [baselineData, setBaselineData] = useState<Record<string, number> | null>(null)
  const [baselineLoading, setBaselineLoading] = useState(true)

  useEffect(() => {
    setHistoryLoading(true)
    setBaselineLoading(true)
    api.monitor.history(item.feature, 30)
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false))
    api.monitor.baselineStats(item.feature)
      .then(r => setBaselineData(r.baseline_stats))
      .catch(() => setBaselineData(null))
      .finally(() => setBaselineLoading(false))
  }, [item.feature])

  return (
    <div className="bg-[var(--bg-secondary)] rounded-lg p-4 text-xs h-full overflow-y-auto border border-[var(--border-subtle)]">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-semibold text-sm truncate mr-2">{item.feature}</h4>
        <button onClick={onClose} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] shrink-0 p-0.5">✕</button>
      </div>
      <div className="flex items-center gap-2 mb-3">
        <Badge variant={item.severity}>{item.severity}</Badge>
        {item.psi != null && (
          <span className="font-mono">PSI: {item.psi.toFixed(4)}</span>
        )}
        <span className="text-[var(--text-tertiary)]">{psiLabel(item.psi, t)}</span>
      </div>

      {/* PSI Timeline Chart */}
      <PsiTimeline data={history} loading={historyLoading} />

      {/* Distribution Shift Comparison */}
      <DistributionShift
        baselineStats={baselineData || item.baseline_stats}
        currentStats={item.current_stats}
        loading={baselineLoading}
      />

      {(item.issues?.length > 0) && (
        <div className="mb-2">
          <p className="font-medium mb-1">{t('detail.issues')}</p>
          {item.issues.map((iss, j: number) => (
            <p key={j} className="text-[var(--text-secondary)]">&bull; {iss.message}</p>
          ))}
        </div>
      )}

      {item.llm_analysis && (
        <div className="border-t border-[var(--border-subtle)] pt-2 mt-2 mb-2">
          <p className="font-medium">{t('detail.ai_analysis')}</p>
          <p className="text-[var(--text-secondary)]">{t('detail.likely_cause')}: {item.llm_analysis.likely_cause}</p>
          {item.llm_analysis.recommended_actions && item.llm_analysis.recommended_actions.length > 0 && (
            <ul className="list-disc list-inside text-[var(--text-secondary)] mt-1">
              {item.llm_analysis.recommended_actions.map((a: string, i: number) => <li key={i}>{a}</li>)}
            </ul>
          )}
        </div>
      )}

      <button onClick={onNavigate} className="text-accent hover:underline text-xs font-medium mt-1">{t('detail.view_feature')}</button>
    </div>
  )
}
