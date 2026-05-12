import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Sun, Moon, Trash2, RefreshCw } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SUPPORTED_LANGS, type SupportedLang } from '../i18n/config'
import { api, invalidateCache } from '../api'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { PageHeader } from '../components/PageHeader'

type Theme = 'light' | 'dark'

const CARD = 'bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5 hover:border-[var(--border-muted)] transition-colors'
const OPTION_BASE = 'flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-left transition-colors'
const OPTION_SELECTED = 'border-[var(--brand)] bg-[var(--brand-subtle-bg)]'
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
      <PageHeader title={t('page.title')} subtitle={t('page.subtitle')} />

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
                      ? 'bg-[var(--brand)] text-[var(--text-on-brand)]'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                  }`}>
                    {code.toUpperCase()}
                  </span>
                  <span className={`text-sm ${selected ? 'font-medium text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>
                    {t(`language.options.${code}`)}
                  </span>
                </div>
                {selected && (
                  <span className="text-[11px] uppercase tracking-wider text-[var(--brand)] font-medium shrink-0">
                    {t('language.current')}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <LLMCacheCard />

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
                      ? 'bg-[var(--brand)] text-[var(--text-on-brand)]'
                      : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
                  }`}>
                    <Icon size={16} strokeWidth={1.8} />
                  </span>
                  <span className={`text-sm ${selected ? 'font-medium text-[var(--text-primary)]' : 'text-[var(--text-secondary)]'}`}>
                    {t(`theme.options.${mode}`)}
                  </span>
                </div>
                {selected && (
                  <span className="text-[11px] uppercase tracking-wider text-[var(--brand)] font-medium shrink-0">
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


function LLMCacheCard() {
  const { t } = useTranslation('settings')
  const [stats, setStats] = useState<{ total: number; active: number; expired: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<'clear' | 'expired' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmClearOpen, setConfirmClearOpen] = useState(false)

  const load = () => {
    setLoading(true)
    invalidateCache('/admin/cache')
    api.admin.cacheStats().then(setStats).catch((e) => setError(String(e))).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const clear = async () => {
    setConfirmClearOpen(false)
    setBusy('clear')
    try {
      await api.admin.cacheClear()
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  const clearExpired = async () => {
    setBusy('expired')
    try {
      await api.admin.cacheClearExpired()
      load()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5 hover:border-[var(--border-muted)] transition-colors">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h2 className="text-sm font-semibold mb-1">{t('llm_cache.title', { defaultValue: 'LLM Response Cache' })}</h2>
          <p className="text-xs text-[var(--text-tertiary)]">{t('llm_cache.description', { defaultValue: 'Cached AI responses keyed by prompt + system. Clearing forces a fresh LLM call next time.' })}</p>
        </div>
        <button onClick={load} className="text-[var(--text-tertiary)] hover:text-brand" aria-label="Refresh">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && <p className="text-[12px] text-[var(--danger)] mb-3">{error}</p>}

      <div className="grid grid-cols-3 gap-3 mb-2">
        <Stat label={t('llm_cache.total', { defaultValue: 'Total' })} value={stats?.total ?? '—'} />
        <Stat label={t('llm_cache.active', { defaultValue: 'Active' })} value={stats?.active ?? '—'} />
        <Stat label={t('llm_cache.expired', { defaultValue: 'Expired' })} value={stats?.expired ?? '—'} />
      </div>

      {/* Empty-state hint distinguishes "cache hasn't been used yet" (normal)
          from "cache is broken" (was the original bug — 0/0/0 with no
          context). The coverage line names exactly which features write
          to the cache so users aren't confused about why AI Chat doesn't
          increment counters. */}
      {stats && stats.total === 0 && !loading && (
        <p className="text-[11px] text-[var(--text-tertiary)] italic mb-2">
          {t('llm_cache.empty_hint', {
            defaultValue: 'Cache trống — chưa có yêu cầu AI nào sinh kết quả cache. Dùng Discovery / Auto-doc / NL Query / Monitoring để điền cache.',
          })}
        </p>
      )}
      <p className="text-[11px] text-[var(--text-tertiary)] mb-4">
        {t('llm_cache.coverage_hint', {
          defaultValue: 'Áp dụng cho: Discovery, Auto-doc, NL Query, Monitoring LLM analysis. AI Chat luôn streaming nên không cache.',
        })}
      </p>

      <div className="flex gap-2">
        <button
          onClick={clearExpired}
          disabled={busy !== null}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)] disabled:opacity-50"
        >
          <Trash2 size={12} /> {busy === 'expired' ? '…' : t('llm_cache.clear_expired', { defaultValue: 'Clear expired' })}
        </button>
        <button
          onClick={() => setConfirmClearOpen(true)}
          disabled={busy !== null}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium border border-[var(--danger-subtle-bg)] text-[var(--danger)] rounded-lg hover:bg-[var(--danger-subtle-bg)] disabled:opacity-50"
        >
          <Trash2 size={12} /> {busy === 'clear' ? '…' : t('llm_cache.clear_all', { defaultValue: 'Clear all' })}
        </button>
      </div>
      <ConfirmDialog
        open={confirmClearOpen}
        onClose={() => setConfirmClearOpen(false)}
        title={t('llm_cache.confirm_clear', { defaultValue: 'Xóa TOÀN BỘ phản hồi LLM đã cache?' })}
        confirmLabel={t('llm_cache.clear_all', { defaultValue: 'Clear all' })}
        onConfirm={clear}
      />
    </div>
  )
}


function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="border border-[var(--border-subtle)] rounded-lg p-3">
      <div className="text-[10px] uppercase text-[var(--text-tertiary)] tracking-wide mb-1">{label}</div>
      <div className="text-xl font-semibold font-mono">{value}</div>
    </div>
  )
}
