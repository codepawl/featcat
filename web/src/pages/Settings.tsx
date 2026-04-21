import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGS, type SupportedLang } from '../i18n/config'

export function Settings() {
  const { t, i18n } = useTranslation('settings')
  const current = (i18n.resolvedLanguage ?? i18n.language) as SupportedLang

  return (
    <div className="max-w-[720px]">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
        <p className="text-sm text-[var(--text-tertiary)] mt-0.5">{t('page.subtitle')}</p>
      </div>

      <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5 hover:border-[var(--border-muted)] transition-colors">
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
                className={`flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-left transition-colors ${
                  selected
                    ? 'border-[var(--accent)] bg-[var(--accent-subtle-bg)]'
                    : 'border-[var(--border-default)] hover:border-[var(--border-muted)]'
                }`}
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
    </div>
  )
}
