import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { LayoutDashboard, Database, Activity, Clock, MessageSquare, Server, Cpu } from 'lucide-react'
import { api } from '../api'
import { ThemeToggle } from './ThemeToggle'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/features', label: 'Features', icon: Database },
  { to: '/monitoring', label: 'Monitoring', icon: Activity },
  { to: '/jobs', label: 'Jobs', icon: Clock },
  { to: '/chat', label: 'AI Chat', icon: MessageSquare },
]

export function Sidebar() {
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
    <nav className="w-[220px] shrink-0 sticky top-0 h-screen overflow-y-auto flex flex-col bg-[var(--bg-primary)] border-r border-[var(--border-subtle)] py-4 transition-all">
      <div className="font-mono text-base font-bold text-accent px-5 pb-5 tracking-tight">featcat</div>
      {NAV.map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === '/'}
          className={({ isActive }) =>
            `flex items-center gap-2.5 px-5 py-2 text-[13px] border-l-2 transition-all no-underline ${
              isActive
                ? 'text-accent border-accent bg-accent-subtle'
                : 'text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] hover:pl-6'
            }`
          }
        >
          <n.icon size={16} />
          {n.label}
        </NavLink>
      ))}
      <div className="mt-auto px-5 text-xs text-[var(--text-tertiary)] flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <Server size={14} className={serverOk ? 'text-green-500' : 'text-[var(--border-default)]'} />
          Server
        </div>
        <div className="flex items-center gap-2">
          <Cpu size={14} className={llm.ok ? 'text-green-500' : 'text-red-500'} />
          LLM: {llm.model}
        </div>
        <ThemeToggle />
      </div>
    </nav>
  )
}
