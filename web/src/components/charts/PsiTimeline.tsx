import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, ReferenceArea, Dot } from 'recharts'

interface PsiDataPoint {
  checked_at: string
  psi: number | null
  severity: string
}

interface PsiTimelineProps {
  data: PsiDataPoint[]
  loading: boolean
}

const SEVERITY_COLORS: Record<string, string> = {
  healthy: '#1D9E75',
  warning: '#F59E0B',
  critical: '#EF4444',
  error: '#EF4444',
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function CustomDot(props: { cx?: number; cy?: number; payload?: PsiDataPoint }) {
  const { cx, cy, payload } = props
  if (!cx || !cy || !payload) return null
  const color = SEVERITY_COLORS[payload.severity] || '#94A3B8'
  return <Dot cx={cx} cy={cy} r={4} fill={color} stroke="var(--bg-primary)" strokeWidth={2} />
}

export function PsiTimeline({ data, loading }: PsiTimelineProps) {
  if (loading) {
    return <div className="h-32 bg-[var(--bg-tertiary)] rounded animate-shimmer" />
  }

  const validData = data.filter(d => d.psi != null)

  if (validData.length < 2) {
    return (
      <div className="flex items-center justify-center h-24 text-xs text-[var(--text-tertiary)] border border-dashed border-[var(--border-default)] rounded-lg">
        Not enough history yet
      </div>
    )
  }

  const maxPsi = Math.max(...validData.map(d => d.psi ?? 0), 0.25) + 0.05

  const chartData = validData.map(d => ({
    ...d,
    date: formatDate(d.checked_at),
    psiValue: d.psi,
  }))

  const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: { payload: { checked_at: string; psiValue: number; severity: string } }[] }) => {
    if (!active || !payload?.[0]) return null
    const d = payload[0].payload
    return (
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[12px] shadow-lg">
        <p className="text-[var(--text-secondary)]">{new Date(d.checked_at).toLocaleString()}</p>
        <p className="font-mono font-semibold">PSI: {d.psiValue?.toFixed(4)}</p>
        <p className="text-[var(--text-tertiary)]">Severity: {d.severity}</p>
      </div>
    )
  }

  return (
    <div className="mb-3">
      <p className="text-xs font-medium text-[var(--text-secondary)] mb-2">PSI Timeline</p>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
            axisLine={{ stroke: 'var(--border-default)' }}
          />
          <YAxis
            domain={[0, maxPsi]}
            tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
            axisLine={{ stroke: 'var(--border-default)' }}
            width={35}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceArea y1={0.2} y2={maxPsi} fill="#EF4444" fillOpacity={0.08} />
          <ReferenceLine y={0.1} stroke="#F59E0B" strokeDasharray="4 4" label={{ value: 'Warning', fontSize: 9, fill: '#F59E0B', position: 'right' }} />
          <ReferenceLine y={0.2} stroke="#EF4444" strokeDasharray="4 4" label={{ value: 'Critical', fontSize: 9, fill: '#EF4444', position: 'right' }} />
          <Line
            type="monotone"
            dataKey="psiValue"
            stroke="#1D9E75"
            strokeWidth={2}
            dot={<CustomDot />}
            activeDot={{ r: 6, stroke: 'var(--bg-primary)', strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
