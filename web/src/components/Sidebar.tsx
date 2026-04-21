import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { LayoutDashboard, Database, Activity, Clock, MessageSquare, FolderKanban, GitBranch, History } from 'lucide-react'
import { api } from '../api'
import { ThemeToggle } from './ThemeToggle'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/features', label: 'Features', icon: Database },
  { to: '/groups', label: 'Groups', icon: FolderKanban },
  { to: '/similarity', label: 'Similarity', icon: GitBranch },
  { to: '/audit', label: 'Audit', icon: History },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/jobs', label: 'Jobs', icon: Clock },
  { to: '/chat', label: 'AI Chat', icon: MessageSquare },
]

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const [llm, setLlm] = useState<{ ok: boolean; model: string }>({ ok: false, model: 'checking...' })
  const [serverOk, setServerOk] = useState(false)

  useEffect(() => {
    api.health()
      .then((d) => {
        setServerOk(true)
        setLlm({ ok: !!d.llm, model: d.model || (d.llm ? 'connected' : 'offline') })
      })
      .catch(() => setServerOk(false))
  }, [])

  return (
    <nav className="w-[220px] shrink-0 sticky top-0 h-screen overflow-y-auto flex flex-col bg-[var(--bg-primary)] border-r border-[var(--border-subtle)] py-4">
      {/* Brand */}
      <div className="px-5 pb-6 pt-1">
        <span className="font-mono text-base font-bold tracking-tight">
          feat<span className="text-accent">cat</span>
        </span>
      </div>

      {/* Navigation */}
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === '/'}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-2.5 px-5 py-2.5 text-[13px] font-medium border-l-2 transition-colors no-underline ${
              isActive
                ? 'text-accent border-accent bg-accent-muted'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]'
            }`
          }
        >
          <n.icon size={16} strokeWidth={1.8} />
          {n.label}
        </NavLink>
      ))}

      {/* Footer */}
      <div className="mt-auto px-5 flex flex-col gap-3">
        <div className="border-t border-[var(--border-subtle)] pt-3 flex flex-col gap-2 text-xs text-[var(--text-tertiary)]">
          <div className="flex items-center gap-2">
            <span className={`size-1.5 rounded-full ${serverOk ? 'bg-[var(--success)]' : 'bg-[var(--border-default)]'}`} />
            Server
          </div>
          <div className="flex items-center gap-2 truncate">
            <span className={`size-1.5 rounded-full ${llm.ok ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`} />
            <span className="truncate">LLM: {llm.model}</span>
          </div>
        </div>
        <div className="border-t border-[var(--border-subtle)] pt-3 pb-1">
          <ThemeToggle />
        </div>
      </div>
    </nav>
  )
}
