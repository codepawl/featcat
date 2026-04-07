import { useEffect, useState } from 'react'
import { Layers, FileText, AlertTriangle, HardDrive } from 'lucide-react'
import { api, timeAgo } from '../api'
import { MetricCard } from '../components/MetricCard'
import { Badge } from '../components/Badge'
import { Skeleton } from '../components/Skeleton'

export function Dashboard() {
  const [stats, setStats] = useState<any>(null)
  const [monitor, setMonitor] = useState<any>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([
      api.stats().catch(() => null),
      api.monitor.check().catch(() => null),
      api.jobs.logs({ limit: '10' }).catch(() => []),
      api.jobs.list().catch(() => []),
    ])
      .then(([s, m, l, j]) => {
        setStats(s)
        setMonitor(m)
        setLogs(Array.isArray(l) ? l : [])
        setJobs(Array.isArray(j) ? j : [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 30000)
    return () => clearInterval(timer)
  }, [])

  if (error) {
    return (
      <div className="text-center py-20">
        <p className="text-red-500 mb-4">Cannot connect to server</p>
        <button onClick={load} className="px-4 py-2 bg-accent text-white rounded-lg text-sm">Retry</button>
      </div>
    )
  }

  // Stats API returns "features" or "total_features" depending on context
  const featureCount = stats?.total_features ?? stats?.features ?? 0
  const sourceCount = stats?.sources ?? 0
  const coverage = stats?.coverage ?? 0

  // Monitor: checked=0 means no baselines
  const alerts = monitor?.details?.filter((d: any) => d.severity !== 'healthy') || []
  const alertCount = (monitor?.warnings || 0) + (monitor?.critical || 0)
  const noBaselines = monitor && monitor.checked === 0

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-semibold">Dashboard</h1>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)
        ) : (
          <>
            <MetricCard label="Features" value={featureCount} icon={Layers} />
            <MetricCard label="Doc Coverage" value={`${Math.round(coverage)}%`} progress={coverage} icon={FileText} />
            <MetricCard label="Drift Alerts" value={noBaselines ? '-' : alertCount} color={noBaselines ? 'default' : alertCount > 0 ? (monitor?.critical > 0 ? 'danger' : 'warning') : 'success'} icon={AlertTriangle} />
            <MetricCard label="Sources" value={sourceCount} icon={HardDrive} />
          </>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-5 mb-6">
        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3">Recent Drift Alerts</h3>
          {loading ? <Skeleton className="h-24" /> : noBaselines ? (
            <p className="text-[var(--text-tertiary)] text-sm">No baselines computed yet. Run baseline first.</p>
          ) : alerts.length === 0 ? (
            <p className="text-[var(--text-tertiary)] text-sm">All features healthy</p>
          ) : (
            <table className="w-full text-[13px]">
              <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                <th className="text-left py-1 font-medium">Severity</th>
                <th className="text-left py-1 font-medium">Feature</th>
                <th className="text-right py-1 font-medium">PSI</th>
              </tr></thead>
              <tbody>
                {alerts.slice(0, 5).map((a: any, i: number) => (
                  <tr key={i} className="border-b border-[var(--border-subtle)]">
                    <td className="py-1.5"><Badge variant={a.severity}>{a.severity}</Badge></td>
                    <td className="py-1.5 font-medium">{a.feature}</td>
                    <td className="py-1.5 text-right font-mono">{a.psi != null ? a.psi.toFixed(4) : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3">Recent Activity</h3>
          {loading ? <Skeleton className="h-24" /> : logs.length === 0 ? (
            <p className="text-[var(--text-tertiary)] text-sm">No recent activity</p>
          ) : (
            <div className="space-y-2">
              {logs.slice(0, 5).map((l: any, i: number) => (
                <div key={i} className="flex items-center gap-2 text-[13px]">
                  <Badge variant={l.status}>{l.status}</Badge>
                  <span className="font-medium">{l.job_name}</span>
                  <span className="ml-auto text-[var(--text-tertiary)] text-xs">{timeAgo(l.started_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
        <h3 className="text-sm font-semibold mb-3">Scheduled Jobs</h3>
        {loading ? <Skeleton className="h-24" /> : jobs.length === 0 ? (
          <p className="text-[var(--text-tertiary)] text-sm">No jobs configured</p>
        ) : (
          <table className="w-full text-[13px]">
            <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
              <th className="text-left py-1 font-medium">Job</th>
              <th className="text-left py-1 font-medium">Schedule</th>
              <th className="text-left py-1 font-medium">Status</th>
              <th className="text-left py-1 font-medium">Last Run</th>
            </tr></thead>
            <tbody>
              {jobs.map((j: any, i: number) => (
                <tr key={i} className="border-b border-[var(--border-subtle)]">
                  <td className="py-2 font-medium">{j.job_name}</td>
                  <td className="py-2 font-mono text-xs text-[var(--text-secondary)]">{j.cron_expression}</td>
                  <td className="py-2"><Badge variant={j.enabled ? 'success' : 'warning'}>{j.enabled ? 'Enabled' : 'Disabled'}</Badge></td>
                  <td className="py-2 text-[var(--text-secondary)]">{timeAgo(j.last_run_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
