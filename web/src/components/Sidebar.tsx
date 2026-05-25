import { NavLink, useLocation } from 'react-router-dom'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  BookOpen,
  ChevronDown,
  Clock,
  Cog,
  Database,
  FolderKanban,
  Gauge,
  GitBranch,
  GitFork,
  HardDrive,
  History,
  LayoutDashboard,
  LayoutGrid,
  Library,
  ListChecks,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
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
  | 'sources'
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
  icon: LucideIcon
  items: NavItem[]
}

const PINNED: NavItem = { to: '/', key: 'dashboard', icon: LayoutDashboard }

const GROUPS: readonly NavGroup[] = [
  {
    key: 'catalog',
    icon: Library,
    items: [
      { to: '/search', key: 'search', icon: SearchIcon },
      { to: '/features', key: 'features', icon: Database },
      { to: '/groups', key: 'groups', icon: FolderKanban },
      { to: '/sources', key: 'sources', icon: HardDrive },
    ],
  },
  {
    key: 'quality',
    icon: Gauge,
    items: [
      { to: '/monitoring', key: 'monitoring', icon: Activity },
      { to: '/actions', key: 'actions', icon: ListChecks },
      { to: '/similarity', key: 'similarity', icon: GitBranch },
      { to: '/lineage', key: 'lineage', icon: GitFork },
    ],
  },
  {
    key: 'system',
    icon: Cog,
    items: [
      { to: '/audit', key: 'audit', icon: History },
      { to: '/jobs', key: 'jobs', icon: Clock },
    ],
  },
  {
    key: 'app',
    icon: LayoutGrid,
    items: [
      { to: '/chat', key: 'chat', icon: MessageSquare },
      { to: '/settings', key: 'settings', icon: Settings },
      { to: '/help', key: 'help', icon: BookOpen },
    ],
  },
] as const

const STORAGE_KEY = 'featcat:sidebar:groups'
const COLLAPSED_STORAGE_KEY = 'featcat:sidebar:collapsed'

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

function loadCollapsed(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === '1'
  } catch {
    return false
  }
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

/** Build the NavLink className. ``indented`` rows sit inside a collapsible
 *  section: smaller text, lighter weight, indented past the section header
 *  so the visual hierarchy reads "section → its items". The pinned Dashboard
 *  row at the top stays full-size since it isn't nested under a section.
 */
function navLinkClassName(indented: boolean, collapsed: boolean) {
  return ({ isActive }: { isActive: boolean }): string => {
    if (collapsed) {
      // Icon-only strip: centered icon, no indent distinction.
      const base =
        'flex items-center justify-center h-10 mx-2 my-0.5 rounded-md transition-colors no-underline relative'
      return isActive
        ? `${base} text-brand bg-brand-muted`
        : `${base} text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]`
    }
    const base = indented
      ? 'flex items-center gap-2 pl-9 pr-5 py-2 text-[12px] border-l-2 transition-colors no-underline'
      : 'flex items-center gap-2.5 px-5 py-2.5 text-[13px] font-medium border-l-2 transition-colors no-underline'
    if (isActive) {
      return `${base} font-medium text-brand border-brand bg-brand-muted`
    }
    return indented
      ? `${base} font-normal text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]`
      : `${base} text-[var(--text-secondary)] border-transparent hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]`
  }
}

function NavItemRow({
  item,
  onNavigate,
  badge,
  indented = false,
  collapsed = false,
}: {
  item: NavItem
  onNavigate?: () => void
  badge?: number
  indented?: boolean
  collapsed?: boolean
}) {
  const { t } = useTranslation('sidebar')
  const label = t(`nav.${item.key}`)
  return (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      onClick={onNavigate}
      className={navLinkClassName(indented, collapsed)}
      title={collapsed ? label : undefined}
      aria-label={collapsed ? label : undefined}
    >
      <item.icon size="1em" className="w-4 h-4 shrink-0" strokeWidth={1.8} />
      {!collapsed && <span className="flex-1">{label}</span>}
      {badge !== undefined && badge > 0 && (
        collapsed ? (
          <span className="absolute top-1 right-1 size-1.5 rounded-full bg-brand" aria-hidden />
        ) : (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-brand text-[var(--bg-primary)]">
            {badge > 99 ? '99+' : badge}
          </span>
        )
      )}
    </NavLink>
  )
}

export function Sidebar({ onNavigate, embedded = false }: { onNavigate?: () => void; embedded?: boolean }) {
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
  const [collapsed, setCollapsed] = useState<boolean>(() => loadCollapsed())

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore quota / private-mode errors */
    }
  }, [collapsed])

  // Ctrl/Cmd+B toggles the sidebar. Skipped if focus is inside an input/textarea
  // or contentEditable element so typing "B" in a search box still works.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'b') return
      if (!(e.ctrlKey || e.metaKey)) return
      const t = e.target as HTMLElement | null
      const tag = t?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || t?.isContentEditable) return
      e.preventDefault()
      toggleCollapsed()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [toggleCollapsed])

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

  const toggleLabel = collapsed ? t('actions.expand') : t('actions.collapse')

  return (
    <nav
      className={`shrink-0 ${embedded ? 'h-full' : 'sticky top-14 h-[calc(100vh-3.5rem)]'} overflow-y-auto flex flex-col bg-[var(--bg-primary)] border-r border-[var(--border-subtle)] py-4 transition-[width] duration-200 ease-out ${
        collapsed ? 'w-16' : 'w-[220px]'
      }`}
      aria-label="Primary navigation"
    >
      {/* Brand row with toggle. In collapsed mode the brand text is hidden;
          the toggle remains as the only interactive element in the header. */}
      <div
        className={`flex items-center pb-6 pt-1 ${
          collapsed ? 'justify-center px-2' : 'justify-between px-5'
        }`}
      >
        {!collapsed && (
          <span className="font-mono text-base font-bold tracking-tight">
            feat<span className="text-brand">cat</span>
          </span>
        )}
        <button
          type="button"
          onClick={toggleCollapsed}
          title={toggleLabel}
          aria-label={toggleLabel}
          aria-expanded={!collapsed}
          className="p-1.5 rounded-md text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
        >
          {collapsed ? (
            <PanelLeftOpen size={16} strokeWidth={1.8} />
          ) : (
            <PanelLeftClose size={16} strokeWidth={1.8} />
          )}
        </button>
      </div>

      {/* Pinned: Dashboard */}
      <NavItemRow item={PINNED} onNavigate={onNavigate} collapsed={collapsed} />

      {/* Groups. Expanded: collapsible sections with headers. Collapsed: flat
          icon strip with a thin separator between groups. */}
      {collapsed ? (
        <div className="mt-2 flex flex-col">
          {GROUPS.map((g, gi) => (
            <div
              key={g.key}
              className={gi > 0 ? 'mt-2 pt-2 border-t border-[var(--border-subtle)]' : ''}
            >
              {g.items.map((item) => (
                <NavItemRow
                  key={item.to}
                  item={item}
                  onNavigate={onNavigate}
                  badge={item.to === '/actions' ? pendingActions : undefined}
                  collapsed
                />
              ))}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-1">
          {GROUPS.map((g) => {
            const isOpen = open[g.key]
            const isActiveSection = activeGroup === g.key
            const showQualityBadge = g.key === 'quality' && !isOpen && pendingActions > 0
            const showItemCount = !isOpen && !showQualityBadge
            const headerColor = isActiveSection
              ? 'text-brand'
              : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
            return (
              <Collapsible
                key={g.key}
                open={isOpen}
                onOpenChange={(v) => setOpen((prev) => ({ ...prev, [g.key]: v }))}
              >
                <CollapsibleTrigger
                  className={`group flex w-full items-center gap-2 px-5 py-2.5 text-[12px] font-semibold uppercase tracking-wider transition-colors hover:bg-[var(--bg-secondary)] ${headerColor}`}
                >
                  <g.icon size={13} strokeWidth={1.8} />
                  <span className="flex-1 text-left">{t(`nav.sections.${g.key}`)}</span>
                  {showQualityBadge && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-brand text-[var(--bg-primary)]">
                      {pendingActions > 99 ? '99+' : pendingActions}
                    </span>
                  )}
                  {showItemCount && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]">
                      {g.items.length}
                    </span>
                  )}
                  <ChevronDown
                    size={12}
                    strokeWidth={2}
                    className={`transition-transform ${isOpen ? '' : '-rotate-90'}`}
                  />
                </CollapsibleTrigger>
                <CollapsibleContent className="overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up">
                  <div className="py-0.5">
                    {g.items.map((item) => (
                      <NavItemRow
                        key={item.to}
                        item={item}
                        onNavigate={onNavigate}
                        badge={item.to === '/actions' ? pendingActions : undefined}
                        indented
                      />
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )
          })}
        </div>
      )}

      {/* Footer. Status text hides when collapsed; the colored dots remain as
          a minimal health indicator. */}
      <div className={`mt-auto ${collapsed ? 'px-2' : 'px-5'}`}>
        <div
          className={`border-t border-[var(--border-subtle)] pt-3 pb-1 flex text-xs text-[var(--text-tertiary)] ${
            collapsed ? 'flex-col items-center gap-2' : 'flex-col gap-2'
          }`}
        >
          <div
            className={`flex items-center gap-2 ${collapsed ? 'justify-center' : ''}`}
            title={collapsed ? t('status.server') : undefined}
          >
            <span
              className={`size-1.5 rounded-full ${serverOk ? 'bg-[var(--success)]' : 'bg-[var(--border-default)]'}`}
            />
            {!collapsed && t('status.server')}
          </div>
          <div
            className={`flex items-center gap-2 truncate ${collapsed ? 'justify-center' : ''}`}
            title={collapsed ? `${t('status.llm_label')}: ${llmDisplay}` : undefined}
          >
            <span
              className={`size-1.5 rounded-full ${llm.ok ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`}
            />
            {!collapsed && (
              <span className="truncate">
                {t('status.llm_label')}: {llmDisplay}
              </span>
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}
