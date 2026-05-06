import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '../Skeleton'

interface DocDebtEntry {
  owner: string
  source: string
  total: number
  undocumented: number
  pct_undocumented: number
}

interface DocDebtHeatmapProps {
  data: DocDebtEntry[]
  loading: boolean
}

function debtColor(pct: number): string {
  if (pct === 0) return 'bg-transparent'
  if (pct <= 25) return 'bg-amber-100 dark:bg-amber-900/30'
  if (pct <= 50) return 'bg-amber-200 dark:bg-amber-800/40'
  if (pct <= 75) return 'bg-orange-300 dark:bg-orange-700/50'
  return 'bg-red-400 dark:bg-red-700/60'
}

export function DocDebtHeatmap({ data, loading }: DocDebtHeatmapProps) {
  const { t } = useTranslation('dashboard')
  const navigate = useNavigate()

  if (loading) return <Skeleton className="h-48" />

  if (data.length === 0) {
    return (
      <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
        <h3 className="text-sm font-semibold mb-1">{t('debt.title')}</h3>
        <p className="text-[var(--text-tertiary)] text-sm">{t('debt.empty')}</p>
      </div>
    )
  }

  // Build grid: rows = owners, columns = sources
  const owners = [...new Set(data.map(d => d.owner))].sort()
  const sources = [...new Set(data.map(d => d.source))].sort()
  const lookup = new Map(data.map(d => [`${d.owner}::${d.source}`, d]))

  // Compute row totals
  const rowTotals = new Map<string, { total: number; undoc: number }>()
  for (const owner of owners) {
    let total = 0, undoc = 0
    for (const src of sources) {
      const entry = lookup.get(`${owner}::${src}`)
      if (entry) { total += entry.total; undoc += entry.undocumented }
    }
    rowTotals.set(owner, { total, undoc })
  }

  // Compute column totals
  const colTotals = new Map<string, { total: number; undoc: number }>()
  for (const src of sources) {
    let total = 0, undoc = 0
    for (const owner of owners) {
      const entry = lookup.get(`${owner}::${src}`)
      if (entry) { total += entry.total; undoc += entry.undocumented }
    }
    colTotals.set(src, { total, undoc })
  }

  const handleCellClick = (owner: string, source: string) => {
    navigate(`/features?owner=${encodeURIComponent(owner)}&source=${encodeURIComponent(source)}&filter=undocumented`)
  }

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg p-5">
      <h3 className="text-sm font-semibold mb-1">{t('debt.title')}</h3>
      <p className="text-xs text-[var(--text-tertiary)] mb-3">{t('debt.subtitle')}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px] border-collapse">
          <thead>
            <tr>
              <th className="text-left py-1.5 px-2 font-medium text-[var(--text-tertiary)] border-b border-[var(--border-default)]">{t('debt.owner')}</th>
              {sources.map(src => (
                <th key={src} className="text-center py-1.5 px-2 font-medium text-[var(--text-tertiary)] border-b border-[var(--border-default)] max-w-[100px] truncate" title={src}>{src}</th>
              ))}
              <th className="text-center py-1.5 px-2 font-semibold text-[var(--text-secondary)] border-b border-[var(--border-default)]">{t('debt.total')}</th>
            </tr>
          </thead>
          <tbody>
            {owners.map(owner => (
              <tr key={owner} className="border-b border-[var(--border-subtle)]">
                <td className="py-1.5 px-2 font-medium text-[var(--text-secondary)] max-w-[120px] truncate" title={owner}>{owner}</td>
                {sources.map(src => {
                  const entry = lookup.get(`${owner}::${src}`)
                  if (!entry) {
                    return <td key={src} className="py-1.5 px-2 text-center bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]">-</td>
                  }
                  return (
                    <td
                      key={src}
                      className={`py-1.5 px-2 text-center cursor-pointer hover:opacity-80 transition-opacity font-mono ${debtColor(entry.pct_undocumented)}`}
                      onClick={() => handleCellClick(owner, src)}
                      title={`${entry.undocumented}/${entry.total} undocumented (${entry.pct_undocumented}%)`}
                    >
                      {entry.undocumented}/{entry.total}
                    </td>
                  )
                })}
                <td className="py-1.5 px-2 text-center font-mono font-semibold text-[var(--text-secondary)]">
                  {rowTotals.get(owner)?.undoc}/{rowTotals.get(owner)?.total}
                </td>
              </tr>
            ))}
            <tr className="border-t-2 border-[var(--border-default)]">
              <td className="py-1.5 px-2 font-semibold text-[var(--text-secondary)]">{t('debt.total')}</td>
              {sources.map(src => {
                const ct = colTotals.get(src)
                return (
                  <td key={src} className="py-1.5 px-2 text-center font-mono font-semibold text-[var(--text-secondary)]">
                    {ct?.undoc}/{ct?.total}
                  </td>
                )
              })}
              <td className="py-1.5 px-2 text-center font-mono font-bold text-[var(--text-primary)]">
                {data.reduce((s, d) => s + d.undocumented, 0)}/{data.reduce((s, d) => s + d.total, 0)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}
