import { useMemo } from 'react'
import type { SimilarityFeatureBrief } from '../../api'

interface MatrixGridProps {
  features: SimilarityFeatureBrief[]
  cells: { a: number; b: number; score: number }[]
  onCellClick: (aId: string, bId: string) => void
}

// Heatmap colors keyed off score thresholds. Mirrors the DocDebtHeatmap
// pattern: Tailwind utility classes with `dark:` variants so the colors invert
// cleanly under the project's class-based dark mode.
function scoreClasses(score: number): { bg: string; text: string } {
  if (score < 0.3) return { bg: 'bg-transparent', text: 'text-[var(--text-tertiary)]' }
  if (score < 0.5) return { bg: 'bg-brand/10 dark:bg-brand/25', text: 'text-[var(--text-primary)]' }
  if (score < 0.7) return { bg: 'bg-brand/30 dark:bg-brand/45', text: 'text-[var(--text-primary)]' }
  if (score < 0.9) return { bg: 'bg-brand/60 dark:bg-brand/65', text: 'text-white' }
  return { bg: 'bg-brand', text: 'text-white' }
}

function columnPart(name: string): string {
  const idx = name.indexOf('.')
  return idx === -1 ? name : name.slice(idx + 1)
}

function sourcePart(name: string): string {
  const idx = name.indexOf('.')
  return idx === -1 ? '' : name.slice(0, idx)
}

export function MatrixGrid({ features, cells, onCellClick }: MatrixGridProps) {
  // O(1) lookup of a cell's score by (i, j) where i < j.
  const cellLookup = useMemo(() => {
    const m = new Map<number, number>()
    for (const c of cells) m.set(c.a * features.length + c.b, c.score)
    return m
  }, [cells, features.length])

  const n = features.length

  // Detect source-group boundaries: cell (i, j) needs a thicker left border
  // when feature j's source differs from j-1's; same for top borders on rows.
  const isNewSource = useMemo(() => {
    const flags: boolean[] = []
    for (let i = 0; i < n; i++) {
      const prev = i > 0 ? sourcePart(features[i - 1].name) : null
      flags.push(i > 0 && sourcePart(features[i].name) !== prev)
    }
    return flags
  }, [features, n])

  return (
    <table className="border-collapse text-[10px] font-mono">
      <thead>
        <tr>
          <th className="sticky top-0 left-0 z-30 bg-[var(--bg-primary)] border-b border-r border-[var(--border-default)]" />
          {features.map((f, j) => (
            <th
              key={f.id}
              className={`sticky top-0 z-20 bg-[var(--bg-primary)] border-b border-[var(--border-default)] align-bottom h-32 px-0.5 ${
                isNewSource[j] ? 'border-l-2 border-l-[var(--border-default)]' : ''
              }`}
              title={f.name}
            >
              <div
                className="origin-bottom-left rotate-[-60deg] translate-x-3 whitespace-nowrap text-[var(--text-secondary)]"
                style={{ width: '0', height: '110px' }}
              >
                <span className="inline-block max-w-[110px] truncate">{columnPart(f.name)}</span>
              </div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {features.map((rowFeat, i) => (
          <tr key={rowFeat.id} className={isNewSource[i] ? 'border-t-2 border-t-[var(--border-default)]' : ''}>
            <th
              className="sticky left-0 z-10 bg-[var(--bg-primary)] border-r border-[var(--border-default)] text-right pr-2 py-1 font-medium text-[var(--text-secondary)] whitespace-nowrap"
              title={rowFeat.name}
            >
              <span className="inline-block max-w-[180px] truncate align-middle">{columnPart(rowFeat.name)}</span>
            </th>
            {features.map((colFeat, j) => {
              const newSourceLeft = isNewSource[j]
              const baseBorder = `border border-[var(--border-subtle)] ${
                newSourceLeft ? 'border-l-2 border-l-[var(--border-default)]' : ''
              }`

              if (i === j) {
                // Diagonal: always 1.0, not clickable, distinct styling.
                return (
                  <td
                    key={colFeat.id}
                    className={`${baseBorder} bg-brand/80 text-white text-center w-9 h-9 align-middle`}
                    title={`${rowFeat.name} = self (1.00)`}
                  >
                    1.00
                  </td>
                )
              }

              if (j < i) {
                // Lower triangle: leave empty to drive the eye to the upper.
                return <td key={colFeat.id} className={`${baseBorder} bg-[var(--bg-tertiary)]/40 w-9 h-9`} />
              }

              const score = cellLookup.get(i * n + j)
              if (score === undefined) {
                // Upper triangle but below threshold — render dimmed blank.
                return (
                  <td
                    key={colFeat.id}
                    className={`${baseBorder} bg-transparent text-[var(--text-muted)] text-center w-9 h-9 align-middle`}
                  >
                    ·
                  </td>
                )
              }

              const cls = scoreClasses(score)
              return (
                <td
                  key={colFeat.id}
                  className={`${baseBorder} ${cls.bg} ${cls.text} text-center w-9 h-9 align-middle cursor-pointer hover:outline hover:outline-2 hover:outline-brand`}
                  title={`${rowFeat.name} ↔ ${colFeat.name}: ${score.toFixed(3)}`}
                  onClick={() => onCellClick(rowFeat.id, colFeat.id)}
                >
                  {score.toFixed(2)}
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
