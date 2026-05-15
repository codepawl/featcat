import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronUp, ChevronDown } from 'lucide-react'

/**
 * Shared table component for paginated, sortable lists.
 *
 * `DataTable` is the canonical table abstraction in the codebase.
 * Already-shared consumers: Features (default unpaginated path), Groups
 * (members), GroupDetail (members). This PR adds Audit (version history)
 * as the 4th, migrating it off a hand-rolled `<table>` element.
 *
 * API design (chosen from existing usage, not from theory):
 *   - `columns`: `{key, label, sortable?, render?, headerRender?}[]`.
 *     `sortable` defaults to true; pass `false` for columns with mixed
 *     types (badges, buttons). `render` returns ReactNode per row;
 *     `headerRender` is used by FeatureSelector's tri-state checkbox.
 *   - `data`: row records keyed by string. Sort uses `row[col.key]`
 *     natively — numeric subtract for numbers, `localeCompare` for the rest.
 *   - `onRowClick(row)`: optional. Adds cursor-pointer + hover styling.
 *   - `pageSize`: default 25. Set higher when virtualisation would be
 *     overkill but the row count is bounded (members lists).
 *
 * Empty state, sort indicator (Chevron up/down), and pagination
 * (prev/next + "page / total") are built-in — call sites get them for
 * free.
 *
 * Example:
 *
 *     <DataTable
 *       columns={[
 *         { key: 'when', label: t('table.when'),
 *           render: (r) => timeAgo(r.created_at) },
 *         { key: 'feature_name', label: t('table.feature'),
 *           render: (r) => <span className="text-brand">{r.feature_name}</span> },
 *       ]}
 *       data={rows}
 *       onRowClick={(r) => navigate(\`/features/\${r.feature_name}\`)}
 *     />
 *
 * Variants observed during the audit (PR body lists each one) and
 * supported by the current API:
 *   - Plain (Features unpaginated): no row-click, default sort
 *   - Row-clickable (Audit, Groups members): pass `onRowClick`
 *   - Header-renderable cells (FeatureSelector, ExportModal): use
 *     `headerRender`
 *   - Sortable-some-columns (every consumer): `sortable: false` per col
 *
 * Variants NOT yet supported and deferred to a follow-up PR (paired
 * with the FloatingPanel work):
 *   - Expandable rows (Jobs history table — coupled to row-detail
 *     overlay state)
 *   - Selected-row side panel (Monitoring drift table — coupled to
 *     framer-motion AnimatePresence)
 */

interface Column<T> {
  key: string
  label: string
  sortable?: boolean
  render?: (row: T) => React.ReactNode
  /** Optional override for the header cell content (e.g. tri-state checkbox). */
  headerRender?: () => React.ReactNode
}

interface Props<T> {
  columns: Column<T>[]
  data: T[]
  onRowClick?: (row: T) => void
  pageSize?: number
}

export function DataTable<T extends Record<string, any>>({ columns, data, onRowClick, pageSize = 25 }: Props<T>) {
  const { t } = useTranslation('common')
  const [sortCol, setSortCol] = useState('')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(0)

  const sorted = useMemo(() => {
    if (!sortCol) return data
    return [...data].sort((a, b) => {
      const av = a[sortCol] ?? '', bv = b[sortCol] ?? ''
      const cmp = typeof av === 'number' ? av - (bv as number) : String(av).localeCompare(String(bv))
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [data, sortCol, sortDir])

  const paged = sorted.slice(page * pageSize, (page + 1) * pageSize)
  const totalPages = Math.ceil(sorted.length / pageSize)

  const toggleSort = (key: string) => {
    if (sortCol === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(key); setSortDir('asc') }
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px] min-w-[480px]">
          <thead>
            <tr>
              {columns.map(c => (
                <th
                  key={c.key}
                  className={`text-left px-3 py-2.5 text-[10px] uppercase tracking-[0.08em] text-[var(--text-tertiary)] font-semibold border-b border-[var(--border-default)] ${c.sortable !== false ? 'cursor-pointer select-none hover:text-[var(--text-secondary)] transition-colors' : ''}`}
                  onClick={() => c.sortable !== false && toggleSort(c.key)}
                >
                  <span className="inline-flex items-center gap-1">
                    {c.headerRender ? c.headerRender() : c.label}
                    {sortCol === c.key && (
                      sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-[var(--border-subtle)] transition-colors ${
                  i % 2 === 1 ? 'bg-[var(--bg-tertiary)]/[0.3]' : ''
                } ${onRowClick ? 'cursor-pointer hover:bg-[var(--bg-secondary)]' : ''}`}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map(c => (
                  <td key={c.key} className="px-3 py-2.5">
                    {c.render ? c.render(row) : String(row[c.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
            {paged.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-10 text-center text-[var(--text-tertiary)] text-sm">
                  {t('state.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex gap-1 justify-center mt-4">
          <button disabled={page === 0} onClick={() => setPage(p => p - 1)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-30 hover:bg-[var(--bg-secondary)] transition-colors">
            {t('actions.previous')}
          </button>
          <span className="px-3 py-1.5 text-xs text-[var(--text-tertiary)] font-mono">{page + 1} / {totalPages}</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-[var(--border-default)] bg-[var(--bg-primary)] disabled:opacity-30 hover:bg-[var(--bg-secondary)] transition-colors">
            {t('actions.next')}
          </button>
        </div>
      )}
    </div>
  )
}
