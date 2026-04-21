import { NavLink } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { LayoutDashboard, Database, Activity, Clock, MessageSquare, FolderKanban, GitBranch, History, Settings } from 'lucide-react'
import { api } from '../api'

const NAV = [
  { to: '/', key: 'dashboard', icon: LayoutDashboard },
  { to: '/features', key: 'features', icon: Database },
  { to: '/groups', key: 'groups', icon: FolderKanban },
  { to: '/similarity', key: 'similarity', icon: GitBranch },
  { to: '/audit', key: 'audit', icon: History },
  { to: '/monitoring', key: 'monitoring', icon: Activity },
  { to: '/jobs', key: 'jobs', icon: Clock },
  { to: '/chat', key: 'chat', icon: MessageSquare },
  { to: '/settings', key: 'settings', icon: Settings },
] as const

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation('sidebar')
  const [llm, setLlm] = useState<{ ok: boolean; model: string | null; checked: boolean }>({ ok: false, model: null, checked: false })
  const [serverOk, setServerOk] = useState(false)

  useEffect(() => {
    api.health()
      .then((d) => {
        setServerOk(true)
        setLlm({ ok: !!d.llm, model: (d.model as string) || null, checked: true })
      })
      .catch(() => { setServerOk(false); setLlm(s => ({ ...s, checked: true })) })
  }, [])

  const llmDisplay = !llm.checked
    ? t('status.checking')
    : llm.model ?? (llm.ok ? t('status.connected') : t('status.disconnected'))

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
          {t(`nav.${n.key}`)}
        </NavLink>
      ))}

      {/* Footer */}
      <div className="mt-auto px-5">
        <div className="border-t border-[var(--border-subtle)] pt-3 pb-1 flex flex-col gap-2 text-xs text-[var(--text-tertiary)]">
          <div className="flex items-center gap-2">
            <span className={`size-1.5 rounded-full ${serverOk ? 'bg-[var(--success)]' : 'bg-[var(--border-default)]'}`} />
            {t('status.server')}
          </div>
          <div className="flex items-center gap-2 truncate">
            <span className={`size-1.5 rounded-full ${llm.ok ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`} />
            <span className="truncate">{t('status.llm_label')}: {llmDisplay}</span>
          </div>
        </div>
      </div>
    </nav>
  )
}
