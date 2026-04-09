import { useEffect, useState } from 'react'
import { Play, Timer, Loader2 } from 'lucide-react'
import { api, invalidateCache, timeAgo } from '../api'
import { Badge } from '../components/Badge'
import { Modal } from '../components/Modal'
import { Skeleton } from '../components/Skeleton'

function cronToHuman(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length < 5) return cron
  const [min, hr, dom, , dow] = parts
  if (min.startsWith('*/')) return `Every ${min.slice(2)} minutes`
  if (hr.startsWith('*/')) return `Every ${hr.slice(2)} hours`
  if (dow !== '*' && dom === '*') {
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    return `Weekly on ${days[+dow] || dow} at ${hr.padStart(2, '0')}:${min.padStart(2, '0')}`
  }
  if (dom === '*' && hr !== '*') return `Daily at ${hr.padStart(2, '0')}:${min.padStart(2, '0')}`
  return cron
}

export function Jobs() {
  const [jobs, setJobs] = useState<any[]>([])
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filterJob, setFilterJob] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [scheduleModal, setScheduleModal] = useState<any>(null)
  const [cronInput, setCronInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(0)
  const [runningJob, setRunningJob] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([api.jobs.list(), api.jobs.logs({ limit: '500' })])
      .then(([j, l]) => {
        setJobs(Array.isArray(j) ? j : [])
        setLogs(Array.isArray(l) ? l : [])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const runJob = async (name: string) => {
    if (runningJob) return
    if (!window.confirm(`Run "${name}" now? This may take 30-60 seconds.`)) return
    setRunningJob(name)
    try {
      await api.jobs.run(name)
      invalidateCache('/jobs')
      setTimeout(load, 2000)
    } catch { /* ignore */ } finally {
      setTimeout(() => setRunningJob(null), 2000)
    }
  }

  const toggleJob = async (name: string, enabled: boolean) => {
    try {
      await api.jobs.update(name, { enabled })
      invalidateCache('/jobs')
      load()
    } catch { /* ignore */ }
  }

  const saveSchedule = async () => {
    if (!scheduleModal || !cronInput) return
    setSaving(true)
    try {
      await api.jobs.update(scheduleModal.job_name, { cron_expression: cronInput })
      invalidateCache('/jobs')
      setScheduleModal(null)
      load()
    } catch { /* ignore */ }
    setSaving(false)
  }

  const filtered = logs.filter((l) => {
    if (filterJob && l.job_name !== filterJob) return false
    if (filterStatus && l.status !== filterStatus) return false
    return true
  })
  const PAGE_SIZE = 50
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-semibold">Jobs</h1>
      </div>

      {/* Job Cards */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {loading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32" />) :
          jobs.map((j) => (
            <div key={j.job_name} className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-4 hover:shadow-md transition-all">
              <div className="flex justify-between items-start mb-2">
                <span className="font-medium text-sm">{j.job_name}</span>
                <Badge variant={j.enabled ? 'success' : 'warning'}>{j.enabled ? 'Enabled' : 'Disabled'}</Badge>
              </div>
              <p className="text-xs text-[var(--text-secondary)] mb-2">{j.description || 'No description'}</p>
              <p className="flex items-center gap-1 text-xs text-[var(--text-tertiary)] font-mono mb-3">
                <Timer size={12} /> {cronToHuman(j.cron_expression)}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => toggleJob(j.job_name, !j.enabled)}
                  className="px-2.5 py-1 text-xs border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)]"
                >
                  {j.enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  onClick={() => runJob(j.job_name)}
                  disabled={runningJob === j.job_name}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs bg-accent text-white rounded-md disabled:opacity-50"
                >
                  {runningJob === j.job_name ? <><Loader2 size={12} className="animate-spin" /> Running...</> : <><Play size={12} /> Run Now</>}
                </button>
                <button
                  onClick={() => { setScheduleModal(j); setCronInput(j.cron_expression); }}
                  className="px-2.5 py-1 text-xs border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)]"
                >
                  Edit Schedule
                </button>
              </div>
            </div>
          ))}
      </div>

      {/* Execution History */}
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
        <div className="flex justify-between items-center mb-4 flex-wrap gap-2">
          <h3 className="text-sm font-semibold">Execution History</h3>
          <div className="flex gap-2">
            <select value={filterJob} onChange={(e) => { setFilterJob(e.target.value); setPage(0); }}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2.5 py-1.5 text-xs">
              <option value="">All Jobs</option>
              {jobs.map((j) => <option key={j.job_name} value={j.job_name}>{j.job_name}</option>)}
            </select>
            <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setPage(0); }}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2.5 py-1.5 text-xs">
              <option value="">All Statuses</option>
              {['success', 'failed', 'warning', 'running'].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </div>

        {loading ? <Skeleton className="h-40" /> : (
          <>
            <table className="w-full text-[13px]">
              <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                <th className="text-left py-2 font-medium">Job</th>
                <th className="text-left py-2 font-medium">Status</th>
                <th className="text-left py-2 font-medium">Started</th>
                <th className="text-left py-2 font-medium">Duration</th>
                <th className="text-left py-2 font-medium">Result</th>
                <th className="text-left py-2 font-medium">Triggered By</th>
              </tr></thead>
              <tbody>
                {paged.map((l, i) => (
                  <tr key={i}
                    className="border-b border-[var(--border-subtle)] cursor-pointer hover:bg-[var(--bg-secondary)] transition-colors"
                    onClick={() => setExpanded(expanded === i ? null : i)}
                  >
                    <td className="py-2 font-medium">{l.job_name}</td>
                    <td className="py-2"><Badge variant={l.status}>{l.status}</Badge></td>
                    <td className="py-2 text-[var(--text-secondary)]">{l.started_at ? new Date(l.started_at).toLocaleString() : '-'}</td>
                    <td className="py-2 font-mono text-xs">{l.duration_seconds != null ? `${l.duration_seconds.toFixed(1)}s` : '-'}</td>
                    <td className="py-2 text-xs text-[var(--text-secondary)] max-w-[200px] truncate">{typeof l.result_summary === 'string' ? l.result_summary : JSON.stringify(l.result_summary || '')}</td>
                    <td className="py-2 text-xs text-[var(--text-tertiary)]">{l.triggered_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {expanded !== null && paged[expanded] && (
              <div className="mt-3 p-3 bg-[var(--bg-secondary)] rounded-lg text-xs font-mono animate-fade-in whitespace-pre-wrap">
                {JSON.stringify(paged[expanded].result_summary, null, 2)}
                {paged[expanded].error_message && (
                  <p className="text-red-500 mt-2">{paged[expanded].error_message}</p>
                )}
              </div>
            )}

            {totalPages > 1 && (
              <div className="flex gap-1 justify-center mt-4">
                <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="px-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-40">Prev</button>
                <span className="px-3 py-1.5 text-xs text-[var(--text-secondary)]">{page + 1} / {totalPages}</span>
                <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)} className="px-3 py-1.5 text-xs rounded-md border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-40">Next</button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Schedule Modal */}
      <Modal open={!!scheduleModal} onClose={() => setScheduleModal(null)} title="Edit Schedule" actions={
        <>
          <button onClick={() => setScheduleModal(null)} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">Cancel</button>
          <button onClick={saveSchedule} disabled={saving || !cronInput} className="flex items-center gap-1.5 px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">
            {saving && <Loader2 size={14} className="animate-spin" />}
            {saving ? 'Saving...' : 'Save'}
          </button>
        </>
      }>
        <p className="text-xs text-[var(--text-secondary)] mb-3">{scheduleModal?.job_name}</p>
        <label className="block text-xs font-medium mb-1">Cron Expression</label>
        <input value={cronInput} onChange={(e) => setCronInput(e.target.value)} placeholder="0 * * * *"
          className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] font-mono focus:border-accent outline-none mb-2" />
        <p className="text-xs text-[var(--text-secondary)]">{cronToHuman(cronInput)}</p>
        <div className="flex gap-2 mt-3">
          {['0 * * * *', '0 */6 * * *', '0 2 * * *', '0 3 * * 0'].map((p) => (
            <button key={p} onClick={() => setCronInput(p)} className="px-2 py-1 text-[11px] border border-[var(--border-default)] rounded-md hover:bg-[var(--bg-secondary)]">{cronToHuman(p)}</button>
          ))}
        </div>
      </Modal>
    </div>
  )
}
