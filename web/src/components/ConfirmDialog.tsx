/** Modal-backed confirmation dialog for destructive (and other) actions.
 *  Composes `<Modal>` (no parallel dialog stack); adds opinionated:
 *  - severity-styled confirm button
 *  - async-aware pending state (label swap + both buttons disabled while
 *    onConfirm() returns a promise that hasn't settled)
 *  - optional "type X to confirm" gate (case-sensitive, trimmed)
 *  - optional checkbox-acknowledgment gate
 *  - default focus on Cancel (or on the text-match input when set) so an
 *    accidental Enter never destroys data
 *
 *  Audit reference: Pattern 1 (Confirmation dialog). Sources delete is the
 *  reference consumer for requireTextMatch.
 */

import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { ReactNode } from 'react'
import { Modal } from './Modal'

export interface ConfirmDialogProps {
  open: boolean
  onClose: () => void
  title: string
  /** Body content above the controls (e.g. impact summary, group list). */
  message?: ReactNode
  /** Red callout shown under the message (e.g. "This action cannot be undone."). */
  warning?: string
  severity?: 'destructive' | 'warning' | 'info'
  confirmLabel: string
  /** Label while onConfirm() is pending. Defaults to confirmLabel + "…". */
  pendingLabel?: string
  /** Defaults to t('actions.cancel', { ns: 'common' }). */
  cancelLabel?: string
  /** When set, user must type `value` exactly to enable the confirm button. */
  requireTextMatch?: { value: string; label: string }
  /** When set, user must tick a checkbox with this label to enable confirm. */
  requireCheckbox?: string
  onConfirm: () => void | Promise<void>
}

const CONFIRM_BG: Record<NonNullable<ConfirmDialogProps['severity']>, string> = {
  destructive: 'bg-[var(--danger)]',
  warning: 'bg-[var(--warning)]',
  info: 'bg-brand',
}

export function ConfirmDialog({
  open,
  onClose,
  title,
  message,
  warning,
  severity = 'destructive',
  confirmLabel,
  pendingLabel,
  cancelLabel,
  requireTextMatch,
  requireCheckbox,
  onConfirm,
}: ConfirmDialogProps) {
  const { t } = useTranslation('common')
  const [pending, setPending] = useState(false)
  const [typed, setTyped] = useState('')
  const [acknowledged, setAcknowledged] = useState(false)
  const cancelRef = useRef<HTMLButtonElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const textInputId = useId()
  const checkboxId = useId()

  // Reset internal state each time the dialog reopens.
  useEffect(() => {
    if (open) {
      setPending(false)
      setTyped('')
      setAcknowledged(false)
    }
  }, [open])

  // Default focus: text input if present, otherwise cancel button.
  useEffect(() => {
    if (!open) return
    const id = requestAnimationFrame(() => {
      if (requireTextMatch && inputRef.current) {
        inputRef.current.focus()
      } else {
        cancelRef.current?.focus()
      }
    })
    return () => cancelAnimationFrame(id)
  }, [open, requireTextMatch])

  const textMatched = !requireTextMatch || typed.trim() === requireTextMatch.value
  const checkboxPassed = !requireCheckbox || acknowledged
  const canConfirm = !pending && textMatched && checkboxPassed

  const handleConfirm = async () => {
    if (!canConfirm) return
    try {
      const result = onConfirm()
      if (result instanceof Promise) {
        setPending(true)
        await result
      }
    } finally {
      setPending(false)
    }
  }

  const confirmButtonClass = `px-4 py-2 text-sm text-white rounded-lg disabled:opacity-50 ${CONFIRM_BG[severity]}`
  const effectivePendingLabel = pendingLabel ?? `${confirmLabel}…`

  return (
    <Modal
      open={open}
      onClose={pending ? () => {} : onClose}
      title={title}
      actions={
        <>
          <button
            ref={cancelRef}
            onClick={onClose}
            disabled={pending}
            className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg disabled:opacity-50"
          >
            {cancelLabel ?? t('actions.cancel')}
          </button>
          <button
            onClick={handleConfirm}
            disabled={!canConfirm}
            className={confirmButtonClass}
          >
            {pending ? effectivePendingLabel : confirmLabel}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        {message && <div className="text-sm">{message}</div>}
        {warning && (
          <p className="text-[12px] text-[var(--danger)] bg-[var(--danger-subtle-bg)] rounded-lg px-3 py-2">
            {warning}
          </p>
        )}
        {requireTextMatch && (
          <div>
            <label htmlFor={textInputId} className="block text-xs font-medium mb-1">
              {requireTextMatch.label}
            </label>
            <input
              ref={inputRef}
              id={textInputId}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] font-mono focus:border-brand outline-none"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        )}
        {requireCheckbox && (
          <label htmlFor={checkboxId} className="flex items-start gap-2 text-[13px] cursor-pointer select-none">
            <input
              id={checkboxId}
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-0.5"
            />
            <span>{requireCheckbox}</span>
          </label>
        )}
      </div>
    </Modal>
  )
}
