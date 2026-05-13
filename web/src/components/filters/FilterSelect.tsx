/** Styled native <select> for filter rows. Generic over its value type so
 *  callers preserve enum type-safety (e.g. `'all' | 'local' | 's3'`).
 *
 *  Native <select> is intentional — keyboard nav and mobile touch sheets
 *  come for free, and filter dropdowns don't need virtualization or async
 *  options. If a future filter does need them, switch that one site to
 *  Radix Select; this component stays light.
 *
 *  Audit reference: Pattern 14 (Filter bar primitives).
 */

export interface FilterSelectOption<T extends string> {
  value: T
  label: string
}

export interface FilterSelectProps<T extends string> {
  value: T
  onChange: (value: T) => void
  options: FilterSelectOption<T>[]
  /** Provide an aria-label when no visible <label> wraps the select. */
  ariaLabel?: string
  className?: string
}

export function FilterSelect<T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: FilterSelectProps<T>) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      aria-label={ariaLabel}
      className={`bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none ${className ?? ''}`}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}
