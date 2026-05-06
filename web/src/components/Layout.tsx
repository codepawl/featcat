import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Menu, X } from 'lucide-react'
import { Sidebar } from './Sidebar'

export function Layout({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation('common')
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen">
      {/* Mobile menu button */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-3 left-3 z-40 p-2 rounded-lg bg-[var(--bg-primary)] border border-[var(--border-subtle)] shadow-sm md:hidden"
        aria-label={t('actions.open_menu')}
      >
        <Menu size={20} />
      </button>

      {/* Mobile overlay */}
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
            <Sidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <Sidebar />
      </div>

      <main className="flex-1 min-w-0 p-4 pt-14 md:p-6 lg:p-8 md:pt-6 lg:pt-8 overflow-y-auto animate-fade-in">
        {children}
      </main>
    </div>
  )
}
