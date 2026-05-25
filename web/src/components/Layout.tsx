import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Menu, Search as SearchIcon, X } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { SearchBar } from './SearchBar'

export function Layout({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation('common')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)

  return (
    <div className="min-h-screen flex flex-col">
      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden" onClick={() => setMobileOpen(false)}>
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />
          <div className="relative z-50 h-full w-[240px]" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setMobileOpen(false)}
              className="absolute top-3 right-3 p-1 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              <X size={18} />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)} embedded />
          </div>
        </div>
      )}

      {/* Sticky top bar */}
      <header
        role="banner"
        className="sticky top-0 z-30 h-14 shrink-0 flex items-center gap-2 px-3 md:px-4 bg-[var(--bg-primary)] border-b border-[var(--border-subtle)]"
      >
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
            <div className="hidden md:block w-[208px] shrink-0" />
            <div className="hidden md:block flex-1">
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
          </>
        )}
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Desktop sidebar */}
        <div className="hidden md:block">
          <Sidebar />
        </div>

        <main className="flex-1 min-w-0 p-4 md:p-6 lg:p-8 animate-fade-in">
          {children}
        </main>
      </div>
    </div>
  )
}
