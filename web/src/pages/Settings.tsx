import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Sun, Moon } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SUPPORTED_LANGS, type SupportedLang } from '../i18n/config'

type Theme = 'light' | 'dark'

const CARD = 'bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5 hover:border-[var(--border-muted)] transition-colors'
const OPTION_BASE = 'flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-left transition-colors'
const OPTION_SELECTED = 'border-[var(--accent)] bg-[var(--accent-subtle-bg)]'
const OPTION_UNSELECTED = 'border-[var(--border-default)] hover:border-[var(--border-muted)]'

export function Settings() {
  const { t, i18n } = useTranslation('settings')
  const current = (i18n.resolvedLanguage ?? i18n.language) as SupportedLang
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  )

  const selectTheme = (next: Theme) => {
    if (next === 'dark') document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
    localStorage.setItem('featcat-theme', next)
    setTheme(next)
  }

  return (
    <div className="max-w-[720px] space-y-4">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
        <p className="text-sm text-[var(--text-tertiary)] mt-0.5">{t('page.subtitle')}</p>
      </div>

      <div className={CARD}>
        <h2 className="text-sm font-semibold mb-1">{t('language.title')}</h2>
        <p className="text-xs text-[var(--text-tertiary)] mb-4">{t('language.description')}</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {SUPPORTED_LANGS.map(code => {
            const selected = current === code
            return (
              <button
                key={code}
                type="button"
                onClick={() => i18n.changeLanguage(code)}
                className={`${OPTION_BASE} ${selected ? OPTION_SELECTED : OPTION_UNSELECTED}`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`inline-flex items-center justify-center w-8 h-5 rounded text-[10px] font-mono font-semibold tracking-wider ${
                    selected
                      ? 'bg-[var(--accent)] text-[var(--text-on-accent)]'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                  }`}>
                    {code.toUpperCase()}
                  </span>
                  <span className={`text-sm ${selected ? 'font-medium text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>
                    {t(`language.options.${code}`)}
                  </span>
                </div>
                {selected && (
                  <span className="text-[11px] uppercase tracking-wider text-[var(--accent)] font-medium shrink-0">
                    {t('language.current')}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div className={CARD}>
        <h2 className="text-sm font-semibold mb-1">{t('theme.title')}</h2>
        <p className="text-xs text-[var(--text-tertiary)] mb-4">{t('theme.description')}</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(['light', 'dark'] as const).map(mode => {
            const selected = theme === mode
            const Icon: LucideIcon = mode === 'dark' ? Moon : Sun
            return (
              <button
                key={mode}
                type="button"
                onClick={() => selectTheme(mode)}
                className={`${OPTION_BASE} ${selected ? OPTION_SELECTED : OPTION_UNSELECTED}`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className={`inline-flex items-center justify-center w-8 h-8 rounded ${
                    selected
                      ? 'bg-[var(--accent)] text-[var(--text-on-accent)]'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                  }`}>
                    <Icon size={16} strokeWidth={1.8} />
                  </span>
                  <span className={`text-sm ${selected ? 'font-medium text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>
                    {t(`theme.options.${mode}`)}
                  </span>
                </div>
                {selected && (
                  <span className="text-[11px] uppercase tracking-wider text-[var(--accent)] font-medium shrink-0">
                    {t('language.current')}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
