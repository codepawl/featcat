/** Stacked horizontal bar where each segment's width is proportional to its
 *  `value`. Replaces the A/B/C/D grade distribution and certification-status
 *  bars duplicated across Dashboard / Groups.
 *
 *  Each segment with an `onClick` renders as a `<button>` so the bar is
 *  keyboard-clickable; segments without one stay as `<div>`s (decorative).
 *
 *  Audit reference: Pattern 9 (Score visualization / multi-segment bars).
 */

export interface SegmentedBarSegment {
  value: number
  /** Tailwind class or var-driven bg, e.g. 'bg-green-500' or 'bg-[var(--success)]'. */
  color: string
  /** Tooltip text via native `title=` (no custom tooltip needed). */
  label?: string
  /** When set, the segment renders as an interactive `<button>`. */
  onClick?: () => void
}

export interface SegmentedBarProps {
  segments: SegmentedBarSegment[]
  /** Visual height. Defaults to 6 (h-1.5). */
  height?: 4 | 6 | 16
  /** Rounded full pill (default true) or square corners. */
  rounded?: boolean
  /** Render zero-value segments at 0% width (still in the DOM). */
  showZero?: boolean
  /** Required — describes what the bar represents (a11y). */
  ariaLabel: string
}

const HEIGHT_CLASS: Record<NonNullable<SegmentedBarProps['height']>, string> = {
  4: 'h-1',
  6: 'h-1.5',
  16: 'h-4',
}

export function SegmentedBar({
  segments,
  height = 6,
  rounded = true,
  showZero = false,
  ariaLabel,
}: SegmentedBarProps) {
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.value), 0)
  const visible = showZero ? segments : segments.filter((s) => s.value > 0)
  const trackClass = `flex items-center gap-0 ${HEIGHT_CLASS[height]} ${rounded ? 'rounded-full' : 'rounded-sm'} overflow-hidden bg-[var(--bg-tertiary)]`

  return (
    <div role="img" aria-label={ariaLabel} className={trackClass}>
      {visible.map((segment, idx) => {
        const pct = total > 0 ? (Math.max(0, segment.value) / total) * 100 : 0
        const isInteractive = !!segment.onClick
        const baseClass = `h-full ${segment.color}`
        const interactiveClass = isInteractive ? ' hover:opacity-80 transition-opacity' : ''
        const style = { width: `${pct}%` }

        if (isInteractive) {
          return (
            <button
              key={idx}
              type="button"
              onClick={segment.onClick}
              title={segment.label}
              aria-label={segment.label ?? `Segment ${idx + 1}`}
              className={`${baseClass}${interactiveClass}`}
              style={style}
            />
          )
        }
        return (
          <div
            key={idx}
            title={segment.label}
            className={baseClass}
            style={style}
          />
        )
      })}
    </div>
  )
}
