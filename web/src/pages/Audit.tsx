import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { api, invalidateCache, timeAgo } from '../api'
import { Badge } from '../components/Badge'
import { Skeleton } from '../components/Skeleton'

const TYPE_COLORS: Record<string, string> = {
  doc: 'info',
  hints: 'warning',
  tags: 'success',
  definition: 'critical',
  metadata: 'default',
}

export function Audit() {
  const navigate = useNavigate()
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(7)
  const [typeFilter, setTypeFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/versions')
    api.versions.recent(100, days)
      .then(setVersions)
      .catch(() => setVersions([]))
      .finally(() => setLoading(false))
  }, [days])

  useEffect(() => { load() }, [load])

  // Auto-refresh every 60s
  useEffect(() => {
    const interval = setInterval(load, 60_000)
    return () => clearInterval(interval)
  }, [load])

  const users = [...new Set(versions.map(v => v.changed_by as string).filter(Boolean))].sort()

  const filtered = versions.filter(v => {
    if (typeFilter && v.change_type !== typeFilter) return false
    if (userFilter && v.changed_by !== userFilter) return false
    return true
  })

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-xl font-semibold">Audit Log</h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-0.5">All metadata changes across the catalog</p>
        </div>
        <button onClick={load} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <select value={days} onChange={e => setDays(Number(e.target.value))}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={365}>All time</option>
        </select>
        <select value={userFilter} onChange={e => setUserFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">All users</option>
          {users.map(u => <option key={u} value={u}>{u}</option>)}
        </select>
        <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">All types</option>
          <option value="doc">Documentation</option>
          <option value="hints">Hints</option>
          <option value="definition">Definition</option>
          <option value="tags">Tags</option>
          <option value="metadata">Metadata</option>
        </select>
        <span className="text-xs text-[var(--text-tertiary)]">{filtered.length} changes</span>
      </div>

      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-5"><Skeleton className="h-48" /></div>
        ) : filtered.length === 0 ? (
          <p className="p-8 text-center text-[var(--text-tertiary)] text-sm">No changes recorded in this period</p>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)] bg-[var(--bg-secondary)]">
                <th className="text-left py-2 px-3 font-medium">When</th>
                <th className="text-left py-2 px-3 font-medium">Feature</th>
                <th className="text-left py-2 px-3 font-medium">Changed by</th>
                <th className="text-left py-2 px-3 font-medium">Type</th>
                <th className="text-left py-2 px-3 font-medium">Summary</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((v, i) => (
                <tr
                  key={i}
                  className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-secondary)] cursor-pointer"
                  onClick={() => navigate(`/features/${encodeURIComponent(v.feature_name as string)}`)}
                >
                  <td className="py-2 px-3 text-[var(--text-tertiary)] whitespace-nowrap">
                    {v.created_at ? timeAgo(v.created_at as string) : '-'}
                  </td>
                  <td className="py-2 px-3 font-medium text-accent">{v.feature_name as string || '-'}</td>
                  <td className="py-2 px-3 text-[var(--text-secondary)]">{v.changed_by as string || '-'}</td>
                  <td className="py-2 px-3">
                    <Badge variant={TYPE_COLORS[v.change_type as string] || 'default'}>
                      {v.change_type as string}
                    </Badge>
                  </td>
                  <td className="py-2 px-3 text-[var(--text-secondary)] max-w-[300px] truncate">
                    {v.change_summary as string}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
