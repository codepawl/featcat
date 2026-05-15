import { useCallback, useEffect, useState } from 'react'
import { X } from 'lucide-react'

/**
 * Shared floating panel for detail views (feature detail, job run, group
 * detail dialog, etc.). Unifies the "centered overlay with header /
 * scrollable body / optional footer" pattern that previously lived
 * either as the `Modal` component (Features) or as bottom-docked inline
 * `<div>` panels (Jobs).
 *
 * After this PR, the project convention is:
 *
 *   All detail views (feature, group, job, source) use FloatingPanel.
 *   Do NOT introduce bottom panels, side drawers, or new modal patterns
 *   for detail views.
 *
 * (See CLAUDE.md > "UI conventions".)
 *
 * API
 *   - `open` / `onClose`: open state and ESC + backdrop-click handler.
 *   - `title`: header text (renders as a `<h2>`).
 *   - `subtitle`: optional, below the title in muted text.
 *   - `headerActions`: optional buttons / badges next to the close X.
 *   - `footer`: optional sticky footer slot (CTAs, cancel/save).
 *   - `size`: `'medium'` (default, max-w-2xl) or `'large'` (max-w-3xl).
 *     Sized to match the Features Modal and SchedulerOverview detail
 *     Modal which were the two largest panels in the codebase.
 *   - `children`: scrollable body content.
 *
 * Example
 *
 *     <FloatingPanel
 *       open={!!selected}
 *       onClose={() => setSelected(null)}
 *       title={selected?.name ?? ''}
 *       subtitle="src.col_a"
 *       size="large"
 *       footer={<button onClick={save}>Save</button>}
 *     >
 *       <Section title="Stats">{...}</Section>
 *     </FloatingPanel>
 *
 * Visual fidelity contract: the rendered DOM is identical to the prior
 * `Modal` component — same animation classes, same rounded-2xl, same
 * backdrop blur, same scroll behavior — so existing tests pinning that
 * shape pass unchanged.
 */

export type FloatingPanelSize = 'medium' | 'large'

interface FloatingPanelProps {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: React.ReactNode
  headerActions?: React.ReactNode
  footer?: React.ReactNode
  size?: FloatingPanelSize
  children: React.ReactNode
  /** Forwarded to the dialog root for tests + page anchoring. */
  'data-testid'?: string
}

const SIZE_CLASSES: Record<FloatingPanelSize, string> = {
  medium: 'max-w-2xl',
  large: 'max-w-3xl',
}

export function FloatingPanel({
  open,
  onClose,
  title,
  subtitle,
  headerActions,
  footer,
  size = 'medium',
  children,
  ...rest
}: FloatingPanelProps) {
  const [closing, setClosing] = useState(false)

  const handleClose = useCallback(() => {
    setClosing(true)
    // Match the prior Modal's 150ms exit animation duration so the close
    // animation visually lines up with the existing :animate-modal-out keyframe.
    setTimeout(onClose, 150)
  }, [onClose])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    if (open) document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, handleClose])

  useEffect(() => {
    if (open) setClosing(false)
  }, [open])

  if (!open) return null

  return (
    <div
      className={`fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 transition-opacity ${closing ? 'opacity-0' : 'opacity-100'}`}
      onClick={handleClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        data-testid={rest['data-testid']}
        className={`bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-2xl shadow-2xl ${SIZE_CLASSES[size]} w-[calc(100%-2rem)] sm:w-[90%] max-h-[85vh] sm:max-h-[80vh] flex flex-col ${closing ? 'animate-modal-out' : 'animate-modal-in'}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-5 sm:px-6 pt-5 pb-3 border-b border-[var(--border-subtle)] gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold truncate">{title}</h2>
            {subtitle !== undefined && (
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{subtitle}</p>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {headerActions}
            <button
              onClick={handleClose}
              aria-label="Close"
              className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors p-1 -mr-1 rounded-lg hover:bg-[var(--bg-tertiary)]"
              data-testid="floating-panel-close"
            >
              <X size={16} strokeWidth={1.8} />
            </button>
          </div>
        </div>
        <div className="px-5 sm:px-6 py-4 overflow-y-auto overscroll-contain flex-1">
          {children}
        </div>
        {footer !== undefined && (
          <div className="flex gap-2 justify-end px-5 sm:px-6 pb-4 pt-3 border-t border-[var(--border-subtle)]">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
