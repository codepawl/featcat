/** Inline status banner (info / warning / danger / success). Replaces the
 *  ad-hoc `<p className="bg-[var(--danger-subtle-bg)] text-[var(--danger)] …">`
 *  blocks that bypass `<Badge>` (which is a pill, not a banner).
 *
 *  Dual-mode dismissal:
 *  - Controlled: pass `open` + `onOpenChange`; parent decides visibility.
 *  - Uncontrolled: omit `open`; the component hides itself when × is clicked.
 *
 *  Audit reference: Pattern 19 (open) — Alert.
 */

import { useControllableState } from '@radix-ui/react-use-controllable-state'
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

export type AlertSeverity = 'info' | 'warning' | 'danger' | 'success'

export interface AlertProps {
  severity: AlertSeverity
  message: ReactNode
  /** Show the matching lucide icon (default true). */
  icon?: boolean
  /** Render the × close button. */
  dismissible?: boolean
  /** Controlled visibility. When provided, parent owns state via onOpenChange. */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  /** Called when the × is clicked, regardless of controlled/uncontrolled. */
  onDismiss?: () => void
  /** Extra layout classes (e.g. `mb-4`) the caller applies from the outside. */
  className?: string
}

const ICONS: Record<AlertSeverity, LucideIcon> = {
  info: Info,
  warning: AlertTriangle,
  danger: AlertCircle,
  success: CheckCircle2,
}

const COLORS: Record<AlertSeverity, { text: string; bg: string; border: string }> = {
  info: {
    text: 'text-[var(--brand)]',
    bg: 'bg-[var(--brand-subtle-bg)]',
    border: 'border-[var(--brand-subtle-bg)]',
  },
  warning: {
    text: 'text-[var(--warning)]',
    bg: 'bg-[var(--warning-subtle-bg)]',
    border: 'border-[var(--warning-subtle-bg)]',
  },
  danger: {
    text: 'text-[var(--danger)]',
    bg: 'bg-[var(--danger-subtle-bg)]',
    border: 'border-[var(--danger-subtle-bg)]',
  },
  success: {
    text: 'text-[var(--success)]',
    bg: 'bg-[var(--success-subtle-bg)]',
    border: 'border-[var(--success-subtle-bg)]',
  },
}

export function Alert({
  severity,
  message,
  icon = true,
  dismissible = false,
  open,
  onOpenChange,
  onDismiss,
  className,
}: AlertProps) {
  const [visible, setVisible] = useControllableState({
    prop: open,
    defaultProp: true,
    onChange: onOpenChange,
  })
  if (!visible) return null

  const Icon = ICONS[severity]
  const colors = COLORS[severity]

  const handleDismiss = () => {
    onDismiss?.()
    setVisible(false)
  }

  return (
    <div
      role="alert"
      className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${colors.text} ${colors.bg} ${colors.border} ${className ?? ''}`}
    >
      {icon && <Icon size={16} className="shrink-0 mt-0.5" />}
      <div className="flex-1">{message}</div>
      {dismissible && <DismissButton onDismiss={handleDismiss} />}
    </div>
  )
}

function DismissButton({ onDismiss }: { onDismiss: () => void }) {
  const { t } = useTranslation('common')
  return (
    <button
      onClick={onDismiss}
      aria-label={t('actions.dismiss')}
      className="shrink-0 ml-1 hover:opacity-80"
    >
      <X size={14} />
    </button>
  )
}
