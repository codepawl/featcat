import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, ChevronDown, XCircle } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { Modal } from './Modal'

/**
 * Feature lifecycle status. Mirrors `featcat.catalog.local.LocalBackend
 * .VALID_STATUSES` and the server-side `StatusChangeRequest` enum.
 */
export type FeatureStatus = 'draft' | 'reviewed' | 'certified' | 'deprecated'

export const FEATURE_STATUSES: readonly FeatureStatus[] = [
  'draft',
  'reviewed',
  'certified',
  'deprecated',
] as const

/**
 * Pill / badge styles per status. Matches the four-color spec the goal
 * calls for (gray / blue / green / red) using the same semantic CSS
 * variables Features.tsx already uses, so dark/light themes pick up
 * the right contrast without per-variant overrides.
 */
export const STATUS_PILL_CLASSES: Record<FeatureStatus, string> = {
  draft:
    'bg-[var(--bg-tertiary)] text-[var(--text-tertiary)] border border-transparent',
  reviewed:
    'bg-[var(--brand-subtle-bg)] text-[var(--brand)] border border-[var(--brand-subtle-bg)]',
  certified:
    'bg-[var(--success-subtle-bg)] text-[var(--success)] border border-[var(--success-subtle-bg)]',
  deprecated:
    'bg-[var(--danger-subtle-bg)] text-[var(--danger)] border border-[var(--danger-subtle-bg)] line-through',
}

interface StatusBadgeProps {
  status: FeatureStatus | null | undefined
  className?: string
}

/**
 * Display-only status pill. NULL status defaults to 'draft' so legacy
 * features (pre-T3.1 migration) render the same as an explicit draft —
 * the spec calls this out as the empty-state behavior.
 */
export function FeatureStatusBadge({ status, className }: StatusBadgeProps) {
  const { t } = useTranslation('features')
  const resolved: FeatureStatus = status ?? 'draft'
  return (
    <span
      data-testid="feature-status-badge"
      data-status={resolved}
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium ${STATUS_PILL_CLASSES[resolved]} ${className ?? ''}`}
    >
      {t(`status.${resolved}`)}
    </span>
  )
}

interface TransitionProps {
  featureName: string
  current: FeatureStatus | null | undefined
  onTransitioned: (newStatus: FeatureStatus) => void
  disabled?: boolean
}

interface ReadinessState {
  ready: boolean
  missing: string[]
}

/**
 * Three-piece component: status badge + "Change status" dropdown +
 * confirm modal (one of two flavors — the certified flavor first
 * fetches the readiness checklist and blocks confirm if any item
 * is missing; the other targets just show a notes textarea).
 *
 * Wiring contract:
 *   - `current` is the source-of-truth status from the parent.
 *   - On success the component calls `onTransitioned(target)` so the
 *     parent can update its in-memory feature row + invalidate caches.
 *   - Cache invalidation is done here for the local detail endpoints
 *     that the modal owns (`/features`, `/features/by-name`).
 */
export function FeatureStatusTransition({
  featureName,
  current,
  onTransitioned,
  disabled = false,
}: TransitionProps) {
  const { t } = useTranslation('features')
  const [menuOpen, setMenuOpen] = useState(false)
  const [target, setTarget] = useState<FeatureStatus | null>(null)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [readiness, setReadiness] = useState<ReadinessState | null>(null)
  const [readinessLoading, setReadinessLoading] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const resolvedCurrent: FeatureStatus = current ?? 'draft'

  // Close dropdown on outside click. Pointerdown beats click for both
  // mouse and touch with one listener.
  useEffect(() => {
    if (!menuOpen) return
    const onOutside = (e: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('pointerdown', onOutside)
    return () => document.removeEventListener('pointerdown', onOutside)
  }, [menuOpen])

  const openTarget = async (s: FeatureStatus): Promise<void> => {
    if (disabled) return
    setMenuOpen(false)
    setNotes('')
    setError(null)
    setReadiness(null)
    setTarget(s)
    if (s === 'certified') {
      setReadinessLoading(true)
      try {
        const r = await api.features.certificationReadiness(featureName)
        setReadiness(r)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
        setReadiness({ ready: false, missing: [] })
      } finally {
        setReadinessLoading(false)
      }
    }
  }

  const cancel = (): void => {
    if (submitting) return
    setTarget(null)
    setNotes('')
    setError(null)
    setReadiness(null)
  }

  const confirm = async (): Promise<void> => {
    if (!target) return
    setSubmitting(true)
    setError(null)
    try {
      const trimmed = notes.trim()
      await api.features.setStatus(featureName, {
        status: target,
        notes: trimmed.length > 0 ? trimmed : null,
      })
      invalidateCache('/features')
      invalidateCache(`/features/by-name?name=${encodeURIComponent(featureName)}`)
      onTransitioned(target)
      setTarget(null)
      setNotes('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  const alternatives = FEATURE_STATUSES.filter((s) => s !== resolvedCurrent)
  const isCertifyTarget = target === 'certified'
  const blockConfirm =
    submitting ||
    (isCertifyTarget && (readinessLoading || !readiness || !readiness.ready))

  return (
    <div className="flex items-center gap-2" ref={menuRef}>
      <FeatureStatusBadge status={resolvedCurrent} />
      <div className="relative">
        <button
          type="button"
          onClick={() => {
            if (disabled) return
            setMenuOpen((v) => !v)
          }}
          disabled={disabled}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full border border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
          data-testid="feature-status-change-button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
        >
          {t('status_actions.change', { defaultValue: 'Change status' })}
          <ChevronDown size={11} aria-hidden />
        </button>
        {menuOpen && !disabled && (
          <div
            role="menu"
            data-testid="feature-status-menu"
            className="absolute z-30 mt-1 right-0 min-w-[150px] bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-lg py-1"
          >
            {FEATURE_STATUSES.map((s) => {
              const disabled = s === resolvedCurrent
              return (
                <button
                  key={s}
                  type="button"
                  role="menuitem"
                  disabled={disabled}
                  onClick={() => void openTarget(s)}
                  className={`w-full text-left px-3 py-1.5 text-[12px] flex items-center justify-between gap-3 ${
                    disabled
                      ? 'text-[var(--text-tertiary)] cursor-not-allowed'
                      : 'text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]'
                  }`}
                  data-testid={`feature-status-option-${s}`}
                  data-current={disabled || undefined}
                >
                  <span>{t(`status.${s}`)}</span>
                  {disabled && (
                    <span className="text-[10px] uppercase tracking-wider text-[var(--text-tertiary)]">
                      {t('status_actions.current', { defaultValue: 'current' })}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </div>

      {target !== null && (
        <Modal
          open
          onClose={cancel}
          title={t('status_actions.modal_title', {
            defaultValue: 'Change status to {{status}}',
            status: t(`status.${target}`),
          })}
          actions={
            <>
              <button
                onClick={cancel}
                disabled={submitting}
                className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg disabled:opacity-50"
              >
                {t('actions.cancel', { ns: 'common' })}
              </button>
              <button
                onClick={() => void confirm()}
                disabled={blockConfirm}
                className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50"
                data-testid="feature-status-confirm"
              >
                {submitting
                  ? t('status_actions.applying', { defaultValue: 'Applying…' })
                  : t('status_actions.confirm', { defaultValue: 'Confirm' })}
              </button>
            </>
          }
        >
          {isCertifyTarget ? (
            <ReadinessChecklist
              loading={readinessLoading}
              readiness={readiness}
              notes={notes}
              onNotesChange={setNotes}
            />
          ) : (
            <NotesField notes={notes} onChange={setNotes} />
          )}
          {error && (
            <p className="mt-3 text-[12px] text-[var(--danger)] bg-[var(--danger-subtle-bg)] rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </Modal>
      )}
    </div>
  )
}

function NotesField({
  notes,
  onChange,
}: {
  notes: string
  onChange: (v: string) => void
}) {
  const { t } = useTranslation('features')
  return (
    <div>
      <label className="block text-xs font-medium mb-1 text-[var(--text-secondary)]">
        {t('status_actions.notes_label', { defaultValue: 'Notes (optional)' })}
      </label>
      <textarea
        value={notes}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        placeholder={t('status_actions.notes_placeholder', {
          defaultValue: 'Why this transition?',
        })}
        className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
        data-testid="feature-status-notes"
      />
    </div>
  )
}

function ReadinessChecklist({
  loading,
  readiness,
  notes,
  onNotesChange,
}: {
  loading: boolean
  readiness: ReadinessState | null
  notes: string
  onNotesChange: (v: string) => void
}) {
  const { t } = useTranslation('features')

  // Stable list of checklist items the server may report missing. Each
  // appears with a pass/fail icon regardless of whether the server names
  // it in `missing`, so the operator sees the full gate.
  const ITEMS = [
    'documentation',
    'data_source',
    'baseline',
    'owner',
    'group_membership_or_standalone',
  ] as const

  if (loading) {
    return (
      <p className="text-sm text-[var(--text-tertiary)] py-4">
        {t('status_actions.checking_readiness', {
          defaultValue: 'Checking certification readiness…',
        })}
      </p>
    )
  }

  if (!readiness) {
    return (
      <p className="text-sm text-[var(--danger)] py-4">
        {t('status_actions.readiness_failed', {
          defaultValue: 'Could not load readiness checklist',
        })}
      </p>
    )
  }

  const missing = new Set(readiness.missing)

  return (
    <div className="space-y-3">
      <p className="text-[13px] text-[var(--text-secondary)]">
        {readiness.ready
          ? t('status_actions.ready_intro', {
              defaultValue: 'All checks passed — ready to certify.',
            })
          : t('status_actions.not_ready_intro', {
              defaultValue: 'Some checks are failing. Fix them before certifying.',
            })}
      </p>
      <ul
        className="space-y-1.5"
        data-testid="feature-status-readiness-checklist"
      >
        {ITEMS.map((item) => {
          const failed = missing.has(item)
          return (
            <li
              key={item}
              data-testid={`feature-status-readiness-${item}`}
              data-failed={failed || undefined}
              className="flex items-center gap-2 text-[13px]"
            >
              {failed ? (
                <XCircle size={14} className="text-[var(--danger)]" aria-hidden />
              ) : (
                <CheckCircle2
                  size={14}
                  className="text-[var(--success)]"
                  aria-hidden
                />
              )}
              <span
                className={failed ? 'text-[var(--danger)]' : 'text-[var(--text-primary)]'}
              >
                {t(`status_actions.readiness_items.${item}`, {
                  defaultValue: item.replace(/_/g, ' '),
                })}
              </span>
            </li>
          )
        })}
      </ul>
      <NotesField notes={notes} onChange={onNotesChange} />
    </div>
  )
}
