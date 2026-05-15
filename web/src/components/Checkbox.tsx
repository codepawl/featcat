import { useEffect, useId, useRef } from 'react'

/**
 * Themed checkbox replacement for the raw `<input type="checkbox">` pattern
 * scattered across the app (regenerate-docs modal, bulk-scan modal,
 * various filter rows). Built on top of the native checkbox so keyboard
 * accessibility comes for free — space toggles, tab focuses, screen
 * readers announce state — but the visible chrome (checkmark, focus
 * ring, error state) is styled with the codebase's existing CSS vars.
 *
 * API design (chosen from the audit, not theory)
 *   - `checked` / `onCheckedChange`: controlled toggle. `onCheckedChange`
 *     receives the new boolean directly (no need to read `e.target.checked`
 *     on every call site — that pattern was repeated everywhere).
 *   - `label`: optional. When provided, the whole row is clickable
 *     (label wraps the input) so list-row use cases stop needing their
 *     own click-wrappers.
 *   - `description`: small text below the label.
 *   - `indeterminate`: true → renders the "−" tri-state glyph (used by
 *     FeatureSelector's select-all-on-page header cell).
 *   - `disabled`, `error`: standard control flags.
 *   - `variant`: `'default'` (standalone form field) | `'compact'`
 *     (in-list, smaller box, tighter row).
 *   - `data-testid`: forwarded to the wrapping `<label>`.
 *
 * Example
 *
 *     <Checkbox
 *       label="Recursive scan"
 *       description="Walk subdirectories"
 *       checked={form.recursive}
 *       onCheckedChange={(v) => setForm((f) => ({ ...f, recursive: v }))}
 *     />
 */

type CheckboxVariant = 'default' | 'compact'

export interface CheckboxProps {
  checked: boolean
  onCheckedChange: (checked: boolean) => void
  label?: React.ReactNode
  description?: React.ReactNode
  indeterminate?: boolean
  disabled?: boolean
  error?: boolean
  variant?: CheckboxVariant
  className?: string
  'aria-label'?: string
  'data-testid'?: string
}

const BOX_SIZE: Record<CheckboxVariant, string> = {
  default: 'size-4',
  compact: 'size-3.5',
}

export function Checkbox({
  checked,
  onCheckedChange,
  label,
  description,
  indeterminate,
  disabled,
  error,
  variant = 'default',
  className,
  ...rest
}: CheckboxProps) {
  const id = useId()
  const inputRef = useRef<HTMLInputElement>(null)

  // The indeterminate state isn't an HTML attribute — it lives on the
  // DOM element only. Wire it imperatively after every render so a
  // parent flipping the prop syncs the visual "—" glyph.
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.indeterminate = !!indeterminate
    }
  }, [indeterminate])

  const Wrapper = label !== undefined || description !== undefined ? 'label' : 'span'
  const wrapperClass =
    variant === 'compact'
      ? 'inline-flex items-start gap-1.5 text-[12px]'
      : 'inline-flex items-start gap-2 text-[13px]'

  return (
    <Wrapper
      htmlFor={Wrapper === 'label' ? id : undefined}
      data-testid={rest['data-testid']}
      className={`${wrapperClass} ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'} ${className ?? ''}`}
    >
      <input
        ref={inputRef}
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={rest['aria-label']}
        aria-invalid={error ? true : undefined}
        onChange={(e) => onCheckedChange(e.target.checked)}
        className={`${BOX_SIZE[variant]} shrink-0 rounded border ${
          error
            ? 'border-[var(--danger)] focus:border-[var(--danger)]'
            : 'border-[var(--border-default)] focus:border-brand'
        } bg-[var(--bg-primary)] text-brand accent-brand outline-none focus:ring-2 focus:ring-brand/30 disabled:cursor-not-allowed`}
      />
      {(label !== undefined || description !== undefined) && (
        <span className="min-w-0">
          {label !== undefined && (
            <span className={`block ${error ? 'text-[var(--danger)]' : 'text-[var(--text-primary)]'}`}>
              {label}
            </span>
          )}
          {description !== undefined && (
            <span className="block text-[11px] text-[var(--text-tertiary)] mt-0.5">
              {description}
            </span>
          )}
        </span>
      )}
    </Wrapper>
  )
}
