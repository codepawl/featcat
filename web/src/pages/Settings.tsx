import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Sun, Moon, Trash2, RefreshCw } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { SUPPORTED_LANGS, type SupportedLang } from '../i18n/config'
import { api, invalidateCache, type AccessRequestItem } from '../api'
import { isAdmin, useAuth } from '../auth'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { PageHeader } from '../components/PageHeader'

type Theme = 'light' | 'dark'

const CARD = 'bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5 hover:border-[var(--border-muted)] transition-colors'
const OPTION_BASE = 'flex items-center justify-between gap-3 px-4 py-3 rounded-lg border text-left transition-colors'
const OPTION_SELECTED = 'border-[var(--brand)] bg-[var(--brand-subtle-bg)]'
const OPTION_UNSELECTED = 'border-[var(--border-default)] hover:border-[var(--border-muted)]'

function SystemStatus() {
  const { t } = useTranslation('settings')
  const [llm, setLlm] = useState<{ ok: boolean; model: string | null; checked: boolean }>({
    ok: false,
    model: null,
    checked: false,
  })
  const [serverOk, setServerOk] = useState(false)

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
  }, [])

  const llmDisplay = !llm.checked
    ? t('status.checking', { defaultValue: 'checking...' })
    : (llm.model ?? (llm.ok ? t('status.connected', { defaultValue: 'Connected' }) : t('status.disconnected', { defaultValue: 'Disconnected' })))

  return (
    <div className="py-2 space-y-3">
      <h2 className="text-sm font-semibold text-[var(--text-primary)]">
        {t('status.title', { defaultValue: 'System Status' })}
      </h2>
      <div className="flex flex-wrap gap-x-6 gap-y-3 text-xs">
        {/* Server Status */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {serverOk && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--success)] opacity-75" />}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${serverOk ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`} />
          </span>
          <span className="text-[var(--text-secondary)] font-medium">
            {t('status.server', { defaultValue: 'Server' })}:
          </span>
          <span className={serverOk ? 'text-[var(--success)] font-medium' : 'text-[var(--danger)] font-medium'}>
            {serverOk ? t('status.connected', { defaultValue: 'Connected' }) : t('status.disconnected', { defaultValue: 'Disconnected' })}
          </span>
        </div>

        {/* LLM Status */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {llm.ok && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[var(--success)] opacity-75" />}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${llm.ok ? 'bg-[var(--success)]' : 'bg-[var(--danger)]'}`} />
          </span>
          <span className="text-[var(--text-secondary)] font-medium">
            {t('status.llm_label', { defaultValue: 'AI / LLM' })}:
          </span>
          {llm.ok ? (
            <span className="font-mono text-[11px] px-1.5 py-0.5 rounded bg-brand-subtle-bg text-brand font-medium">
              {llmDisplay}
            </span>
          ) : (
            <span className="text-[var(--danger)] font-medium">
              {llmDisplay}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

export function Settings() {
  const { t, i18n } = useTranslation('settings')
  const { auth, signOut } = useAuth()
  const current = (i18n.resolvedLanguage ?? i18n.language) as SupportedLang
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains('dark') ? 'dark' : 'light'
  )
  const [accessRequests, setAccessRequests] = useState<AccessRequestItem[]>([])

  useEffect(() => {
    if (!isAdmin(auth?.user)) {
      setAccessRequests([])
      return
    }
    api.auth.accessRequests().then(setAccessRequests).catch(() => setAccessRequests([]))
  }, [auth?.user])

  const selectTheme = (next: Theme) => {
    if (next === 'dark') document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
    localStorage.setItem('featcat-theme', next)
    setTheme(next)
  }

  return (
    <div className="max-w space-y-6">
      <PageHeader title={t('page.title')} subtitle={t('page.subtitle')} />

      <div className={CARD}>
        <h2 className="text-sm font-semibold mb-1">{t('auth.title', { defaultValue: 'Access' })}</h2>
        <p className="text-xs text-[var(--text-tertiary)] mb-4">
          {auth?.user
            ? t('auth.signed_in', {
                defaultValue: 'Signed in as {{email}} ({{role}})',
                email: auth.user.email,
                role: auth.user.role,
              })
            : t('auth.not_signed_in', { defaultValue: 'Not signed in.' })}
        </p>
        {auth?.user ? (
          <button
            type="button"
            onClick={() => void signOut()}
            className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]"
          >
            {t('auth.sign_out', { defaultValue: 'Sign out' })}
          </button>
        ) : (
          <p className="text-xs text-[var(--text-secondary)]">
            {t('auth.hint', {
              defaultValue: 'Use the Account button in the top bar if you want to sign in, switch accounts, or refresh an optional company session.',
            })}
          </p>
        )}
      </div>

      {isAdmin(auth?.user) && (
        <div className={CARD}>
          <h2 className="text-sm font-semibold mb-1">{t('auth.requests_title', { defaultValue: 'Pending access requests' })}</h2>
          <p className="text-xs text-[var(--text-tertiary)] mb-4">
            {t('auth.requests_hint', {
              defaultValue: 'Employees can request access with their @fpt.com address from the optional account panel.',
            })}
          </p>
          {accessRequests.length === 0 ? (
            <p className="text-xs text-[var(--text-secondary)]">
              {t('auth.requests_empty', { defaultValue: 'No pending requests.' })}
            </p>
          ) : (
            <div className="space-y-2">
              {accessRequests.map((req) => (
                <div key={req.id} className="rounded-lg border border-[var(--border-default)] bg-[var(--bg-secondary)] p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-sm text-[var(--text-primary)]">{req.email}</span>
                    <span className="px-2 py-0.5 rounded-full bg-[var(--brand-subtle-bg)] text-brand text-[11px] uppercase tracking-wide">
                      {req.status}
                    </span>
                  </div>
                  {req.display_name && <p className="mt-1 text-xs text-[var(--text-secondary)]">{req.display_name}</p>}
                  {req.message && <p className="mt-1 text-xs text-[var(--text-secondary)] whitespace-pre-wrap">{req.message}</p>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <SystemStatus />

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

      {isAdmin(auth?.user) ? <LLMCacheCard /> : <AdminOnlyNotice />}

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


function AdminOnlyNotice() {
  const { t } = useTranslation('settings')
  return (
    <div className={CARD}>
      <h2 className="text-sm font-semibold mb-1">{t('admin.title', { defaultValue: 'Admin tools' })}</h2>
      <p className="text-xs text-[var(--text-tertiary)]">
        {t('admin.hint', {
          defaultValue: 'Cache management is available to admin users only.',
        })}
      </p>
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
