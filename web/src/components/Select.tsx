/**
 * Themed `<select>` replacement for the raw native dropdowns scattered
 * across the app (Jobs filters, MultiMetricTimeline range picker,
 * Sources filter+sort, Features definition-type editor, etc.).
 *
 * Implemented as a styled native `<select>` for the same reasons
 * FilterSelect already documents: keyboard nav, mobile touch sheets,
 * focus management, and screen-reader semantics all come for free
 * from the browser's built-in widget. The visible chrome (border,
 * padding, focus ring, custom chevron) matches the codebase's CSS
 * vars so the result feels native to the design system without
 * surrendering accessibility.
 *
 * FilterSelect (`web/src/components/filters/FilterSelect.tsx`) stays
 * — it's the filter-bar-specific variant; this `Select` is the
 * general-purpose form-field equivalent.
 *
 * API design (chosen from the audit)
 *   - `options`: `{value, label, disabled?}[]`. Generic over `T` so
 *     enum-typed callers preserve type-safety (e.g. `'sql' | 'python' |
 *     'manual'`).
 *   - `value` / `onChange(value)`: controlled string. onChange receives
 *     the unwrapped value, not an event.
 *   - `placeholder`: rendered as a disabled first option when supplied,
 *     so callers can express the "nothing chosen yet" state without
 *     introducing a sentinel `''` value.
 *   - `size`: `'sm'` (compact rows, default) | `'md'` (form fields).
 *   - `disabled`, `error`, `ariaLabel`, `className`, `data-testid`.
 *   - **No searchable variant.** None of the audited usages have more
 *     than ~10 options; if one ever does, switch THAT site to a
 *     dedicated combobox primitive rather than over-design this one.
 *
 * Keyboard: native — space/enter opens the menu, arrows navigate,
 * enter selects, escape closes. No custom event handling.
 *
 * Example
 *
 *     <Select<'sql' | 'python' | 'manual'>
 *       options={[
 *         { value: 'sql', label: 'SQL' },
 *         { value: 'python', label: 'Python' },
 *         { value: 'manual', label: 'Manual' },
 *       ]}
 *       value={defForm.definition_type}
 *       onChange={(v) => setDefForm((f) => ({ ...f, definition_type: v }))}
 *     />
 */

import { ChevronDown } from 'lucide-react'

type SelectSize = 'sm' | 'md'

export interface SelectOption<T extends string> {
  value: T
  label: string
  disabled?: boolean
}

export interface SelectProps<T extends string> {
  value: T | ''
  onChange: (value: T) => void
  options: SelectOption<T>[]
  placeholder?: string
  size?: SelectSize
  disabled?: boolean
  error?: boolean
  ariaLabel?: string
  className?: string
  'data-testid'?: string
}

const SIZE_CLASSES: Record<SelectSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs',
  md: 'px-3 py-2 text-[13px]',
}

export function Select<T extends string>({
  value,
  onChange,
  options,
  placeholder,
  size = 'sm',
  disabled,
  error,
  ariaLabel,
  className,
  ...rest
}: SelectProps<T>) {
  const borderClass = error
    ? 'border-[var(--danger)] focus:border-[var(--danger)]'
    : 'border-[var(--border-default)] focus:border-brand'

  return (
    <span className={`relative inline-block ${className ?? ''}`}>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-invalid={error ? true : undefined}
        data-testid={rest['data-testid']}
        className={`appearance-none bg-[var(--bg-primary)] border ${borderClass} rounded-lg ${SIZE_CLASSES[size]} pr-7 outline-none disabled:opacity-50 disabled:cursor-not-allowed w-full`}
      >
        {placeholder !== undefined && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} disabled={opt.disabled}>
            {opt.label}
          </option>
        ))}
      </select>
      <ChevronDown
        size={12}
        strokeWidth={2}
        aria-hidden
        className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] pointer-events-none"
      />
    </span>
  )
}
