/** Empty / error placeholder block: centered icon + title + optional
 *  description + optional CTA. Replaces ~18 inline copies across 8 pages
 *  (Sources, Search, Groups, Dashboard, Monitoring, Features, ...).
 *
 *  Single component for both empty and error variants — they share layout
 *  chrome; only the default icon and color tint differ.
 *
 *  Audit reference: Pattern 2 (EmptyState). The Dashboard error state at
 *  Dashboard.tsx:100-104 is the canonical `variant="error"` consumer.
 */

import type { LucideIcon } from 'lucide-react'
import { AlertTriangle, Inbox } from 'lucide-react'

export interface EmptyStateProps {
  /** `empty` (default) renders the muted-tertiary icon. `error` swaps the
   *  default icon for AlertTriangle and tints it with `--danger`. */
  variant?: 'empty' | 'error'
  /** Override the default icon for the variant. */
  icon?: LucideIcon
  title: string
  description?: string
  /** Optional CTA button — rendered as a brand-tinted text link to keep
   *  visual weight low (matches the Sources / Search empty-CTA pattern). */
  action?: { label: string; onClick: () => void }
  /** `bordered` wraps the block in a dashed-border card (Search pattern).
   *  `plain` (default) sits inline with no border. */
  surface?: 'plain' | 'bordered'
  /** `default` = py-8 (plain) / py-16 (bordered). `compact` = py-4. */
  size?: 'compact' | 'default'
}

const PADDING: Record<string, string> = {
  'plain-default': 'py-8',
  'plain-compact': 'py-4',
  'bordered-default': 'py-16',
  'bordered-compact': 'py-8',
}

export function EmptyState({
  variant = 'empty',
  icon,
  title,
  description,
  action,
  surface = 'plain',
  size = 'default',
}: EmptyStateProps) {
  const Icon = icon ?? (variant === 'error' ? AlertTriangle : Inbox)
  const iconColor = variant === 'error' ? 'text-[var(--danger)]' : 'text-[var(--text-tertiary)]'
  const padding = PADDING[`${surface}-${size}`]
  const wrapperClass =
    surface === 'bordered'
      ? `text-center ${padding} px-3 border border-dashed border-[var(--border-subtle)] rounded-xl`
      : `text-center ${padding} px-3`

  return (
    <div className={wrapperClass}>
      <Icon size={32} className={`mx-auto mb-2 ${iconColor}`} strokeWidth={1.5} />
      <p className="text-sm text-[var(--text-secondary)] mb-2">{title}</p>
      {description && (
        <p className="text-xs text-[var(--text-tertiary)] mb-2">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="text-xs text-brand hover:underline mt-1"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
