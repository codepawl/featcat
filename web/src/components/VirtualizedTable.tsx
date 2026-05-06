import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useTranslation } from 'react-i18next'

interface Column<T> {
  key: string
  label: string
  /** Disables the sort affordance; default true for headers. */
  sortable?: boolean
  render?: (row: T) => React.ReactNode
}

interface Props<T> {
  columns: Column<T>[]
  data: T[]
  onRowClick?: (row: T) => void
  /** Total matching rows across all pages — drives the "1-50 of 5234" display. */
  total: number
  limit: number
  offset: number
  onPageChange: (newOffset: number) => void
  /** Optional indicator while a page request is in flight; rows fade slightly. */
  loading?: boolean
  /** CSS height of the scroll viewport. Default 60vh. */
  viewportHeight?: string
}

const ROW_HEIGHT = 48 // T1.4 spec — fixed row height for the virtualizer

/**
 * Server-paginated, row-virtualized table.
 *
 * Renders ≤ ``limit`` rows from a single page; the virtualizer keeps the DOM
 * to ~window-height worth of <div> rows even when ``limit`` is 200+. Pagination
 * controls live at the bottom and signal back via ``onPageChange``.
 *
 * Intentionally simpler than ``DataTable``: no client-side sort or filter —
 * those are server-side responsibilities in the paginated path. Sorting
 * affordances on the header are visual hints; wire them to server params via
 * the parent's state if needed.
 */
// `Record<string, any>` matches DataTable's signature so call sites that
// already pass interface-typed rows (FeatureRow, GroupRow, etc.) work without
// adding index signatures to every shape. `unknown` here would force every
// caller to assert at the boundary; the small typing escape is paid once.
//
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function VirtualizedTable<T extends Record<string, any>>({
  columns,
  data,
  onRowClick,
  total,
  limit,
  offset,
  onPageChange,
  loading,
  viewportHeight = '60vh',
}: Props<T>) {
  const { t } = useTranslation('common')
  const parentRef = useRef<HTMLDivElement>(null)

  const virtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8, // render a small buffer above/below for smoother scrolling
  })

  const showingFrom = total === 0 ? 0 : offset + 1
  const showingTo = Math.min(offset + data.length, total)
  const isFirstPage = offset === 0
  const isLastPage = offset + limit >= total

  return (
    <div className={loading ? 'opacity-60 transition-opacity' : ''}>
      {/* Sticky header — kept outside the scroll container so it doesn't move
          with the virtualizer. Column widths use a CSS grid so cells line up
          between header and rows without measuring. */}
      <div
        className="grid border-b border-[var(--border-default)] bg-[var(--bg-primary)] text-[10px] uppercase tracking-[0.08em] text-[var(--text-tertiary)] font-semibold"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}
      >
        {columns.map((c) => (
          <div key={c.key} className="px-3 py-2.5 text-left truncate">
            {c.label}
          </div>
        ))}
      </div>

      {/* Virtualizer scroll container. Height is fixed so the virtualizer can
          decide what's visible. Inner div carries getTotalSize() so the
          scrollbar reflects the full row count. */}
      <div
        ref={parentRef}
        className="overflow-y-auto"
        style={{ height: viewportHeight }}
      >
        {data.length === 0 ? (
          <div className="px-3 py-10 text-center text-[var(--text-tertiary)] text-sm">
            {t('state.empty')}
          </div>
        ) : (
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative', width: '100%' }}>
            {virtualizer.getVirtualItems().map((vi) => {
              const row = data[vi.index]
              return (
                <div
                  key={vi.key}
                  className={`grid border-b border-[var(--border-subtle)] text-[13px] transition-colors ${
                    vi.index % 2 === 1 ? 'bg-[var(--bg-tertiary)]/[0.3]' : ''
                  } ${onRowClick ? 'cursor-pointer hover:bg-[var(--bg-secondary)]' : ''}`}
                  style={{
                    gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))`,
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    transform: `translateY(${vi.start}px)`,
                    height: ROW_HEIGHT,
                  }}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((c) => (
                    <div key={c.key} className="px-3 flex items-center min-w-0 truncate">
                      {c.render ? c.render(row) : String(row[c.key] ?? '')}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Pagination footer */}
      <div className="flex items-center justify-between gap-3 mt-3 text-xs text-[var(--text-tertiary)]">
        <div className="font-mono">
          {total === 0
            ? t('state.empty')
            : `${showingFrom.toLocaleString()}–${showingTo.toLocaleString()} / ${total.toLocaleString()}`}
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            disabled={isFirstPage}
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-30 hover:bg-[var(--bg-secondary)] transition-colors"
          >
            {t('actions.previous')}
          </button>
          <button
            type="button"
            disabled={isLastPage}
            onClick={() => onPageChange(offset + limit)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-30 hover:bg-[var(--bg-secondary)] transition-colors"
          >
            {t('actions.next')}
          </button>
        </div>
      </div>
    </div>
  )
}
