import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { BookOpen, LogIn, Menu, PanelLeftClose, PanelLeftOpen, Search as SearchIcon, Settings as SettingsIcon, X, Sparkles } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { SearchBar } from './SearchBar'
import { Modal } from './Modal'
import { useAuth } from '../auth'
import { Settings as SettingsPage } from '../pages/Settings'
import { AuthAccessPanel } from './AuthAccessPanel'

const COLLAPSED_STORAGE_KEY = 'featcat:sidebar:collapsed'

function loadCollapsed(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function Layout({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation(['common', 'sidebar'])
  const { auth, refreshAuth, signInWithToken, signOut } = useAuth()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [authPanelOpen, setAuthPanelOpen] = useState(false)
  const [collapsed, setCollapsed] = useState<boolean>(() => loadCollapsed())

  const toggleCollapsed = useCallback(() => setCollapsed((c) => !c), [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? '1' : '0')
    } catch {
      /* ignore quota */
    }
  }, [collapsed])

  // Ctrl/Cmd+B toggles the sidebar.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== 'b') return
      if (!(e.ctrlKey || e.metaKey)) return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase()
      if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return
      e.preventDefault()
      toggleCollapsed()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [toggleCollapsed])

  return (
    <div className="min-h-screen flex flex-col">
      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden flex" onClick={() => setMobileOpen(false)}>
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] transition-opacity duration-200" />

          {/* Drawer Content */}
          <div
            className="relative z-50 h-full w-[260px] bg-[var(--bg-primary)] border-r border-[var(--border-subtle)] shadow-xl flex flex-col animate-in slide-in-from-left duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="h-14 px-4 flex items-center justify-between border-b border-[var(--border-subtle)] shrink-0">
              <span className="font-semibold text-brand text-sm tracking-wide">FeatCat</span>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
                aria-label={t('actions.close')}
              >
                <X size={18} />
              </button>
            </div>
            {/* Sidebar content */}
            <div className="flex-1 overflow-y-auto min-h-0">
              <Sidebar onNavigate={() => setMobileOpen(false)} embedded collapsed={false} />
            </div>
          </div>
        </div>
      )}

      {/* Sticky top bar */}
      <header
        role="banner"
        className="sticky top-0 z-30 h-14 shrink-0 flex items-center bg-[var(--bg-primary)] border-b border-[var(--border-subtle)]"
      >
        {/* Left Side: Sidebar Toggle (logo removed, sticky/no-move) */}
        <div className="hidden md:flex items-center justify-center shrink-0 w-16 h-full">
          <button
            type="button"
            onClick={toggleCollapsed}
            className="p-1.5 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
            title={collapsed ? t('sidebar:actions.expand') : t('sidebar:actions.collapse')}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} strokeWidth={1.8} />
            ) : (
              <PanelLeftClose size={18} strokeWidth={1.8} />
            )}
          </button>
        </div>

        {/* Right Side: Main Header Content */}
        <div className="flex-1 h-full flex items-center justify-between px-3 md:px-4 min-w-0">
          {mobileSearchOpen ? (
            <>
              <SearchBar className="flex-1" onSubmit={() => setMobileSearchOpen(false)} />
              <button
                onClick={() => setMobileSearchOpen(false)}
                className="p-2 rounded-lg text-[var(--text-tertiary)] hover:text-[var(--text-primary)] md:hidden"
                aria-label={t('actions.close')}
              >
                <X size={18} />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setMobileOpen(true)}
                className="p-2 rounded-lg hover:bg-[var(--bg-secondary)] md:hidden"
                aria-label={t('actions.open_menu')}
              >
                <Menu size={20} />
              </button>

              {/* Spacer on the left to center the search bar relative to the remaining space */}
              <div className="hidden md:block w-[184px] shrink-0" aria-hidden="true" />

              <div className="hidden md:block flex-1 max-w-2xl mx-auto">
                <SearchBar />
              </div>

              <div className="flex-1 md:hidden" />
              <button
                onClick={() => setMobileSearchOpen(true)}
                className="p-2 rounded-lg hover:bg-[var(--bg-secondary)] md:hidden"
                aria-label={t('actions.search')}
              >
                <SearchIcon size={20} />
              </button>

              {/* Top-right Actions: AI Chat, Help & Settings */}
              <div className="flex items-center gap-2 ml-2 shrink-0">
                <button
                  type="button"
                  onClick={() => setAuthPanelOpen(true)}
                  className="flex items-center justify-center gap-1.5 h-9 px-3.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] hover:bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] transition-colors shrink-0"
                  title={auth?.user ? `${auth.user.email} (${auth.user.role})` : 'Account'}
                >
                  <LogIn size={14} strokeWidth={2} />
                  <span className="hidden sm:inline">
                    {auth?.user ? auth.user.email : 'Account'}
                  </span>
                </button>
                <Link
                  to="/chat"
                  className="flex items-center justify-center gap-1.5 h-9 px-3.5 bg-[var(--brand-subtle-bg)] border border-[var(--brand-border)] hover:border-brand hover:brightness-[0.98] dark:hover:brightness-[1.05] rounded-lg text-sm text-brand transition-all duration-200 font-medium shadow-sm shrink-0 active:scale-[0.98]"
                >
                  <Sparkles size={14} className="text-brand animate-pulse" strokeWidth={2.2} />
                  <span>{t('sidebar:nav.chat')}</span>
                </Link>
                <div className="h-4 w-[1px] bg-[var(--border-subtle)] mx-0.5" aria-hidden="true" />
                <Link
                  to="/help"
                  className="flex items-center justify-center h-9 w-9 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors shrink-0"
                  title={t('sidebar:nav.help')}
                >
                  <BookOpen size={18} strokeWidth={1.8} />
                </Link>
                <button
                  type="button"
                  onClick={() => setSettingsOpen(true)}
                  className="flex items-center justify-center h-9 w-9 rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors shrink-0"
                  title={t('sidebar:nav.settings')}
                >
                  <SettingsIcon size={18} strokeWidth={1.8} />
                </button>
              </div>
            </>
          )}
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Desktop sidebar */}
        <div className="hidden md:block shrink-0">
          <Sidebar collapsed={collapsed} />
        </div>

        <main className="flex-1 min-w-0 p-4 md:p-6 lg:p-8 animate-fade-in">
          {children}
        </main>
      </div>

      <Modal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        title={t('sidebar:nav.settings')}
        maxWidth="max-w-2xl"
      >
        <SettingsPage />
      </Modal>

      <Modal
        open={authPanelOpen}
        onClose={() => setAuthPanelOpen(false)}
        title="Account"
        maxWidth="max-w-xl"
      >
        <AuthAccessPanel
          auth={auth}
          onRetry={() => void refreshAuth()}
          onSignIn={signInWithToken}
          onSignOut={async () => {
            await signOut()
            setAuthPanelOpen(false)
          }}
        />
      </Modal>
    </div>
  )
}
