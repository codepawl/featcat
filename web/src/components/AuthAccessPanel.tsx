import { useEffect, useMemo, useState } from 'react'
import { api, invalidateCache, type AuthConfig, type AuthState } from '../api'

interface AuthAccessPanelProps {
  auth: AuthState | null
  onRetry: () => void
  onSignIn: (token: string) => Promise<void>
  onSignOut: () => Promise<void>
  fullScreen?: boolean
}

export function AuthAccessPanel({
  auth,
  onRetry,
  onSignIn,
  onSignOut,
  fullScreen = false,
}: AuthAccessPanelProps) {
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [mode, setMode] = useState<'company' | 'request' | 'token'>('company')
  const [token, setToken] = useState('')
  const [companyEmail, setCompanyEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [message, setMessage] = useState('')
  const [requesting, setRequesting] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)
  const [requestSuccess, setRequestSuccess] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.auth.config().then(setAuthConfig).catch(() => setAuthConfig(null))
  }, [])

  const allowedDomains = useMemo(() => {
    const domains = authConfig?.allowed_email_domains?.length ? authConfig.allowed_email_domains : ['fpt.com']
    return domains
  }, [authConfig])

  const primaryDomain = allowedDomains[0] ?? 'fpt.com'

  const submit = async () => {
    const next = token.trim()
    if (!next || busy) return
    setBusy(true)
    setError(null)
    try {
      await onSignIn(next)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  const submitRequest = async () => {
    const nextEmail = companyEmail.trim().toLowerCase()
    const suffix = `@${primaryDomain}`
    const isValid = nextEmail.length > suffix.length && nextEmail.endsWith(suffix) && nextEmail.includes('@')
    if (!isValid || requesting) return
    setRequesting(true)
    setRequestError(null)
    setRequestSuccess(null)
    try {
      await api.auth.requestAccess({
        email: nextEmail,
        display_name: displayName.trim() || undefined,
        message: message.trim() || undefined,
      })
      invalidateCache('/auth/access-requests')
      setRequestSuccess(`Request sent for ${nextEmail}. An admin will review it.`)
      setDisplayName('')
      setMessage('')
    } catch (e) {
      setRequestError(e instanceof Error ? e.message : 'Request failed')
    } finally {
      setRequesting(false)
    }
  }

  const requestSuffix = `@${primaryDomain}`

  const content = (
    <div className={`w-full ${fullScreen ? 'max-w-lg' : ''}`}>
      <div className={`${fullScreen ? 'rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-6 shadow-sm' : 'space-y-4'}`}>
        <div className="text-xs uppercase tracking-[0.2em] text-[var(--text-tertiary)]">Account</div>
        {auth?.user ? (
          <>
            <h2 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">Signed in</h2>
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              You are signed in as <span className="font-medium text-[var(--text-primary)]">{auth.user.email}</span>
              {' '}with the <span className="font-medium capitalize">{auth.user.role}</span> role.
              Use sign out if you want to switch accounts.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void onSignOut()}
                className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-brand text-white font-medium hover:brightness-110 transition"
              >
                Sign out
              </button>
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center justify-center h-10 px-4 rounded-lg border border-[var(--border-default)] text-[var(--text-primary)] font-medium hover:bg-[var(--bg-secondary)] transition"
              >
                Refresh
              </button>
            </div>
          </>
        ) : (
          <>
            <h1 className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
              {authConfig?.company_name ? `${authConfig.company_name} account` : 'Account'}
            </h1>
            <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
              The app is open to everyone. Use this panel only if you want to sign in with a company account,
              request a work-email account, or use an access token for an internal deployment.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setMode('company')}
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  mode === 'company'
                    ? 'bg-brand text-white border-brand'
                    : 'border-[var(--border-default)] hover:bg-[var(--bg-secondary)]'
                }`}
              >
                Company account
              </button>
              <button
                type="button"
                onClick={() => setMode('request')}
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  mode === 'request'
                    ? 'bg-brand text-white border-brand'
                    : 'border-[var(--border-default)] hover:bg-[var(--bg-secondary)]'
                }`}
              >
                Request access
              </button>
              <button
                type="button"
                onClick={() => setMode('token')}
                className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                  mode === 'token'
                    ? 'bg-brand text-white border-brand'
                    : 'border-[var(--border-default)] hover:bg-[var(--bg-secondary)]'
                }`}
              >
                Access token
              </button>
            </div>

            {mode === 'company' && (
              <div className="mt-5 space-y-3">
                <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-secondary)] p-4">
                  <p className="text-sm text-[var(--text-secondary)]">
                    Complete sign-in with your company identity provider first, then click Refresh here.
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={onRetry}
                      className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-brand text-white font-medium hover:brightness-110 transition"
                    >
                      Refresh
                    </button>
                    <button
                      type="button"
                      onClick={() => setMode('request')}
                      className="inline-flex items-center justify-center h-10 px-4 rounded-lg border border-[var(--border-default)] text-[var(--text-primary)] font-medium hover:bg-[var(--bg-primary)] transition"
                    >
                      Request access
                    </button>
                  </div>
                </div>
              </div>
            )}

            {mode === 'request' && (
              <div className="mt-5 space-y-3">
                <p className="text-sm text-[var(--text-secondary)]">
                  Request access with your work email. Only addresses ending in <span className="font-medium">{requestSuffix}</span>
                  {' '}are accepted.
                </p>
                <label className="block">
                  <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">Work email</span>
                  <input
                    value={companyEmail}
                    onChange={(e) => setCompanyEmail(e.target.value)}
                    placeholder={`you${requestSuffix}`}
                    className="mt-1 w-full h-10 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-sm outline-none focus:border-brand"
                  />
                </label>
                <label className="block">
                  <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">Display name</span>
                  <input
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="Your name"
                    className="mt-1 w-full h-10 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-sm outline-none focus:border-brand"
                  />
                </label>
                <label className="block">
                  <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">Message</span>
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={3}
                    placeholder="Team, project, or why you need access"
                    className="mt-1 w-full rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-sm outline-none focus:border-brand resize-none"
                  />
                </label>
                {requestError && <p className="text-xs text-[var(--danger)]">{requestError}</p>}
                {requestSuccess && <p className="text-xs text-[var(--success)]">{requestSuccess}</p>}
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={submitRequest}
                    disabled={requesting || !companyEmail.trim().toLowerCase().endsWith(requestSuffix)}
                    className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-brand text-white font-medium hover:brightness-110 transition disabled:opacity-50"
                  >
                    {requesting ? 'Sending…' : 'Request access'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode('company')}
                    className="inline-flex items-center justify-center h-10 px-4 rounded-lg border border-[var(--border-default)] text-[var(--text-primary)] font-medium hover:bg-[var(--bg-secondary)] transition"
                  >
                    Back to company login
                  </button>
                </div>
              </div>
            )}

            {mode === 'token' && (
              <div className="mt-5 space-y-3">
                <p className="text-sm leading-6 text-[var(--text-secondary)]">
                  Paste a bearer token if your deployment uses token-based access instead of SSO.
                </p>
                <label className="block">
                  <span className="sr-only">Access token</span>
                  <input
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="Access token"
                    className="w-full h-10 rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 text-sm outline-none focus:border-brand"
                  />
                </label>
                {error && <p className="text-xs text-[var(--danger)]">{error}</p>}
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={submit}
                    disabled={busy || !token.trim()}
                    className="inline-flex items-center justify-center h-10 px-4 rounded-lg bg-brand text-white font-medium hover:brightness-110 transition disabled:opacity-50"
                  >
                    {busy ? 'Signing in…' : 'Sign in'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setMode('company')}
                    className="inline-flex items-center justify-center h-10 px-4 rounded-lg border border-[var(--border-default)] text-[var(--text-primary)] font-medium hover:bg-[var(--bg-secondary)] transition"
                  >
                    Back to company login
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )

  if (fullScreen) {
    return <div className="min-h-screen flex items-center justify-center p-6">{content}</div>
  }

  return content
}
