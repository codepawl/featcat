import { memo, useCallback, useMemo } from 'react'
import type { SimilarityFeatureBrief } from '../../api'

interface MatrixGridProps {
  features: SimilarityFeatureBrief[]
  cells: { a: number; b: number; score: number }[]
  threshold: number
  onCellClick: (aId: string, bId: string) => void
}

// 5-bucket scale with bigger opacity jumps so 0.03 and 0.73 don't look alike.
// Below 0.5 the cell is tinted but text-free — magnitude is communicated by
// color, the exact value lives in the title= tooltip. Avoids visual clutter
// when many weak hits land just above the threshold slider.
function bucketClasses(score: number): { bg: string; text: string; showText: boolean } {
  if (score < 0.5) return { bg: 'bg-brand/10 dark:bg-brand/15', text: '', showText: false }
  if (score < 0.65) return { bg: 'bg-brand/30 dark:bg-brand/35', text: 'text-[var(--text-primary)]', showText: true }
  if (score < 0.8) return { bg: 'bg-brand/55', text: 'text-white', showText: true }
  if (score < 0.92) return { bg: 'bg-brand/80', text: 'text-white', showText: true }
  return { bg: 'bg-brand', text: 'text-white', showText: true }
}

function columnPart(name: string): string {
  const idx = name.indexOf('.')
  return idx === -1 ? name : name.slice(idx + 1)
}

function sourcePart(name: string): string {
  const idx = name.indexOf('.')
  return idx === -1 ? '' : name.slice(0, idx)
}

interface CellProps {
  rowId: string
  colId: string
  rowName: string
  colName: string
  score: number | undefined
  kind: 'diagonal' | 'lower' | 'upper-empty' | 'upper-scored'
  borderLeft: boolean
  onClick: (a: string, b: string) => void
}

const MatrixCell = memo(function MatrixCell({
  rowId,
  colId,
  rowName,
  colName,
  score,
  kind,
  borderLeft,
  onClick,
}: CellProps) {
  const borderClass = `border border-[var(--border-subtle)]${
    borderLeft ? ' border-l-2 border-l-[var(--border-default)]' : ''
  }`

  if (kind === 'diagonal') {
    // Self-similarity is always 1.0 and carries no information; fade into the
    // background instead of competing with real scores. An em-dash signals
    // "no data here" without drawing the eye.
    return (
      <td
        className={`${borderClass} bg-[var(--bg-tertiary)] w-10 h-10 align-middle text-center text-[var(--text-tertiary)] select-none`}
        title={`${rowName} (self)`}
        aria-label="self"
      >
        —
      </td>
    )
  }

  if (kind === 'lower') {
    return <td className={`${borderClass} bg-[var(--bg-tertiary)]/30 w-10 h-10`} />
  }

  if (kind === 'upper-empty' || score === undefined) {
    return <td className={`${borderClass} w-10 h-10`} />
  }

  const cls = bucketClasses(score)
  const handle = () => onClick(rowId, colId)
  return (
    <td
      className={`${borderClass} ${cls.bg} ${cls.text} text-center w-10 h-10 align-middle cursor-pointer hover:outline hover:outline-2 hover:-outline-offset-1 hover:outline-brand transition-colors`}
      title={`${rowName} ↔ ${colName}: ${score.toFixed(3)}`}
      onClick={handle}
    >
      {cls.showText ? score.toFixed(2) : ''}
    </td>
  )
})

function MatrixGridImpl({ features, cells, threshold, onCellClick }: MatrixGridProps) {
  // O(1) score lookup keyed by row*n + col. Built once per cells/features
  // change — independent of threshold so the slider never re-builds this.
  const n = features.length
  const cellLookup = useMemo(() => {
    const m = new Map<number, number>()
    for (const c of cells) m.set(c.a * n + c.b, c.score)
    return m
  }, [cells, n])

  // Source-group boundaries: cell j gets a thicker left border when feature
  // j's source differs from j-1's. Same flag drives the top border on rows.
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
              className={`sticky top-0 z-20 bg-[var(--bg-primary)] border-b border-[var(--border-default)] align-bottom w-10 h-36 px-0 ${
                isNewSource[j] ? 'border-l-2 border-l-[var(--border-default)]' : ''
              }`}
              title={f.name}
            >
              {/* Vertical-writing-mode + 180° flip reads bottom-to-top, with
                  the first character sitting next to the data cell. w-10 on the
                  parent th keeps the header column flush with the 40px data
                  column — no more rotated-out-of-flow misalignment. */}
              <div className="mx-auto whitespace-nowrap text-[10px] text-[var(--text-secondary)] pb-1 max-h-[136px] overflow-hidden [writing-mode:vertical-rl] rotate-180">
                {columnPart(f.name)}
              </div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {features.map((rowFeat, i) => (
          <tr
            key={rowFeat.id}
            className={isNewSource[i] ? 'border-t-2 border-t-[var(--border-default)]' : ''}
          >
            <th
              className="sticky left-0 z-10 bg-[var(--bg-primary)] border-r border-[var(--border-default)] text-right pr-2 py-1 font-medium text-[var(--text-secondary)] whitespace-nowrap"
              title={rowFeat.name}
            >
              <span className="inline-block max-w-[180px] truncate align-middle">
                {columnPart(rowFeat.name)}
              </span>
            </th>
            {features.map((colFeat, j) => {
              let kind: CellProps['kind']
              let score: number | undefined
              if (i === j) {
                kind = 'diagonal'
              } else if (j < i) {
                kind = 'lower'
              } else {
                score = cellLookup.get(i * n + j)
                if (score === undefined || score < threshold) {
                  kind = 'upper-empty'
                  score = undefined
                } else {
                  kind = 'upper-scored'
                }
              }
              return (
                <MatrixCell
                  key={colFeat.id}
                  rowId={rowFeat.id}
                  colId={colFeat.id}
                  rowName={rowFeat.name}
                  colName={colFeat.name}
                  score={score}
                  kind={kind}
                  borderLeft={isNewSource[j]}
                  onClick={onCellClick}
                />
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export const MatrixGrid = memo(MatrixGridImpl)

// Re-export the memoized cell click handler shape so callers can build a
// stable onClick (otherwise React.memo's referential equality fails).
export function useStableCellClick(
  setActivePair: (pair: { a: string; b: string }) => void,
): (a: string, b: string) => void {
  return useCallback((a, b) => setActivePair({ a, b }), [setActivePair])
}
