import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import * as d3 from 'd3'
import { api, invalidateCache } from '../api'
import { Skeleton } from '../components/Skeleton'
import { Maximize2, RotateCcw } from 'lucide-react'

const SOURCE_PALETTE = [
  '#1D9E75', '#6366F1', '#F59E0B', '#EF4444', '#8B5CF6',
  '#06B6D4', '#EC4899', '#84CC16', '#F97316', '#14B8A6',
]

const DRIFT_BORDER: Record<string, string> = {
  healthy: '#1D9E75',
  warning: '#F59E0B',
  critical: '#EF4444',
  error: '#EF4444',
}

function columnName(spec: string): string {
  const col = spec.includes('.') ? spec.split('.').pop()! : spec
  return col.length > 14 ? col.slice(0, 13) + '\u2026' : col
}

function sourceName(spec: string): string {
  return spec.includes('.') ? spec.split('.')[0] : ''
}

function edgeColor(similarity: number): string {
  if (similarity > 0.7) return '#1D9E75'
  if (similarity >= 0.4) return '#64748B'
  return '#334155'
}

// Module-level cache to preserve graph layout across tab switches
let cachedGraphData: GraphData | null = null
let cachedThreshold: number | null = null

interface GraphNode extends d3.SimulationNodeDatum {
  id: string
  spec: string
  source: string
  dtype: string
  has_doc: boolean
  drift_status: string
  tags: string[]
}

interface GraphEdge extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode
  target: string | GraphNode
  similarity: number
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export function Similarity() {
  const { t } = useTranslation('similarity')
  const navigate = useNavigate()
  const svgRef = useRef<SVGSVGElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [sources, setSources] = useState<string[]>([])
  const [visibleSources, setVisibleSources] = useState<Set<string>>(new Set())
  const [threshold, setThreshold] = useState(0.3)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [graphSearch, setGraphSearch] = useState('')
  const simulationRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null)
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const navigateRef = useRef(navigate)
  navigateRef.current = navigate
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback((t: number) => {
    // Use cache if threshold unchanged
    if (cachedGraphData && cachedThreshold === t) {
      setData(cachedGraphData)
      const srcSet = new Set(cachedGraphData.nodes.map(n => n.source))
      const srcList = [...srcSet].sort()
      setSources(srcList)
      setVisibleSources(new Set(srcList))
      setLoading(false)
      return
    }
    setLoading(true)
    invalidateCache('/features/similarity-graph')
    api.similarity.graph(t)
      .then(d => {
        cachedGraphData = d
        cachedThreshold = t
        setData(d)
        const srcSet = new Set(d.nodes.map(n => n.source))
        const srcList = [...srcSet].sort()
        setSources(srcList)
        setVisibleSources(new Set(srcList))
      })
      .catch(() => setData({ nodes: [], edges: [] }))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(threshold) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const handleThresholdChange = (value: number) => {
    setThreshold(value)
    cachedGraphData = null  // clear cache on threshold change
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => load(value), 400)
  }

  // Build color map
  const colorMap = useMemo(() => new Map(sources.map((s, i) => [s, SOURCE_PALETTE[i % SOURCE_PALETTE.length]])), [sources])

  // D3 graph rendering
  useEffect(() => {
    if (!data || !svgRef.current || !containerRef.current) return
    if (data.nodes.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const rect = containerRef.current.getBoundingClientRect()
    const width = rect.width
    const height = rect.height

    svg.attr('width', width).attr('height', height)

    // Filter by visible sources
    const filteredNodes = data.nodes.filter(n => visibleSources.has(n.source))
    const filteredIds = new Set(filteredNodes.map(n => n.id))
    const filteredEdges = data.edges.filter(e => {
      const src = typeof e.source === 'string' ? e.source : e.source.id
      const tgt = typeof e.target === 'string' ? e.target : e.target.id
      return filteredIds.has(src) && filteredIds.has(tgt)
    })

    // Deep copy for simulation
    const nodes: GraphNode[] = filteredNodes.map(n => ({ ...n }))
    const edges: GraphEdge[] = filteredEdges.map(e => ({ ...e }))

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => g.attr('transform', event.transform))

    svg.call(zoom)
    zoomRef.current = zoom

    // Click on background to deselect
    svg.on('click', (event) => {
      if (event.target === svgRef.current) {
        setSelectedNode(null)
      }
    })

    const g = svg.append('g')

    // Tooltip
    const tooltip = d3.select(containerRef.current)
      .append('div')
      .attr('class', 'similarity-tooltip')
      .style('position', 'absolute')
      .style('pointer-events', 'none')
      .style('opacity', '0')
      .style('background', 'var(--bg-primary)')
      .style('border', '1px solid var(--border-default)')
      .style('border-radius', '8px')
      .style('padding', '10px 12px')
      .style('font-size', '12px')
      .style('color', 'var(--text-primary)')
      .style('box-shadow', '0 4px 12px rgba(0,0,0,0.15)')
      .style('z-index', '20')
      .style('max-width', '280px')
      .style('line-height', '1.5')

    // Edges — undirected (no arrowheads)
    const link = g.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', d => edgeColor((d as GraphEdge).similarity))
      .attr('stroke-opacity', d => 0.3 + (d as GraphEdge).similarity * 0.5)
      .attr('stroke-width', d => 1 + (d as GraphEdge).similarity * 4)

    // Node groups
    const node = g.append('g')
      .selectAll<SVGGElement, GraphNode>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag<SVGGElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) simulationRef.current?.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulationRef.current?.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
      )

    // Node circles
    node.append('circle')
      .attr('r', 24)
      .attr('fill', d => colorMap.get(d.source) || '#94A3B8')
      .attr('stroke', d => DRIFT_BORDER[d.drift_status] || '#1D9E75')
      .attr('stroke-width', 2.5)
      .attr('opacity', 0.9)

    // Drift status dot — top-right of node, on the circle border
    node.append('circle')
      .attr('r', 5)
      .attr('cx', 17)
      .attr('cy', -17)
      .attr('fill', d => {
        if (d.drift_status === 'critical') return '#ef4444'
        if (d.drift_status === 'warning') return '#f59e0b'
        return '#22c55e'
      })
      .attr('stroke', '#0f172a')
      .attr('stroke-width', 2)
      .attr('display', d => d.drift_status === 'healthy' ? 'none' : 'block')

    // Source label (above)
    node.append('text')
      .text(d => sourceName(d.spec))
      .attr('text-anchor', 'middle')
      .attr('dy', -32)
      .attr('font-size', 9)
      .attr('fill', 'var(--text-tertiary)')
      .attr('pointer-events', 'none')

    // Column label (below)
    node.append('text')
      .text(d => columnName(d.spec))
      .attr('text-anchor', 'middle')
      .attr('dy', 40)
      .attr('font-size', 11)
      .attr('fill', 'var(--text-secondary)')
      .attr('pointer-events', 'none')

    // Hover: show tooltip
    node.on('mouseenter', (event, d) => {
      const connectedCount = edges.filter(e => {
        const src = typeof e.source === 'string' ? e.source : (e.source as GraphNode).id
        const tgt = typeof e.target === 'string' ? e.target : (e.target as GraphNode).id
        return src === d.id || tgt === d.id
      }).length

      const tagsStr = d.tags.length > 0 ? d.tags.join(', ') : t('tooltip.tags_none')
      tooltip
        .html(`
          <div style="font-weight:600;margin-bottom:4px">${d.spec}</div>
          <div style="color:var(--text-secondary)">${t('tooltip.type')}: ${d.dtype} &nbsp;|&nbsp; ${t('tooltip.source')}: ${d.source}</div>
          <div style="color:var(--text-secondary)">${t('tooltip.tags')}: ${tagsStr}</div>
          <div style="color:var(--text-secondary)">${t('tooltip.doc')}: ${d.has_doc ? '\u2713' : '\u2717'} &nbsp;|&nbsp; ${t('tooltip.drift')}: ${d.drift_status}</div>
          <div style="color:var(--text-tertiary);margin-top:4px;border-top:1px solid var(--border-subtle);padding-top:4px">${t('tooltip.connected_to', { count: connectedCount })}</div>
        `)
        .style('opacity', '1')

      const containerRect = containerRef.current!.getBoundingClientRect()
      const x = event.clientX - containerRect.left + 12
      const y = event.clientY - containerRect.top - 10
      tooltip.style('left', x + 'px').style('top', y + 'px')
    })
    .on('mousemove', (event) => {
      const containerRect = containerRef.current!.getBoundingClientRect()
      const x = event.clientX - containerRect.left + 12
      const y = event.clientY - containerRect.top - 10
      tooltip.style('left', x + 'px').style('top', y + 'px')
    })
    .on('mouseleave', () => {
      tooltip.style('opacity', '0')
    })

    // Click: select node (highlight edges), double-click navigates
    node.on('click', (event, d) => {
      event.stopPropagation()
      setSelectedNode(prev => prev === d.id ? null : d.id)
    })
    .on('dblclick', (_event, d) => {
      navigateRef.current(`/features/${encodeURIComponent(d.spec)}`)
    })

    // Force simulation
    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(edges).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(40))

    simulation.on('tick', () => {
      link
        .attr('x1', d => (d.source as GraphNode).x!)
        .attr('y1', d => (d.source as GraphNode).y!)
        .attr('x2', d => (d.target as GraphNode).x!)
        .attr('y2', d => (d.target as GraphNode).y!)

      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    simulationRef.current = simulation

    // Auto-fit once when layout stabilizes
    simulation.on('end', () => {
      handleFit()
    })

    return () => {
      simulation.stop()
      tooltip.remove()
    }
  }, [data, visibleSources, colorMap])

  // Selection highlighting effect
  useEffect(() => {
    if (!svgRef.current || !data) return
    const svg = d3.select(svgRef.current)

    if (!selectedNode) {
      // Reset all
      svg.selectAll<SVGGElement, GraphNode>('g g g').select('circle:first-child').attr('opacity', 0.9)
      svg.selectAll<SVGGElement, GraphNode>('g g g').selectAll('text').attr('opacity', 1)
      svg.selectAll<SVGLineElement, GraphEdge>('g g line')
        .attr('stroke', d => edgeColor((d as GraphEdge).similarity))
        .attr('stroke-opacity', d => 0.3 + (d as GraphEdge).similarity * 0.5)
      return
    }

    const connected = new Set<string>()
    connected.add(selectedNode)
    data.edges.forEach(e => {
      const src = typeof e.source === 'string' ? e.source : (e.source as GraphNode).id
      const tgt = typeof e.target === 'string' ? e.target : (e.target as GraphNode).id
      if (src === selectedNode) connected.add(tgt)
      if (tgt === selectedNode) connected.add(src)
    })

    svg.selectAll<SVGGElement, GraphNode>('g g g')
      .select('circle:first-child')
      .attr('opacity', n => connected.has(n.id) ? 1 : 0.15)
    svg.selectAll<SVGGElement, GraphNode>('g g g')
      .selectAll('text')
      .attr('opacity', n => connected.has((n as unknown as GraphNode).id) ? 1 : 0.15)
    svg.selectAll<SVGLineElement, GraphEdge>('g g line')
      .attr('stroke-opacity', e => {
        const src = typeof e.source === 'string' ? e.source : (e.source as GraphNode).id
        const tgt = typeof e.target === 'string' ? e.target : (e.target as GraphNode).id
        return (src === selectedNode || tgt === selectedNode) ? 0.9 : 0.05
      })
      .attr('stroke', e => {
        const src = typeof e.source === 'string' ? e.source : (e.source as GraphNode).id
        const tgt = typeof e.target === 'string' ? e.target : (e.target as GraphNode).id
        return (src === selectedNode || tgt === selectedNode) ? '#1D9E75' : edgeColor((e as GraphEdge).similarity)
      })
  }, [selectedNode, data])

  // Graph search: dim non-matching nodes
  useEffect(() => {
    if (!svgRef.current || !data) return
    const svg = d3.select(svgRef.current)
    const q = graphSearch.toLowerCase().trim()

    if (!q) {
      svg.selectAll<SVGGElement, GraphNode>('g g g').select('circle:first-child').attr('opacity', 0.9)
      svg.selectAll<SVGGElement, GraphNode>('g g g').selectAll('text').attr('opacity', 1)
      return
    }

    svg.selectAll<SVGGElement, GraphNode>('g g g').each(function (d) {
      const text = `${d.spec} ${d.source} ${(d.tags || []).join(' ')}`.toLowerCase()
      const match = text.includes(q)
      d3.select(this).select('circle:first-child').attr('opacity', match ? 1 : 0.15)
      d3.select(this).selectAll('text').attr('opacity', match ? 1 : 0.15)
    })
  }, [graphSearch, data])

  const handleFit = () => {
    if (!svgRef.current || !zoomRef.current) return
    const svg = d3.select(svgRef.current)
    const gNode = svg.select<SVGGElement>('g').node()
    if (!gNode) return
    const bounds = gNode.getBBox()
    const w = svgRef.current.clientWidth
    const h = svgRef.current.clientHeight
    if (bounds.width === 0 || bounds.height === 0) return
    const scale = 0.85 / Math.max(bounds.width / w, bounds.height / h)
    const tx = (w - scale * (bounds.x * 2 + bounds.width)) / 2
    const ty = (h - scale * (bounds.y * 2 + bounds.height)) / 2
    svg.transition().duration(500).call(
      zoomRef.current.transform,
      d3.zoomIdentity.translate(tx, ty).scale(scale),
    )
  }

  const handleResetLayout = () => {
    if (!simulationRef.current) return
    simulationRef.current.alpha(1).restart()
  }

  const toggleSource = (src: string) => {
    setVisibleSources(prev => {
      const next = new Set(prev)
      if (next.has(src)) next.delete(src)
      else next.add(src)
      return next
    })
  }

  const isEmpty = data && data.nodes.length === 0

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 64px)' }}>
      <div className="flex justify-between items-center mb-4 shrink-0">
        <div>
          <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-0.5">
            {t('page.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={graphSearch}
            onChange={e => setGraphSearch(e.target.value)}
            placeholder={t('filter_placeholder')}
            className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-1.5 text-[12px] w-36 focus:border-accent outline-none"
          />
          <label className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
            <span className="whitespace-nowrap">{t('threshold_label')}</span>
            <input
              type="range"
              min={0.1}
              max={0.9}
              step={0.05}
              value={threshold}
              onChange={e => handleThresholdChange(parseFloat(e.target.value))}
              className="w-32 accent-accent"
            />
            <span className="font-mono w-8 text-right">{threshold.toFixed(2)}</span>
          </label>
        </div>
      </div>

      {loading ? (
        <Skeleton className="flex-1 min-h-[500px]" />
      ) : isEmpty ? (
        <div className="flex flex-col items-center justify-center flex-1 min-h-[400px] text-center gap-3">
          <p className="text-[var(--text-primary)] font-medium">{t('empty.title')}</p>
          <p className="text-[var(--text-tertiary)] text-sm max-w-sm">
            {t('empty.subtitle')}
          </p>
        </div>
      ) : (
        <div ref={containerRef} className="relative flex-1 min-h-[500px] bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
          <svg ref={svgRef} className="w-full h-full" />

          {/* Controls overlay */}
          <div className="absolute top-3 right-3 flex flex-col gap-2 z-10">
            <button onClick={handleFit} className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm hover:bg-[var(--bg-secondary)]" title={t('actions.fit_title')}>
              <Maximize2 size={13} /> {t('actions.fit')}
            </button>
            <button onClick={handleResetLayout} className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm hover:bg-[var(--bg-secondary)]" title={t('actions.reset_title')}>
              <RotateCcw size={13} /> {t('actions.reset_layout')}
            </button>
            {sources.length > 1 && (
              <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm p-2">
                <p className="text-[10px] font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-1">{t('sources_label')}</p>
                {sources.map(src => (
                  <label key={src} className="flex items-center gap-1.5 text-[11px] cursor-pointer py-0.5">
                    <input
                      type="checkbox"
                      checked={visibleSources.has(src)}
                      onChange={() => toggleSource(src)}
                      className="accent-accent"
                    />
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: colorMap.get(src) || '#94A3B8' }} />
                    <span className="truncate max-w-[100px]">{src}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="absolute bottom-3 left-3 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm p-2.5 z-10">
            <div className="flex flex-col gap-1.5 text-[10px] text-[var(--text-tertiary)]">
              <div className="flex items-center gap-2">
                <span className="w-6 h-[3px] rounded" style={{ background: '#1D9E75' }} />
                <span>{t('legend.strong')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-6 h-[2px] rounded" style={{ background: '#64748B' }} />
                <span>{t('legend.moderate')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-6 h-[1px] rounded" style={{ background: '#334155' }} />
                <span>{t('legend.weak')}</span>
              </div>
              {sources.length > 0 && (
                <div className="flex items-center gap-2 mt-1 pt-1 border-t border-[var(--border-subtle)] flex-wrap">
                  {sources.map(src => (
                    <span key={src} className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: colorMap.get(src) || '#94A3B8' }} />
                      <span>{src}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
