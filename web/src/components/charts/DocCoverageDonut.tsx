import { useNavigate } from 'react-router-dom'
import { PieChart, Pie, Cell, Label, ResponsiveContainer, Legend, Tooltip } from 'recharts'
import { Skeleton } from '../Skeleton'

interface DocCoverageDonutProps {
  totalFeatures: number
  documentedFeatures: number
  featuresWithHints: number
  loading: boolean
}

const COLORS = {
  documented: '#1D9E75',
  hintsOnly: '#F59E0B',
  noDoc: '#94A3B8',
}

export function DocCoverageDonut({ totalFeatures, documentedFeatures, featuresWithHints, loading }: DocCoverageDonutProps) {
  const navigate = useNavigate()

  if (loading) return <Skeleton className="h-52" />

  if (totalFeatures === 0) {
    return (
      <div className="flex items-center justify-center h-52 text-sm text-[var(--text-tertiary)]">
        No features in catalog
      </div>
    )
  }

  // hints-only = features that have hints but no doc
  const hintsOnly = Math.max(0, featuresWithHints - documentedFeatures)
  const noDoc = totalFeatures - documentedFeatures - hintsOnly
  const docPct = Math.round((documentedFeatures / totalFeatures) * 100)

  const data = [
    { name: 'Documented', value: documentedFeatures, color: COLORS.documented },
    { name: 'Has hints only', value: hintsOnly, color: COLORS.hintsOnly },
    { name: 'No doc', value: noDoc, color: COLORS.noDoc },
  ].filter(d => d.value > 0)

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-3">Documentation Coverage</h3>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={70}
            outerRadius={100}
            paddingAngle={2}
            dataKey="value"
            onClick={() => navigate('/features?filter=undocumented')}
            className="cursor-pointer"
          >
            {data.map((entry, idx) => (
              <Cell key={idx} fill={entry.color} stroke="var(--bg-primary)" strokeWidth={2} />
            ))}
            <Label
              content={({ viewBox }) => {
                const { cx, cy } = viewBox as { cx: number; cy: number }
                return (
                  <g>
                    <text x={cx} y={cy - 8} textAnchor="middle" dominantBaseline="middle"
                      className="fill-[var(--text-primary)]" fontSize={28} fontWeight={700}>
                      {docPct}%
                    </text>
                    <text x={cx} y={cy + 20} textAnchor="middle" dominantBaseline="middle"
                      className="fill-[var(--text-tertiary)]" fontSize={13}>
                      documented
                    </text>
                  </g>
                )
              }}
            />
          </Pie>
          <Tooltip
            contentStyle={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
              borderRadius: 8,
              fontSize: 13,
              color: 'var(--text-primary)',
            }}
            formatter={(value, name) => [`${value} features`, name]}
          />
          <Legend
            verticalAlign="bottom"
            height={36}
            iconType="circle"
            iconSize={8}
            formatter={(value: string) => <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{value}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
