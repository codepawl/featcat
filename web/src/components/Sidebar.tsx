import { NavLink, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  BookOpen,
  ChevronDown,
  Clock,
  Database,
  FolderKanban,
  GitBranch,
  GitFork,
  History,
  LayoutDashboard,
  ListChecks,
  MessageSquare,
  type LucideIcon,
  Search as SearchIcon,
  Settings,
} from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible'
import { api } from '../api'

type NavKey =
  | 'dashboard'
  | 'search'
  | 'features'
  | 'groups'
  | 'monitoring'
  | 'actions'
  | 'similarity'
  | 'lineage'
  | 'audit'
  | 'jobs'
  | 'chat'
  | 'settings'
  | 'help'

interface NavItem {
  to: string
  key: NavKey
  icon: LucideIcon
}

type GroupKey = 'catalog' | 'quality' | 'system' | 'app'

interface NavGroup {
  key: GroupKey
  items: NavItem[]
}

const PINNED: NavItem = { to: '/', key: 'dashboard', icon: LayoutDashboard }

const GROUPS: readonly NavGroup[] = [
  {
    key: 'catalog',
    items: [
      { to: '/search', key: 'search', icon: SearchIcon },
      { to: '/features', key: 'features', icon: Database },
      { to: '/groups', key: 'groups', icon: FolderKanban },
    ],
  },
  {
    key: 'quality',
    items: [
      { to: '/monitoring', key: 'monitoring', icon: Activity },
      { to: '/actions', key: 'actions', icon: ListChecks },
      { to: '/similarity', key: 'similarity', icon: GitBranch },
      { to: '/lineage', key: 'lineage', icon: GitFork },
    ],
  },
  {
    key: 'system',
    items: [
      { to: '/audit', key: 'audit', icon: History },
      { to: '/jobs', key: 'jobs', icon: Clock },
    ],
  },
  {
    key: 'app',
    items: [
      { to: '/chat', key: 'chat', icon: MessageSquare },
      { to: '/settings', key: 'settings', icon: Settings },
      { to: '/help', key: 'help', icon: BookOpen },
    ],
  },
] as const

const STORAGE_KEY = 'featcat:sidebar:groups'

type OpenMap = Record<GroupKey, boolean>

function pathMatchesItem(path: string, to: string): boolean {
  if (to === '/') return path === '/'
  return path === to || path.startsWith(`${to}/`)
}

function groupOfPath(path: string): GroupKey | null {
  for (const g of GROUPS) {
    if (g.items.some((i) => pathMatchesItem(path, i.to))) return g.key
  }
  return null
}

function loadOpen(): OpenMap {
  const fallback: OpenMap = { catalog: false, quality: false, system: false, app: false }
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<OpenMap>
    return {
      catalog: !!parsed.catalog,
      quality: !!parsed.quality,
      system: !!parsed.system,
      app: !!parsed.app,
    }
  } catch {
    return fallback
  }
}

function navLinkClassName({ isActive }: { isActive: boolean }): string {
  const base =
    'flex items-center gap-2.5 px-5 py-2.5 text-[13px] font-medium border-l-2 transition-colors no-underline'
  return isActive
    ? `${base} text-brand border-brand bg-brand-muted`
    : `${base} text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]`
}

function NavItemRow({
  item,
  onNavigate,
  badge,
}: {
  item: NavItem
  onNavigate?: () => void
  badge?: number
}) {
  const { t } = useTranslation('sidebar')
  return (
    <NavLink to={item.to} end={item.to === '/'} onClick={onNavigate} className={navLinkClassName}>
      <item.icon size={16} strokeWidth={1.8} />
      <span className="flex-1">{t(`nav.${item.key}`)}</span>
      {badge !== undefined && badge > 0 && (
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-brand text-[var(--bg-primary)]">
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </NavLink>
  )
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation('sidebar')
  const location = useLocation()
  const [llm, setLlm] = useState<{ ok: boolean; model: string | null; checked: boolean }>({
    ok: false,
    model: null,
    checked: false,
  })
  const [serverOk, setServerOk] = useState(false)
  const [pendingActions, setPendingActions] = useState<number>(0)
  const [open, setOpen] = useState<OpenMap>(() => loadOpen())

  useEffect(() => {
    api
      .health()
      .then((d) => {
        setServerOk(true)
        setLlm({ ok: !!d.llm, model: (d.model as string) || null, checked: true })
      })
      .catch(() => {
        setServerOk(false)
        setLlm((s) => ({ ...s, checked: true }))
      })
    api.actions
      .count('pending')
      .then((d) => setPendingActions(d.count))
      .catch(() => {})
  }, [])

  // Force the group containing the active route to be open. Manual open/close
  // for other groups still persists, but the active group can't be hidden.
  const activeGroup = groupOfPath(location.pathname)
  useEffect(() => {
    if (activeGroup) {
      setOpen((prev) => (prev[activeGroup] ? prev : { ...prev, [activeGroup]: true }))
    }
  }, [activeGroup])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(open))
    } catch {
      /* ignore quota / private-mode errors */
    }
  }, [open])

  const llmDisplay = !llm.checked
    ? t('status.checking')
    : (llm.model ?? (llm.ok ? t('status.connected') : t('status.disconnected')))

  return (
    <nav className="w-[220px] shrink-0 sticky top-0 h-screen overflow-y-auto flex flex-col bg-[var(--bg-primary)] border-r border-[var(--border-subtle)] py-4">
      {/* Brand */}
      <div className="px-5 pb-6 pt-1">
        <span className="font-mono text-base font-bold tracking-tight">
          feat<span className="text-brand">cat</span>
        </span>
      </div>

      {/* Pinned: Dashboard */}
      <NavItemRow item={PINNED} onNavigate={onNavigate} />

      {/* Groups */}
      <div className="mt-3 flex flex-col">
        {GROUPS.map((g) => {
          const isOpen = open[g.key]
          const showQualityBadge = g.key === 'quality' && !isOpen && pendingActions > 0
          return (
            <Collapsible
              key={g.key}
              open={isOpen}
              onOpenChange={(v) => setOpen((prev) => ({ ...prev, [g.key]: v }))}
            >
              <CollapsibleTrigger className="group flex w-full items-center gap-2 px-5 py-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
                <span className="flex-1 text-left">{t(`nav.sections.${g.key}`)}</span>
                {showQualityBadge && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-brand text-[var(--bg-primary)]">
                    {pendingActions > 99 ? '99+' : pendingActions}
                  </span>
                )}
                <ChevronDown
                  size={12}
                  strokeWidth={2}
                  className={`transition-transform ${isOpen ? '' : '-rotate-90'}`}
                />
              </CollapsibleTrigger>
              <CollapsibleContent>
                {g.items.map((item) => (
                  <NavItemRow
                    key={item.to}
                    item={item}
                    onNavigate={onNavigate}
                    badge={item.to === '/actions' ? pendingActions : undefined}
                  />
                ))}
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </div>

      {/* Footer */}
      <div className="mt-auto px-5">
        <div className="border-t border-[var(--border-subtle)] pt-3 pb-1 flex flex-col gap-2 text-xs text-[var(--text-tertiary)]">
          <div className="flex items-center gap-2">
            <span
              className={`size-1.5 rounded-full ${serverOk ? 'bg-[var(--success)]' : 'bg-[var(--border-default)]'}`}
            />
            {t('status.server')}
          </div>
          <div className="flex items-center gap-2 truncate">
            <span
              className={`size-1.5 rounded-full ${llm.ok ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`}
            />
            <span className="truncate">
              {t('status.llm_label')}: {llmDisplay}
            </span>
          </div>
        </div>
      </div>
    </nav>
  )
}
