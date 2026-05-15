import type { ReactNode } from 'react'

/**
 * Shared panel-style card for section wrappers.
 *
 * Replaces the repeating
 *   `<div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)]
 *                    rounded-xl p-5">`
 * pattern that lives inline across Jobs, Audit, Monitoring, Sources,
 * GroupDetail, and more. The audit (see PR body) found this shape was
 * the most-divergent class of "card" in the codebase — sometimes p-5,
 * sometimes p-3 with no padding override, sometimes wrapped in a header
 * row with a title + actions, sometimes plain.
 *
 * API design (chosen from existing usage, not from theory):
 *   - `title`: optional section heading, rendered as a `<h3>` so the
 *     headings hierarchy stays consistent.
 *   - `actions`: optional right-aligned slot in the header row. Buttons,
 *     selects, badges all fit.
 *   - `padding`: `'normal'` (default, p-5 — the predominant choice) or
 *     `'compact'` (p-3, used for list-row groupings) or `'none'` (lets
 *     callers embed a table flush to the border).
 *   - `border`: `'subtle'` (default) or `'default'` (stronger border for
 *     interactive panels like Jobs filter controls).
 *   - `className`: passthrough for layout tweaks (mb-4, flex-1, etc.).
 *   - `data-testid`: forwarded for tests + page anchoring.
 *
 * Example:
 *
 *     <Card title="Execution History" actions={<FilterChips />}>
 *       <DataTable columns={cols} data={rows} />
 *     </Card>
 *
 * Visual fidelity contract: the rendered DOM must be visually
 * indistinguishable from the inline pattern it replaces. New variants
 * are added via props, NEVER via subclassing this component.
 */

type CardPadding = 'normal' | 'compact' | 'none'
type CardBorder = 'subtle' | 'default'

export interface CardProps {
  title?: ReactNode
  /** Right-aligned content in the header row (filters, buttons, badges). */
  actions?: ReactNode
  /** Header-row override when `title` + `actions` aren't enough (rare). */
  header?: ReactNode
  padding?: CardPadding
  border?: CardBorder
  className?: string
  children?: ReactNode
  /** Forwarded to the outer `<section>` element. */
  'data-testid'?: string
}

const PADDING_CLASSES: Record<CardPadding, string> = {
  normal: 'p-5',
  compact: 'p-3',
  none: '',
}

const BORDER_CLASSES: Record<CardBorder, string> = {
  subtle: 'border border-[var(--border-subtle)]',
  default: 'border border-[var(--border-default)]',
}

export function Card({
  title,
  actions,
  header,
  padding = 'normal',
  border = 'subtle',
  className,
  children,
  ...rest
}: CardProps) {
  const showHeader = header !== undefined || title !== undefined || actions !== undefined
  return (
    <section
      data-testid={rest['data-testid']}
      className={`bg-[var(--bg-primary)] ${BORDER_CLASSES[border]} rounded-xl ${PADDING_CLASSES[padding]} ${className ?? ''}`}
    >
      {showHeader && (
        <div className="flex items-center justify-between gap-2 flex-wrap mb-4 last:mb-0">
          {header ?? (
            <>
              {title !== undefined && (
                <h3 className="text-sm font-semibold">{title}</h3>
              )}
              {actions !== undefined && (
                <div className="flex items-center gap-2 flex-wrap">{actions}</div>
              )}
            </>
          )}
        </div>
      )}
      {children}
    </section>
  )
}
