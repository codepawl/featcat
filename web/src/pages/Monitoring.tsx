import { useEffect, useState } from 'react'
import { api } from '../api'
import { MetricCard } from '../components/MetricCard'
import { Badge } from '../components/Badge'
import { Modal } from '../components/Modal'
import { Skeleton } from '../components/Skeleton'

export function Monitoring() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [checking, setChecking] = useState(false)
  const [baselineModal, setBaselineModal] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)

  const load = () => {
    setLoading(true)
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
    try {
      const d = await api.monitor.check()
      setData(d)
    } catch { /* ignore */ }
    setChecking(false)
  }

  const confirmBaseline = async () => {
    try {
      await api.monitor.baseline()
      setBaselineModal(false)
      load()
    } catch { /* ignore */ }
  }

  const exportReport = async () => {
    try {
      const report = await api.monitor.report()
      const lines = [
        '# Feature Quality Report', '',
        `Total: ${report.total_features}, Checked: ${report.checked}`,
        `Healthy: ${report.healthy}, Warnings: ${report.warnings}, Critical: ${report.critical}`, '',
        '| Feature | Severity | PSI |', '|---------|----------|-----|',
        ...(report.details || []).map((d: any) => `| ${d.feature} | ${d.severity} | ${d.psi?.toFixed(4) ?? '-'} |`),
      ]
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'monitoring-report.md'; a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }

  const details = data?.details || []
  const sorted = [...details].sort((a: any, b: any) => {
    const order: Record<string, number> = { critical: 0, error: 0, warning: 1, healthy: 2 }
    return (order[a.severity] ?? 3) - (order[b.severity] ?? 3)
  })

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-semibold">Monitoring</h1>
        <span className="text-xs text-[var(--text-tertiary)]">{data?.timestamp ? new Date(data.timestamp).toLocaleString() : ''}</span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)
        ) : (
          <>
            <MetricCard label="Healthy" value={data?.healthy ?? 0} color="success" />
            <MetricCard label="Warnings" value={data?.warnings ?? 0} color={data?.warnings > 0 ? 'warning' : 'default'} />
            <MetricCard label="Critical" value={data?.critical ?? 0} color={data?.critical > 0 ? 'danger' : 'default'} />
            <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg p-4 flex items-center justify-center">
              <button onClick={runCheck} disabled={checking} className="px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium disabled:opacity-50">
                {checking ? 'Checking...' : 'Run Check Now'}
              </button>
            </div>
          </>
        )}
      </div>

      {/* Feature Drift Table */}
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-6">
        <h3 className="text-sm font-semibold mb-3">Feature Drift Status</h3>
        {loading ? <Skeleton className="h-32" /> : sorted.length === 0 ? (
          <p className="text-[var(--text-tertiary)] text-sm py-4 text-center">No drift data. Run baseline first, then check.</p>
        ) : (
          <table className="w-full text-[13px]">
            <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
              <th className="text-left py-2 font-medium">Feature</th>
              <th className="text-left py-2 font-medium">Severity</th>
              <th className="text-left py-2 font-medium">Issue</th>
              <th className="text-right py-2 font-medium">PSI</th>
            </tr></thead>
            <tbody>
              {sorted.map((d: any, i: number) => (
                <tr key={i}
                  className="border-b border-[var(--border-subtle)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors"
                  onClick={() => setExpanded(expanded === i ? null : i)}
                >
                  <td className="py-2 font-medium">{d.feature}</td>
                  <td className="py-2"><Badge variant={d.severity}>{d.severity}</Badge></td>
                  <td className="py-2 text-[var(--text-secondary)]">{d.issues?.[0]?.message || '-'}</td>
                  <td className="py-2 text-right font-mono">{d.psi != null ? d.psi.toFixed(4) : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {expanded !== null && sorted[expanded] && (
          <div className="mt-3 p-3 bg-[var(--bg-secondary)] rounded-lg text-xs animate-fade-in">
            <p className="font-medium mb-1">{sorted[expanded].feature} — Details</p>
            {(sorted[expanded].issues || []).map((iss: any, j: number) => (
              <p key={j} className="text-[var(--text-secondary)]">&bull; {iss.message}</p>
            ))}
            {sorted[expanded].llm_analysis && (
              <p className="mt-2 text-[var(--text-secondary)]">AI: {sorted[expanded].llm_analysis.likely_cause}</p>
            )}
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button onClick={() => setBaselineModal(true)} className="px-4 py-2 text-[13px] border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)]">
          Refresh Baseline
        </button>
        <button onClick={exportReport} className="px-4 py-2 text-[13px] border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)]">
          Export Report
        </button>
      </div>

      <Modal open={baselineModal} onClose={() => setBaselineModal(false)} title="Refresh Baseline" actions={
        <>
          <button onClick={() => setBaselineModal(false)} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">Cancel</button>
          <button onClick={confirmBaseline} className="px-4 py-2 text-sm bg-accent text-white rounded-lg">Confirm</button>
        </>
      }>
        <p className="text-sm text-[var(--text-secondary)]">
          This will recompute baseline statistics for all features. Current drift alerts will be cleared until the next check.
        </p>
      </Modal>
    </div>
  )
}
