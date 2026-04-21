import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, FileText, AlertTriangle, HardDrive, RefreshCw, HeartPulse } from 'lucide-react'
import { api, invalidateCache, timeAgo } from '../api'
import { MetricCard } from '../components/MetricCard'
import { Badge } from '../components/Badge'
import { Skeleton } from '../components/Skeleton'
import { DocDebtHeatmap } from '../components/charts/DocDebtHeatmap'
import { DataSourceNodes } from '../components/charts/DataSourceNodes'

export function Dashboard() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [healthSummary, setHealthSummary] = useState<{ grade_distribution: Record<string, number>; average_score: number; lowest_scored: { spec: string; score: number; grade: string }[] } | null>(null)
  const [monitor, setMonitor] = useState<Record<string, unknown> | null>(null)
  const [logs, setLogs] = useState<Record<string, unknown>[]>([])
  const [jobs, setJobs] = useState<Record<string, unknown>[]>([])
  const [topFeatures, setTopFeatures] = useState<{ name: string; view_count: number; query_count: number; total_count: number; last_seen: string; created_at: string; source: string }[]>([])
  const [orphaned, setOrphaned] = useState<{ name: string; last_seen: string | null }[]>([])
  const [docDebt, setDocDebt] = useState<{ owner: string; source: string; total: number; undocumented: number; pct_undocumented: number }[]>([])
  const [sourceStats, setSourceStats] = useState<{ source_name: string; path: string; feature_count: number; documented_count: number; drift_alerts: number; critical_alerts: number; last_scanned: string | null; top_drifting_feature: string | null }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    invalidateCache()
    Promise.all([
      api.stats().catch(() => null),
      api.monitor.check().catch(() => null),
      api.jobs.logs({ limit: '10' }).catch(() => []),
      api.jobs.list().catch(() => []),
      api.usage.top(50, 30).catch(() => []),
      api.usage.orphaned(30).catch(() => []),
      api.docDebt().catch(() => []),
      api.statsBySource().catch(() => []),
      api.features.healthSummary().catch(() => null),
    ])
      .then(([s, m, l, j, tf, o, dd, ss, hs]) => {
        setStats(s)
        setMonitor(m)
        setLogs(Array.isArray(l) ? l : [])
        setJobs(Array.isArray(j) ? j : [])
        setTopFeatures(Array.isArray(tf) ? tf : [])
        setOrphaned(Array.isArray(o) ? o : [])
        setDocDebt(Array.isArray(dd) ? dd : [])
        setSourceStats(Array.isArray(ss) ? ss : [])
        setHealthSummary(hs)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
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
  const monitorDetails = (monitor?.details || []) as { severity: string; feature: string; psi: number | null }[]
  const alerts = monitorDetails.filter(d => d.severity !== 'healthy')
  const alertCount = ((monitor?.warnings as number) || 0) + ((monitor?.critical as number) || 0)
  const noBaselines = monitor && monitor.checked === 0

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <button onClick={load} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Section 1: Catalog Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)
        ) : (
          <>
            <MetricCard label="Features" value={featureCount} icon={Layers} />
            <MetricCard label="Doc Coverage" value={`${Math.round(coverage)}%`} progress={coverage} icon={FileText} />
            <MetricCard label="Drift Alerts" value={noBaselines ? '-' : alertCount} color={noBaselines ? 'default' : alertCount > 0 ? ((monitor?.critical as number) > 0 ? 'danger' : 'warning') : 'success'} icon={AlertTriangle} />
            <MetricCard label="Sources" value={sourceCount} icon={HardDrive} />
          </>
        )}
      </div>

      {/* Section 2: Data Sources */}
      <hr className="border-[var(--border-subtle)] mt-8" />
      <div className="mt-8 mb-4">
        <DataSourceNodes data={sourceStats} loading={loading} />
      </div>

      {/* Section 3: Quality & Debt */}
      <hr className="border-[var(--border-subtle)] mt-8" />
      <div className="mt-8 mb-4">
        <h2 className="text-lg font-semibold">Quality & Debt</h2>
        <p className="text-sm text-[var(--text-tertiary)] mt-0.5">Documentation coverage and drift alerts across your catalog</p>
      </div>

      {/* Health Summary Card */}
      {!loading && healthSummary && (
        <div
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5 mb-4 cursor-pointer hover:border-[var(--border-muted)] transition-colors"
          onClick={() => navigate('/features?sort=health&order=asc')}
        >
          <div className="flex items-center gap-2 mb-3">
            <HeartPulse size={16} className="text-accent" />
            <h3 className="text-sm font-semibold">Catalog Health</h3>
            <span className="ml-auto text-2xl font-semibold">{healthSummary.average_score}<span className="text-sm font-normal text-[var(--text-tertiary)]">/100</span></span>
          </div>
          <div className="flex items-center gap-1 h-4 rounded-full overflow-hidden mb-2">
            {(['A', 'B', 'C', 'D'] as const).map(g => {
              const count = healthSummary.grade_distribution[g] || 0
              const total = Object.values(healthSummary.grade_distribution).reduce((a, b) => a + b, 0)
              const pct = total > 0 ? (count / total) * 100 : 0
              if (pct === 0) return null
              const bg = { A: 'bg-green-500', B: 'bg-teal-500', C: 'bg-amber-500', D: 'bg-red-500' }[g]
              return <div key={g} className={`h-full ${bg}`} style={{ width: `${pct}%` }} />
            })}
          </div>
          <div className="flex gap-4 text-xs text-[var(--text-secondary)]">
            {(['A', 'B', 'C', 'D'] as const).map(g => {
              const count = healthSummary.grade_distribution[g] || 0
              const color = { A: 'text-green-500', B: 'text-teal-500', C: 'text-amber-500', D: 'text-red-500' }[g]
              return <span key={g} className="flex items-center gap-1"><span className={`font-bold ${color}`}>{g}</span> {count}</span>
            })}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 mb-6">
        <DocDebtHeatmap data={docDebt} loading={loading} />
        <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
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
                {alerts.slice(0, 5).map((a, i) => (
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
      </div>

      {/* Section 4: Activity & Usage */}
      <hr className="border-[var(--border-subtle)] mt-8" />
      <div className="mt-8 mb-4">
        <h2 className="text-lg font-semibold">Activity & Usage</h2>
        <p className="text-sm text-[var(--text-tertiary)] mt-0.5">Recent catalog activity and feature adoption</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
          <h3 className="text-sm font-semibold mb-3">Top Features</h3>
          {loading ? <Skeleton className="h-24" /> : topFeatures.length === 0 ? (
            <p className="text-[var(--text-tertiary)] text-sm">No usage data yet</p>
          ) : (
            <table className="w-full text-[13px]">
              <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                <th className="text-left py-1 font-medium">#</th>
                <th className="text-left py-1 font-medium">Feature</th>
                <th className="text-right py-1 font-medium">Views</th>
                <th className="text-right py-1 font-medium">Queries</th>
              </tr></thead>
              <tbody>
                {topFeatures.slice(0, 5).map((f, i) => (
                  <tr key={i} className="border-b border-[var(--border-subtle)]">
                    <td className="py-1.5 text-[var(--text-tertiary)]">{i + 1}</td>
                    <td className="py-1.5 font-medium">{f.name}</td>
                    <td className="py-1.5 text-right font-mono">{f.view_count}</td>
                    <td className="py-1.5 text-right font-mono">{f.query_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
          <h3 className="text-sm font-semibold mb-3">Orphaned Features</h3>
          {loading ? <Skeleton className="h-24" /> : orphaned.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
              All features active in the last 30 days
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle size={16} className="text-amber-500" />
                <span className="text-sm font-medium">{orphaned.length} feature{orphaned.length !== 1 ? 's' : ''} with no recent usage</span>
              </div>
              <div className="space-y-1">
                {orphaned.slice(0, 5).map((f, i) => (
                  <div key={i} className="text-[13px] text-[var(--text-secondary)]">{f.name}</div>
                ))}
                {orphaned.length > 5 && (
                  <a href="/features" className="text-xs text-accent hover:underline">View all features →</a>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
          <h3 className="text-sm font-semibold mb-3">Recent Activity</h3>
          {loading ? <Skeleton className="h-24" /> : logs.length === 0 ? (
            <p className="text-[var(--text-tertiary)] text-sm">No recent activity</p>
          ) : (
            <div className="space-y-2">
              {logs.slice(0, 5).map((l, i) => (
                <div key={i} className="flex items-center gap-2 text-[13px]">
                  <Badge variant={l.status as string}>{l.status as string}</Badge>
                  <span className="font-medium">{l.job_name as string}</span>
                  <span className="ml-auto text-[var(--text-tertiary)] text-xs">{timeAgo(l.started_at as string)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Section 5: System */}
      <hr className="border-[var(--border-subtle)] mt-8" />
      <div className="mt-8 mb-4">
        <h2 className="text-lg font-semibold">System</h2>
        <p className="text-sm text-[var(--text-tertiary)] mt-0.5">Scheduled background jobs</p>
      </div>
      <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
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
              {jobs.map((j, i) => (
                <tr key={i} className="border-b border-[var(--border-subtle)]">
                  <td className="py-2 font-medium">{j.job_name as string}</td>
                  <td className="py-2 font-mono text-xs text-[var(--text-secondary)]">{j.cron_expression as string}</td>
                  <td className="py-2"><Badge variant={j.enabled ? 'success' : 'warning'}>{j.enabled ? 'Enabled' : 'Disabled'}</Badge></td>
                  <td className="py-2 text-[var(--text-secondary)]">{timeAgo(j.last_run_at as string)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
