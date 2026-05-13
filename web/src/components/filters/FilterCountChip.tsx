/** Small muted chip showing a count + optional label, e.g. "120 features"
 *  next to a filter row. Sits in the same visual slot Audit / Jobs use today.
 *
 *  Audit reference: Pattern 14 (Filter bar primitives).
 */

export interface FilterCountChipProps {
  count: number
  /** Suffix label, e.g. "features". Omit for a count-only chip. */
  label?: string
}

export function FilterCountChip({ count, label }: FilterCountChipProps) {
  return (
    <span className="text-xs text-[var(--text-tertiary)]">
      {count}
      {label && ` ${label}`}
    </span>
  )
}
