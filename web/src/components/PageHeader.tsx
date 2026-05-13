/** Page-level header: title (optionally with subtitle) on the left, free-form
 *  actions on the right. Replaces the `flex justify-between items-center mb-6
 *  + h1 + button cluster` pattern that was inlined on 17 pages.
 *
 *  Audit reference: docs/audits — Pattern 11 (Page header layout).
 */

import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: string
  /** Optional secondary line. When present, the title cluster wraps in its
   *  own div so the action row stays vertically centered against the title. */
  subtitle?: string
  /** Right-side action slot (typically a button or button group). */
  actions?: ReactNode
  /** `default` = text-2xl (most pages); `compact` = text-xl (Audit / Actions). */
  size?: 'default' | 'compact'
}

const TITLE_SIZE: Record<NonNullable<PageHeaderProps['size']>, string> = {
  default: 'text-2xl',
  compact: 'text-xl',
}

export function PageHeader({ title, subtitle, actions, size = 'default' }: PageHeaderProps) {
  return (
    <div className="flex justify-between items-center mb-6">
      <div>
        <h1 className={`${TITLE_SIZE[size]} font-semibold`}>{title}</h1>
        {subtitle && (
          <p className="text-sm text-[var(--text-tertiary)] mt-0.5">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}
