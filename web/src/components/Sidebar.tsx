import { NavLink, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Activity,
  ChevronDown,
  Clock,
  Cog,
  Database,
  BarChart3,
  Layers3,
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
  RefreshCw,
  Users,
  type LucideIcon,
  Search as SearchIcon,
} from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible'
import { api } from '../api'

type NavKey =
  | 'dashboard'
  | 'search'
  | 'features'
  | 'businessMetrics'
  | 'entities'
  | 'entityRelationships'
  | 'featureViews'
  | 'featureSets'
  | 'groups'
  | 'sources'
  | 'monitoring'
  | 'actions'
  | 'similarity'
  | 'lineage'
  | 'audit'
  | 'datasetBuilds'
  | 'materializationSchedules'
  | 'jobs'
  | 'chat'
  | 'settings'
  | 'help'

interface NavItem {
  to: string
  key: NavKey
  icon: LucideIcon
}

type GroupKey = 'registry' | 'modeling' | 'business' | 'quality' | 'system'
type SectionKey = GroupKey | 'server'

interface NavGroup {
  key: GroupKey
  icon: LucideIcon
  items: NavItem[]
}

const PINNED: NavItem = { to: '/', key: 'dashboard', icon: LayoutDashboard }

const GROUPS: readonly NavGroup[] = [
  {
    key: 'registry',
    icon: Library,
    items: [
      { to: '/features', key: 'features', icon: Database },
      { to: '/feature-views', key: 'featureViews', icon: Layers3 },
      { to: '/feature-sets', key: 'featureSets', icon: FolderKanban },
    ],
  },
  {
    key: 'modeling',
    icon: GitFork,
    items: [
      { to: '/entities', key: 'entities', icon: Users },
      { to: '/entity-relationships', key: 'entityRelationships', icon: GitFork },
      { to: '/sources', key: 'sources', icon: HardDrive },
    ],
  },
  {
    key: 'business',
    icon: FolderKanban,
    items: [
      { to: '/business-metrics', key: 'businessMetrics', icon: BarChart3 },
      { to: '/groups', key: 'groups', icon: FolderKanban },
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
      { to: '/datasets/builds', key: 'datasetBuilds', icon: Database },
      { to: '/online/materialization-schedules', key: 'materializationSchedules', icon: RefreshCw },
      { to: '/jobs', key: 'jobs', icon: Clock },
    ],
  },
] as const



const STORAGE_KEY = 'featcat:sidebar:groups'
type OpenMap = Record<GroupKey, boolean>

function pathMatchesItem(path: string, to: string): boolean {
  if (to === '/') return path === '/'
  return path === to || path.startsWith(`${to}/`)
}

function groupOfPath(path: string): SectionKey | null {
  for (const g of GROUPS) {
    if (g.items.some((i) => pathMatchesItem(path, i.to))) return g.key
  }
  if (pathMatchesItem(path, '/chat') || pathMatchesItem(path, '/help') || pathMatchesItem(path, '/settings')) {
    return 'server'
  }
  return null
}

function loadOpen(): OpenMap {
  const fallback: OpenMap = {
    registry: false,
    modeling: false,
    business: false,
    quality: false,
    system: false,
  }
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<OpenMap>
    return {
      registry: !!parsed.registry,
      modeling: !!parsed.modeling,
      business: !!parsed.business,
      quality: !!parsed.quality,
      system: !!parsed.system,
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
    const base = 'flex items-center rounded-lg no-underline relative transition-all duration-100 active:scale-[0.98]'

    const dimensions = collapsed
      ? 'h-10 w-10 mx-auto my-1 justify-center px-0'
      : indented
        ? 'h-9 px-3 pl-9 my-0.5 mx-3 justify-start text-[12px]'
        : 'h-9 px-3 my-0.5 mx-3 justify-start text-[12px] font-medium'

    const stateColors = isActive
      ? 'text-brand bg-brand-subtle-bg font-medium'
      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]'

    const indicator = isActive
      ? ' after:absolute after:-left-3 after:top-2 after:bottom-2 after:w-1 after:rounded-r-md after:bg-brand'
      : ''

    return `${base} ${dimensions} ${stateColors}${indicator}`
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
      <span className={`transition-all duration-100 truncate ${collapsed ? 'w-0 opacity-0 ml-0 flex-none' : 'ml-2 flex-1 text-left min-w-0'}`}>
        {label}
      </span>
      {badge !== undefined && badge > 0 && (
        <span
          className={`transition-all duration-100 rounded-full bg-brand text-brand-foreground font-semibold shadow-sm flex items-center justify-center ${
            collapsed
              ? 'absolute top-1.5 right-1.5 size-2 animate-pulse text-[0px] p-0'
              : 'text-[9px] font-mono px-1.5 py-0.5 rounded-md bg-brand text-[var(--bg-primary)] ml-auto shrink-0 h-4 min-w-[16px]'
          }`}
        >
          <span className={`transition-all duration-100 ${collapsed ? 'opacity-0 scale-0 w-0' : 'opacity-100 scale-100'}`}>
            {badge > 99 ? '99+' : badge}
          </span>
        </span>
      )}
    </NavLink>
  )
}



export function Sidebar({
  onNavigate,
  embedded = false,
  collapsed = false,
}: {
  onNavigate?: () => void
  embedded?: boolean
  collapsed?: boolean
}) {
  const { t } = useTranslation('sidebar')
  const location = useLocation()
  const [pendingActions, setPendingActions] = useState<number>(0)
  const [open, setOpen] = useState<OpenMap>(() => loadOpen())

  useEffect(() => {
    api.actions
      .count('pending')
      .then((d) => setPendingActions(d.count))
      .catch(() => {})
  }, [])

  // Force the group containing the active route to be open. Manual open/close
  // for other groups still persists, but the active group can't be hidden.
  const activeGroup = groupOfPath(location.pathname)
  useEffect(() => {
    if (activeGroup && activeGroup !== 'server') {
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

  return (
    <nav
      className={`shrink-0 ${
        embedded
          ? 'h-full w-full'
          : `sticky top-14 h-[calc(100vh-3.5rem)] border-r border-[var(--border-subtle)] ${collapsed ? 'w-16' : 'w-[220px]'}`
      } overflow-hidden flex flex-col bg-[var(--bg-primary)] py-4 transition-[width] duration-100 ease-in-out`}
      aria-label="Primary navigation"
    >

      {/* Groups. Expanded: collapsible sections with headers. Collapsed: flat
          icon strip with a thin separator between groups. */}
      <div className={`mt-2 flex-1 min-h-0 overflow-y-auto flex flex-col gap-1 ${collapsed ? '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden' : ''}`}>
        <NavItemRow
          item={PINNED}
          onNavigate={onNavigate}
          collapsed={collapsed}
        />
        <div className={`my-2 border-t border-[var(--border-subtle)] opacity-40 transition-all duration-100 ${collapsed ? 'mx-3' : 'mx-5'}`} aria-hidden="true" />

        {GROUPS.map((g, gi) => {
          const isOpen = collapsed ? true : open[g.key]
          const isActiveSection = activeGroup === g.key
          const showQualityBadge = g.key === 'quality' && !isOpen && pendingActions > 0
          const showItemCount = !isOpen && !showQualityBadge
          const headerColor = isActiveSection
            ? 'text-brand'
            : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
          return (
            <div key={g.key}>
              {collapsed && gi > 0 && (
                <div className="my-2 mx-3 border-t border-[var(--border-subtle)] opacity-40 transition-all duration-100" aria-hidden="true" />
              )}
              <Collapsible
                open={isOpen}
                onOpenChange={(v) => !collapsed && setOpen((prev) => ({ ...prev, [g.key]: v }))}
              >
                <CollapsibleTrigger
                  className={`group flex items-center gap-2 mx-3 rounded-lg text-[11px] font-semibold uppercase tracking-wider transition-all duration-100 hover:bg-[var(--bg-secondary)]/60 ${headerColor} ${
                    collapsed ? 'h-0 py-0 my-0 opacity-0 overflow-hidden pointer-events-none' : 'h-8 px-3 py-2 my-0.5 opacity-100'
                  }`}
                >
                  <g.icon size={13} strokeWidth={1.8} className="shrink-0" />
                  <span className={`transition-all duration-100 truncate ${collapsed ? 'w-0 opacity-0 ml-0 flex-none' : 'ml-2 flex-1 text-left min-w-0'}`}>
                    {t(`nav.sections.${g.key}`)}
                  </span>
                  <div className={`flex items-center gap-1.5 transition-all duration-100 shrink-0 ${collapsed ? 'w-0 opacity-0 overflow-hidden' : 'w-auto opacity-100'}`}>
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
                      className={`transition-transform duration-200 ${isOpen ? '' : '-rotate-90'}`}
                    />
                  </div>
                </CollapsibleTrigger>
                <CollapsibleContent className="overflow-hidden data-[state=open]:animate-collapsible-down data-[state=closed]:animate-collapsible-up">
                  <div className="py-0.5">
                    {g.items.map((item) => (
                      <NavItemRow
                        key={item.to}
                        item={item}
                        onNavigate={onNavigate}
                        badge={item.to === '/actions' ? pendingActions : undefined}
                        indented={!collapsed}
                        collapsed={collapsed}
                      />
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            </div>
          )
        })}
      </div>
    </nav>
  )
}
