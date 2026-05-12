import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import * as d3 from 'd3'
import { api } from '../api'
import { Skeleton } from '../components/Skeleton'
import { Maximize2, RotateCcw } from 'lucide-react'

const SOURCE_PALETTE = [
  '#1D9E75', '#6366F1', '#F59E0B', '#EF4444', '#8B5CF6',
  '#06B6D4', '#EC4899', '#84CC16', '#F97316', '#14B8A6',
]

// Auto-pick canvas above this many nodes — SVG above ~500 nodes (~3 elements
// each = 1500+ DOM nodes plus event listeners) starts to drag in modern
// Chromium. Canvas keeps frame budget headroom up to ~10k nodes because the
// cost moves from DOM mutation to a single bitmap blit per tick.
const CANVAS_THRESHOLD = 500

// Click / hover hit radius (in pre-zoom screen pixels). The SVG version got
// this for free via per-element listeners; canvas needs an explicit value.
const HIT_RADIUS_PX = 20

type RenderMode = 'auto' | 'svg' | 'canvas'

function columnName(name: string): string {
  const col = name.includes('.') ? name.split('.').pop()! : name
  return col.length > 16 ? col.slice(0, 15) + '…' : col
}

function sourceName(name: string): string {
  return name.includes('.') ? name.split('.')[0] : ''
}

interface ApiNode {
  name: string
  source: string
  dtype: string
  owner: string
}

interface ApiEdge {
  child: string
  parent: string
  transform: string
  detected_method: string
}

interface ApiGraph {
  nodes: ApiNode[]
  edges: ApiEdge[]
}

interface SimNode extends d3.SimulationNodeDatum, ApiNode {
  id: string
}

interface SimEdge extends d3.SimulationLinkDatum<SimNode> {
  source: string | SimNode
  target: string | SimNode
  transform: string
  detected_method: string
}

// Module-level cache so the layout survives tab switches
let cachedGraph: ApiGraph | null = null

export function Lineage() {
  const { t } = useTranslation('lineage')
  const navigate = useNavigate()
  const svgRef = useRef<SVGSVGElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const simulationRef = useRef<d3.Simulation<SimNode, SimEdge> | null>(null)
  const zoomRef = useRef<d3.ZoomBehavior<Element, unknown> | null>(null)
  const navigateRef = useRef(navigate)
  navigateRef.current = navigate

  const [data, setData] = useState<ApiGraph | null>(null)
  const [loading, setLoading] = useState(true)
  const [sources, setSources] = useState<string[]>([])
  const [visibleSources, setVisibleSources] = useState<Set<string>>(new Set())
  const [hideIsolated, setHideIsolated] = useState(false)
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [graphSearch, setGraphSearch] = useState('')
  const [renderMode, setRenderMode] = useState<RenderMode>('auto')

  // Fetch once on mount
  const load = useCallback(() => {
    if (cachedGraph) {
      setData(cachedGraph)
      const srcSet = new Set(cachedGraph.nodes.map(n => n.source).filter(Boolean))
      const srcList = [...srcSet].sort()
      setSources(srcList)
      setVisibleSources(new Set(srcList))
      setLoading(false)
      return
    }
    setLoading(true)
    api.lineage.full()
      .then((d: ApiGraph) => {
        cachedGraph = d
        setData(d)
        const srcSet = new Set(d.nodes.map(n => n.source).filter(Boolean))
        const srcList = [...srcSet].sort()
        setSources(srcList)
        setVisibleSources(new Set(srcList))
      })
      .catch(() => setData({ nodes: [], edges: [] }))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const colorMap = useMemo(
    () => new Map(sources.map((s, i) => [s, SOURCE_PALETTE[i % SOURCE_PALETTE.length]])),
    [sources],
  )

  // Filter pipeline: source filter -> isolated filter. No node cap anymore;
  // canvas mode handles large graphs. Memoised so d3 effects don't re-run
  // unless inputs actually change.
  const filtered = useMemo(() => {
    if (!data) return { nodes: [] as ApiNode[], edges: [] as ApiEdge[], total: 0 }
    const srcOk = (n: ApiNode) => visibleSources.size === 0 || visibleSources.has(n.source)
    const baseNodes = data.nodes.filter(srcOk)
    const baseIds = new Set(baseNodes.map(n => n.name))
    const baseEdges = data.edges.filter(e => baseIds.has(e.child) && baseIds.has(e.parent))

    let nodes = baseNodes
    if (hideIsolated) {
      const connected = new Set<string>()
      for (const e of baseEdges) {
        connected.add(e.child)
        connected.add(e.parent)
      }
      nodes = baseNodes.filter(n => connected.has(n.name))
    }

    const ids = new Set(nodes.map(n => n.name))
    const edges = baseEdges.filter(e => ids.has(e.child) && ids.has(e.parent))
    return { nodes, edges, total: nodes.length }
  }, [data, visibleSources, hideIsolated])

  // Build ancestor + descendant sets for the selected node from full data
  const reachable = useMemo(() => {
    if (!selectedNode || !data) return null
    const upstream = new Set<string>([selectedNode])
    const downstream = new Set<string>([selectedNode])
    const parentsOf = new Map<string, string[]>()
    const childrenOf = new Map<string, string[]>()
    for (const e of data.edges) {
      if (!parentsOf.has(e.child)) parentsOf.set(e.child, [])
      parentsOf.get(e.child)!.push(e.parent)
      if (!childrenOf.has(e.parent)) childrenOf.set(e.parent, [])
      childrenOf.get(e.parent)!.push(e.child)
    }
    const stackUp = [selectedNode]
    while (stackUp.length > 0) {
      const cur = stackUp.pop()!
      for (const p of parentsOf.get(cur) ?? []) {
        if (!upstream.has(p)) {
          upstream.add(p)
          stackUp.push(p)
        }
      }
    }
    const stackDown = [selectedNode]
    while (stackDown.length > 0) {
      const cur = stackDown.pop()!
      for (const c of childrenOf.get(cur) ?? []) {
        if (!downstream.has(c)) {
          downstream.add(c)
          stackDown.push(c)
        }
      }
    }
    const all = new Set([...upstream, ...downstream])
    return { all, upstream, downstream }
  }, [selectedNode, data])

  // Resolve auto -> svg/canvas based on node count threshold.
  const effectiveMode: 'svg' | 'canvas' = useMemo(() => {
    if (renderMode === 'svg') return 'svg'
    if (renderMode === 'canvas') return 'canvas'
    return filtered.nodes.length > CANVAS_THRESHOLD ? 'canvas' : 'svg'
  }, [renderMode, filtered.nodes.length])

  // ----- SVG renderer -------------------------------------------------------
  useEffect(() => {
    if (effectiveMode !== 'svg') return
    if (!svgRef.current || !containerRef.current) return
    if (filtered.nodes.length === 0) return

    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const rect = containerRef.current.getBoundingClientRect()
    const width = rect.width
    const height = rect.height
    svg.attr('width', width).attr('height', height)

    // Deep copy so the simulation can mutate x/y without scribbling on the
    // memoised filtered arrays (otherwise React's referential checks lie to us).
    const nodes: SimNode[] = filtered.nodes.map(n => ({ ...n, id: n.name }))
    const edges: SimEdge[] = filtered.edges.map(e => ({
      source: e.parent,
      target: e.child,
      transform: e.transform,
      detected_method: e.detected_method,
    }))

    // Arrowhead defs (one for default, one for highlighted)
    const defs = svg.append('defs')
    const mkArrow = (id: string, color: string) => {
      defs.append('marker')
        .attr('id', id)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 26)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', color)
    }
    mkArrow('lineage-arrow-default', '#64748B')
    mkArrow('lineage-arrow-highlight', '#1D9E75')
    mkArrow('lineage-arrow-fade', '#1f2937')

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 4])
      .on('zoom', (event) => g.attr('transform', event.transform))
    svg.call(zoom)
    zoomRef.current = zoom as unknown as d3.ZoomBehavior<Element, unknown>

    svg.on('click', (event) => {
      if (event.target === svgRef.current) setSelectedNode(null)
    })

    const g = svg.append('g')

    // Tooltip
    const tooltip = d3.select(containerRef.current)
      .append('div')
      .attr('class', 'lineage-tooltip')
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
      .style('max-width', '320px')
      .style('line-height', '1.5')

    // Edges (line — arrowhead via marker-end)
    const link = g.append('g')
      .attr('class', 'edges')
      .selectAll<SVGLineElement, SimEdge>('line')
      .data(edges)
      .join('line')
      .attr('stroke', '#64748B')
      .attr('stroke-opacity', 0.55)
      .attr('stroke-width', 1.4)
      .attr('stroke-dasharray', d => d.detected_method === 'sqlglot' ? '4 3' : null)
      .attr('marker-end', 'url(#lineage-arrow-default)')

    // Edge hover: tooltip with transform
    link
      .on('mouseenter', (event, d) => {
        const transform = d.transform || `<span style="color:var(--text-tertiary)">${t('tooltip.no_transform')}</span>`
        const src = typeof d.source === 'string' ? d.source : d.source.id
        const tgt = typeof d.target === 'string' ? d.target : d.target.id
        tooltip.html(`
          <div style="font-weight:600;margin-bottom:4px">${src} → ${tgt}</div>
          <div style="color:var(--text-secondary)">${t('tooltip.transform')}: ${transform}</div>
          <div style="color:var(--text-tertiary);margin-top:4px">${t('tooltip.method')}: ${d.detected_method}</div>
        `).style('opacity', '1')
        const containerRect = containerRef.current!.getBoundingClientRect()
        tooltip.style('left', (event.clientX - containerRect.left + 12) + 'px')
          .style('top', (event.clientY - containerRect.top - 10) + 'px')
      })
      .on('mousemove', (event) => {
        const containerRect = containerRef.current!.getBoundingClientRect()
        tooltip.style('left', (event.clientX - containerRect.left + 12) + 'px')
          .style('top', (event.clientY - containerRect.top - 10) + 'px')
      })
      .on('mouseleave', () => tooltip.style('opacity', '0'))

    // Nodes
    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll<SVGGElement, SimNode>('g')
      .data(nodes)
      .join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag<SVGGElement, SimNode>()
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
        }),
      )

    // Compute label widths once for sizing
    const NODE_HEIGHT = 28
    const PAD_X = 14

    node.append('rect')
      .attr('rx', 6)
      .attr('ry', 6)
      .attr('y', -NODE_HEIGHT / 2)
      .attr('height', NODE_HEIGHT)
      .attr('fill', d => colorMap.get(d.source) || '#94A3B8')
      .attr('fill-opacity', 0.9)
      .attr('stroke', d => colorMap.get(d.source) || '#94A3B8')
      .attr('stroke-width', 1.5)

    const label = node.append('text')
      .text(d => columnName(d.name))
      .attr('text-anchor', 'middle')
      .attr('dy', 4)
      .attr('font-size', 11)
      .attr('font-weight', 500)
      .attr('fill', '#fff')
      .attr('pointer-events', 'none')

    // Resize rect to fit label
    label.each(function (_, i) {
      const bbox = (this as SVGTextElement).getBBox()
      const w = Math.max(bbox.width + PAD_X * 2, 64)
      d3.select(node.nodes()[i]).select<SVGRectElement>('rect')
        .attr('x', -w / 2)
        .attr('width', w)
    })

    // Source label above
    node.append('text')
      .text(d => sourceName(d.name))
      .attr('text-anchor', 'middle')
      .attr('dy', -NODE_HEIGHT / 2 - 5)
      .attr('font-size', 9)
      .attr('fill', 'var(--text-tertiary)')
      .attr('pointer-events', 'none')

    // Node hover tooltip
    node.on('mouseenter', (event, d) => {
      const upstreamCount = edges.filter(e => {
        const tgt = typeof e.target === 'string' ? e.target : e.target.id
        return tgt === d.id
      }).length
      const downstreamCount = edges.filter(e => {
        const src = typeof e.source === 'string' ? e.source : e.source.id
        return src === d.id
      }).length
      tooltip.html(`
        <div style="font-weight:600;margin-bottom:4px">${d.name}</div>
        <div style="color:var(--text-secondary)">${t('tooltip.dtype')}: ${d.dtype || '-'} &nbsp;|&nbsp; ${t('tooltip.source')}: ${d.source || '-'}</div>
        <div style="color:var(--text-secondary)">${t('tooltip.owner')}: ${d.owner || t('tooltip.owner_unset')}</div>
        <div style="color:var(--text-tertiary);margin-top:4px;border-top:1px solid var(--border-subtle);padding-top:4px">
          ↑ ${t('tooltip.upstream')}: ${upstreamCount} &nbsp;—&nbsp; ↓ ${t('tooltip.downstream')}: ${downstreamCount}
        </div>
      `).style('opacity', '1')
      const containerRect = containerRef.current!.getBoundingClientRect()
      tooltip.style('left', (event.clientX - containerRect.left + 12) + 'px')
        .style('top', (event.clientY - containerRect.top - 10) + 'px')
    })
    .on('mousemove', (event) => {
      const containerRect = containerRef.current!.getBoundingClientRect()
      tooltip.style('left', (event.clientX - containerRect.left + 12) + 'px')
        .style('top', (event.clientY - containerRect.top - 10) + 'px')
    })
    .on('mouseleave', () => tooltip.style('opacity', '0'))
    .on('click', (event, d) => {
      event.stopPropagation()
      setSelectedNode(prev => prev === d.id ? null : d.id)
    })
    .on('dblclick', (_event, d) => {
      navigateRef.current(`/features/${encodeURIComponent(d.name)}`)
    })

    // Force simulation: lighter charge + shorter link distance helps keep
    // hierarchies legible without forcing a full Sugiyama layout.
    const simulation = d3.forceSimulation<SimNode>(nodes)
      .force('link', d3.forceLink<SimNode, SimEdge>(edges).id(d => d.id).distance(110).strength(0.6))
      .force('charge', d3.forceManyBody().strength(-260))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(48))
      // y-bias: parents sit above children. Approximated by pulling each
      // node toward y = depth * spacing where depth = longest path from a
      // root parent. Cheap topological ranking, run once.
      .force('y', d3.forceY<SimNode>(rankYTarget(nodes, edges, height)).strength(0.18))

    simulation.on('tick', () => {
      link
        .attr('x1', d => (d.source as SimNode).x ?? 0)
        .attr('y1', d => (d.source as SimNode).y ?? 0)
        .attr('x2', d => (d.target as SimNode).x ?? 0)
        .attr('y2', d => (d.target as SimNode).y ?? 0)
      node.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    simulation.on('end', () => handleFit())

    simulationRef.current = simulation

    return () => {
      simulation.stop()
      tooltip.remove()
    }
  }, [filtered, colorMap, t, effectiveMode])

  // ----- Canvas renderer ----------------------------------------------------
  // Mirrors the SVG path's physics (same forces, same y-rank bias). Differences:
  //   - One <canvas> blit per tick instead of per-node DOM mutation.
  //   - Hit-testing for click/hover/drag is manual: brute-force nearest-node
  //     within HIT_RADIUS_PX. O(N) per pointer event, fine up to ~20k nodes.
  //   - Zoom + pan are applied by transforming the canvas context (translate +
  //     scale) before draw — d3.zoom drives the same transform value as SVG.
  useEffect(() => {
    if (effectiveMode !== 'canvas') return
    if (!canvasRef.current || !containerRef.current) return
    if (filtered.nodes.length === 0) return

    const canvas = canvasRef.current
    const container = containerRef.current
    const rect = container.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    const width = rect.width
    const height = rect.height
    canvas.width = Math.floor(width * dpr)
    canvas.height = Math.floor(height * dpr)
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const nodes: SimNode[] = filtered.nodes.map(n => ({ ...n, id: n.name }))
    const edges: SimEdge[] = filtered.edges.map(e => ({
      source: e.parent,
      target: e.child,
      transform: e.transform,
      detected_method: e.detected_method,
    }))

    // Resolve string sources/targets to node refs once so tick draws can
    // skip the `typeof === 'string'` dance per edge per frame.
    const byId = new Map<string, SimNode>(nodes.map(n => [n.id, n]))
    const resolvedEdges: { src: SimNode; tgt: SimNode; e: SimEdge }[] = []
    for (const e of edges) {
      const src = typeof e.source === 'string' ? byId.get(e.source) : (e.source as SimNode)
      const tgt = typeof e.target === 'string' ? byId.get(e.target) : (e.target as SimNode)
      if (src && tgt) resolvedEdges.push({ src, tgt, e })
    }

    // Tooltip — created once, removed in cleanup. Same DOM tooltip as SVG mode
    // so styling is identical.
    const tooltip = d3.select(container)
      .append('div')
      .attr('class', 'lineage-tooltip')
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
      .style('max-width', '320px')
      .style('line-height', '1.5')

    // Current zoom transform — d3.zoomIdentity until the user pans/zooms.
    let transform = d3.zoomIdentity

    const draw = () => {
      ctx.save()
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      ctx.translate(transform.x, transform.y)
      ctx.scale(transform.k, transform.k)

      const reach = reachableRef.current
      const search = searchRef.current.toLowerCase().trim()

      // Edges first so nodes paint on top.
      ctx.lineWidth = 1.4 / Math.max(transform.k, 0.5)
      for (const { src, tgt, e } of resolvedEdges) {
        const sx = src.x ?? 0, sy = src.y ?? 0
        const tx = tgt.x ?? 0, ty = tgt.y ?? 0
        let stroke = '#64748B'
        let alpha = 0.55
        if (reach) {
          const inPath = reach.all.has(src.id) && reach.all.has(tgt.id)
          stroke = inPath ? '#1D9E75' : '#1f2937'
          alpha = inPath ? 0.9 : 0.06
        }
        ctx.strokeStyle = stroke
        ctx.globalAlpha = alpha
        if (e.detected_method === 'sqlglot') {
          ctx.setLineDash([4, 3])
        } else {
          ctx.setLineDash([])
        }
        ctx.beginPath()
        ctx.moveTo(sx, sy)
        ctx.lineTo(tx, ty)
        ctx.stroke()

        // Arrowhead — small filled triangle at the target end. Computed in
        // simulation space so it scales with zoom for free.
        const dx = tx - sx, dy = ty - sy
        const len = Math.hypot(dx, dy) || 1
        const ux = dx / len, uy = dy / len
        // Back the head off the target node by ~26 units (matches SVG marker refX).
        const hx = tx - ux * 26
        const hy = ty - uy * 26
        const ah = 7  // arrow length
        const aw = 4  // half-width
        ctx.fillStyle = stroke
        ctx.beginPath()
        ctx.moveTo(hx, hy)
        ctx.lineTo(hx - ux * ah - uy * aw, hy - uy * ah + ux * aw)
        ctx.lineTo(hx - ux * ah + uy * aw, hy - uy * ah - ux * aw)
        ctx.closePath()
        ctx.fill()
      }
      ctx.setLineDash([])
      ctx.globalAlpha = 1

      // Nodes — circles (with a label adjacent) instead of rounded rects.
      // Rendering thousands of rounded-rect text bubbles per tick costs more
      // than circles + text-on-zoom, and circles read better at far-zoom.
      const NODE_RADIUS = 8
      // Only render text labels above this zoom level; at far-zoom they're
      // unreadable AND dominate the per-frame budget.
      const showLabels = transform.k > 0.7
      ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'

      for (const n of nodes) {
        const x = n.x ?? 0, y = n.y ?? 0
        let alpha = 0.95
        if (reach) alpha = reach.all.has(n.id) ? 1 : 0.15
        if (search && !`${n.name} ${n.source} ${n.dtype} ${n.owner}`.toLowerCase().includes(search)) {
          alpha = Math.min(alpha, 0.18)
        }
        ctx.globalAlpha = alpha
        const color = colorMap.get(n.source) || '#94A3B8'
        ctx.fillStyle = color
        ctx.strokeStyle = color
        ctx.lineWidth = 1.5
        ctx.beginPath()
        ctx.arc(x, y, NODE_RADIUS, 0, Math.PI * 2)
        ctx.fill()
        if (showLabels) {
          ctx.fillStyle = 'rgba(0,0,0,0.35)'
          ctx.fillText(columnName(n.name), x + 1, y + NODE_RADIUS + 11)
          ctx.fillStyle = '#fff'
          ctx.fillText(columnName(n.name), x, y + NODE_RADIUS + 10)
        }
      }
      ctx.globalAlpha = 1
      ctx.restore()
    }

    const simulation = d3.forceSimulation<SimNode>(nodes)
      .force('link', d3.forceLink<SimNode, SimEdge>(edges).id(d => d.id).distance(80).strength(0.5))
      .force('charge', d3.forceManyBody<SimNode>().strength(-160).distanceMax(400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(20))
      .force('y', d3.forceY<SimNode>(rankYTarget(nodes, edges, height)).strength(0.18))
      // Cool the simulation faster for big graphs — otherwise we spend ~30s
      // rendering visibly-wiggling nodes that have already settled.
      .alphaDecay(0.04)

    simulation.on('tick', draw)
    simulationRef.current = simulation

    // ----- Hit-testing helpers ------------------------------------------------
    // Convert a pointer event to simulation-space coordinates (inverse of the
    // current zoom transform). Brute-force nearest-node search; for catalogs
    // <10k nodes this is well under 1ms per pointer event in modern V8.
    const pointerToSim = (event: PointerEvent | MouseEvent): { x: number; y: number } => {
      const r = canvas.getBoundingClientRect()
      const px = event.clientX - r.left
      const py = event.clientY - r.top
      // Apply inverse transform: (px - tx) / k
      return { x: (px - transform.x) / transform.k, y: (py - transform.y) / transform.k }
    }

    const findNearest = (sx: number, sy: number): SimNode | null => {
      // Hit threshold is in screen pixels; convert to simulation space so it
      // stays clickable at all zoom levels.
      const threshold = HIT_RADIUS_PX / transform.k
      let best: SimNode | null = null
      let bestDist = threshold * threshold
      for (const n of nodes) {
        const dx = (n.x ?? 0) - sx
        const dy = (n.y ?? 0) - sy
        const d2 = dx * dx + dy * dy
        if (d2 < bestDist) {
          bestDist = d2
          best = n
        }
      }
      return best
    }

    // ----- Drag (manual; can't use d3.drag on canvas elements directly) -----
    let dragging: SimNode | null = null
    let dragStart: { x: number; y: number } | null = null

    const onPointerDown = (event: PointerEvent) => {
      const { x, y } = pointerToSim(event)
      const hit = findNearest(x, y)
      if (hit) {
        dragging = hit
        dragStart = { x, y }
        hit.fx = hit.x
        hit.fy = hit.y
        simulation.alphaTarget(0.3).restart()
        canvas.setPointerCapture(event.pointerId)
        event.preventDefault()
      }
    }

    const onPointerMove = (event: PointerEvent) => {
      const sim = pointerToSim(event)
      if (dragging) {
        dragging.fx = sim.x
        dragging.fy = sim.y
        return
      }
      // Hover: tooltip + cursor change
      const hit = findNearest(sim.x, sim.y)
      if (hit) {
        canvas.style.cursor = 'pointer'
        const upstreamCount = resolvedEdges.filter(({ tgt }) => tgt.id === hit.id).length
        const downstreamCount = resolvedEdges.filter(({ src }) => src.id === hit.id).length
        tooltip.html(`
          <div style="font-weight:600;margin-bottom:4px">${hit.name}</div>
          <div style="color:var(--text-secondary)">${t('tooltip.dtype')}: ${hit.dtype || '-'} &nbsp;|&nbsp; ${t('tooltip.source')}: ${hit.source || '-'}</div>
          <div style="color:var(--text-secondary)">${t('tooltip.owner')}: ${hit.owner || t('tooltip.owner_unset')}</div>
          <div style="color:var(--text-tertiary);margin-top:4px;border-top:1px solid var(--border-subtle);padding-top:4px">
            ↑ ${t('tooltip.upstream')}: ${upstreamCount} &nbsp;—&nbsp; ↓ ${t('tooltip.downstream')}: ${downstreamCount}
          </div>
        `).style('opacity', '1')
        const cr = container.getBoundingClientRect()
        tooltip.style('left', (event.clientX - cr.left + 12) + 'px')
          .style('top', (event.clientY - cr.top - 10) + 'px')
      } else {
        canvas.style.cursor = 'grab'
        tooltip.style('opacity', '0')
      }
    }

    const onPointerUp = (event: PointerEvent) => {
      if (dragging) {
        const sim = pointerToSim(event)
        // Treat as click if pointer barely moved.
        const moved = dragStart && (Math.hypot(sim.x - dragStart.x, sim.y - dragStart.y) > 4)
        const clicked = dragging
        // Release physics pin — let the force layout absorb the node again.
        dragging.fx = null
        dragging.fy = null
        simulation.alphaTarget(0)
        if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId)
        dragging = null
        dragStart = null
        if (!moved) {
          setSelectedNode(prev => prev === clicked.id ? null : clicked.id)
        }
      }
    }

    const onDblClick = (event: MouseEvent) => {
      const { x, y } = pointerToSim(event)
      const hit = findNearest(x, y)
      if (hit) navigateRef.current(`/features/${encodeURIComponent(hit.name)}`)
    }

    const onClickEmpty = (event: MouseEvent) => {
      // Background click clears selection. We piggyback on pointerup for nodes,
      // so this only fires when nothing was hit.
      const { x, y } = pointerToSim(event)
      if (!findNearest(x, y)) setSelectedNode(null)
    }

    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerup', onPointerUp)
    canvas.addEventListener('pointercancel', onPointerUp)
    canvas.addEventListener('dblclick', onDblClick)
    canvas.addEventListener('click', onClickEmpty)
    canvas.style.cursor = 'grab'

    // ----- Zoom + pan via d3.zoom on the canvas element ---------------------
    // The wheel/drag-on-empty interactions are owned by d3.zoom; node-drag
    // listeners above stop propagation by calling preventDefault on
    // pointerdown when a node was hit, which keeps d3.zoom from kicking in
    // during a node drag.
    const zoom = d3.zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.15, 4])
      .filter((event: Event) => {
        // Block zoom-pan when the pointer is down on a node (we handle it
        // ourselves above). Wheel events always pass through for zoom.
        if (event.type === 'wheel') return true
        if (dragging) return false
        // Also block on mousedown over a node so d3.zoom's drag-pan doesn't
        // fight with our node-drag.
        const me = event as MouseEvent
        const { x, y } = pointerToSim(me)
        return !findNearest(x, y)
      })
      .on('zoom', (event) => {
        transform = event.transform
        draw()
      })
    d3.select(canvas).call(zoom)
    zoomRef.current = zoom as unknown as d3.ZoomBehavior<Element, unknown>

    return () => {
      simulation.stop()
      tooltip.remove()
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerup', onPointerUp)
      canvas.removeEventListener('pointercancel', onPointerUp)
      canvas.removeEventListener('dblclick', onDblClick)
      canvas.removeEventListener('click', onClickEmpty)
      d3.select(canvas).on('.zoom', null)
    }
  }, [filtered, colorMap, t, effectiveMode])

  // Selection / search use refs to avoid restarting the canvas effect every
  // keystroke. The canvas tick redraws automatically via simulation; for
  // selection changes after the simulation has cooled we trigger one redraw.
  const reachableRef = useRef(reachable)
  reachableRef.current = reachable
  const searchRef = useRef(graphSearch)
  searchRef.current = graphSearch

  // After selection / search changes in canvas mode, nudge the simulation so
  // the tick handler repaints with new highlights even when forces have settled.
  useEffect(() => {
    if (effectiveMode !== 'canvas') return
    const sim = simulationRef.current
    if (!sim) return
    sim.alpha(Math.max(sim.alpha(), 0.02)).restart()
  }, [reachable, graphSearch, effectiveMode])

  // Selection highlight effect for SVG mode — paints over whatever the render
  // effect produced. (Canvas mode handles this inside the draw call.)
  useEffect(() => {
    if (effectiveMode !== 'svg') return
    if (!svgRef.current) return
    const svg = d3.select(svgRef.current)
    const nodeG = svg.selectAll<SVGGElement, SimNode>('g.nodes > g')
    const edgeL = svg.selectAll<SVGLineElement, SimEdge>('g.edges > line')

    if (!reachable) {
      nodeG.select('rect').attr('opacity', 0.95)
      nodeG.selectAll('text').attr('opacity', 1)
      edgeL.attr('stroke-opacity', 0.55).attr('stroke', '#64748B').attr('marker-end', 'url(#lineage-arrow-default)')
      return
    }
    nodeG.select('rect').attr('opacity', d => reachable.all.has(d.id) ? 1 : 0.15)
    nodeG.selectAll('text').attr('opacity', function () {
      const datum = d3.select((this as Element).parentNode as Element).datum() as SimNode | undefined
      return datum && reachable.all.has(datum.id) ? 1 : 0.18
    })
    edgeL
      .attr('stroke-opacity', d => {
        const src = typeof d.source === 'string' ? d.source : d.source.id
        const tgt = typeof d.target === 'string' ? d.target : d.target.id
        return reachable.all.has(src) && reachable.all.has(tgt) ? 0.9 : 0.06
      })
      .attr('stroke', d => {
        const src = typeof d.source === 'string' ? d.source : d.source.id
        const tgt = typeof d.target === 'string' ? d.target : d.target.id
        return reachable.all.has(src) && reachable.all.has(tgt) ? '#1D9E75' : '#1f2937'
      })
      .attr('marker-end', d => {
        const src = typeof d.source === 'string' ? d.source : d.source.id
        const tgt = typeof d.target === 'string' ? d.target : d.target.id
        return reachable.all.has(src) && reachable.all.has(tgt)
          ? 'url(#lineage-arrow-highlight)'
          : 'url(#lineage-arrow-fade)'
      })
  }, [reachable, effectiveMode])

  // Search highlight: dim non-matching nodes (independent of selection).
  // SVG-only — canvas reads searchRef inside its draw loop.
  useEffect(() => {
    if (effectiveMode !== 'svg') return
    if (!svgRef.current) return
    const svg = d3.select(svgRef.current)
    const nodeG = svg.selectAll<SVGGElement, SimNode>('g.nodes > g')
    const q = graphSearch.toLowerCase().trim()
    if (!q) {
      // Don't override the selection effect — only act when there's no selection.
      if (!reachable) {
        nodeG.select('rect').attr('opacity', 0.95)
        nodeG.selectAll('text').attr('opacity', 1)
      }
      return
    }
    nodeG.each(function (d) {
      const text = `${d.name} ${d.source} ${d.dtype} ${d.owner}`.toLowerCase()
      const match = text.includes(q)
      d3.select(this).select('rect').attr('opacity', match ? 1 : 0.15)
      d3.select(this).selectAll('text').attr('opacity', match ? 1 : 0.18)
    })
  }, [graphSearch, reachable, effectiveMode])

  const handleFit = () => {
    if (effectiveMode === 'svg') {
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
        (zoomRef.current as unknown as d3.ZoomBehavior<SVGSVGElement, unknown>).transform,
        d3.zoomIdentity.translate(tx, ty).scale(scale),
      )
    } else {
      // Canvas: compute bounds from node positions, then apply via d3.zoom.
      if (!canvasRef.current || !zoomRef.current) return
      const sim = simulationRef.current
      if (!sim) return
      const nodes = sim.nodes()
      if (nodes.length === 0) return
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
      for (const n of nodes) {
        const x = n.x ?? 0, y = n.y ?? 0
        if (x < minX) minX = x
        if (y < minY) minY = y
        if (x > maxX) maxX = x
        if (y > maxY) maxY = y
      }
      const bw = maxX - minX, bh = maxY - minY
      if (bw <= 0 || bh <= 0) return
      const w = canvasRef.current.clientWidth
      const h = canvasRef.current.clientHeight
      const scale = 0.85 / Math.max(bw / w, bh / h)
      const tx = (w - scale * (minX + maxX)) / 2
      const ty = (h - scale * (minY + maxY)) / 2
      d3.select(canvasRef.current).transition().duration(500).call(
        (zoomRef.current as unknown as d3.ZoomBehavior<HTMLCanvasElement, unknown>).transform,
        d3.zoomIdentity.translate(tx, ty).scale(scale),
      )
    }
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

  const isEmpty = data && data.edges.length === 0

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 64px)' }}>
      <div className="flex justify-between items-center mb-4 shrink-0 flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
          <p className="text-sm text-[var(--text-tertiary)] mt-0.5 max-w-2xl">{t('page.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={graphSearch}
            onChange={e => setGraphSearch(e.target.value)}
            placeholder={t('filter_placeholder')}
            className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-1.5 text-[12px] w-44 focus:border-brand outline-none"
          />
        </div>
      </div>

      {loading ? (
        <Skeleton className="flex-1 min-h-[500px]" />
      ) : isEmpty ? (
        <div className="flex flex-col items-center justify-center flex-1 min-h-[400px] text-center gap-3 px-6">
          <p className="text-[var(--text-primary)] font-medium">{t('empty.title')}</p>
          <p className="text-[var(--text-tertiary)] text-sm max-w-md">{t('empty.subtitle')}</p>
          <div className="mt-2 text-left bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg px-4 py-3 text-sm">
            <div className="text-[var(--text-secondary)] mb-1">{t('empty.cta_detect')}</div>
            <code className="font-mono text-[12px] text-brand">{t('empty.cta_detect_cmd')}</code>
            <div className="text-[var(--text-tertiary)] text-xs mt-3">{t('empty.cta_apply_hint')}</div>
          </div>
        </div>
      ) : (
        <div ref={containerRef} className="relative flex-1 min-h-[500px] bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
          {effectiveMode === 'svg'
            ? <svg ref={svgRef} className="w-full h-full" />
            : <canvas ref={canvasRef} className="w-full h-full block" />
          }

          {/* Top-right controls */}
          <div className="absolute top-3 right-3 flex flex-col gap-2 z-10 max-w-[220px]">
            <button onClick={handleFit} className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm hover:bg-[var(--bg-secondary)]" title={t('actions.fit_title')}>
              <Maximize2 size={13} /> {t('actions.fit')}
            </button>
            <button onClick={handleResetLayout} className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm hover:bg-[var(--bg-secondary)]" title={t('actions.reset_title')}>
              <RotateCcw size={13} /> {t('actions.reset_layout')}
            </button>

            <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm p-2 flex flex-col gap-1.5">
              <label className="flex items-center gap-1.5 text-[11px] cursor-pointer">
                <input
                  type="checkbox"
                  checked={hideIsolated}
                  onChange={e => setHideIsolated(e.target.checked)}
                  className="accent-brand"
                />
                <span>{t('filters.hide_isolated')}</span>
              </label>
            </div>

            {/* Render-mode toggle: Auto / SVG / Canvas. Auto picks based on
                node count, SVG/Canvas force the choice for debugging or when
                operators want crisper text on small graphs. */}
            <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm p-2">
              <p className="text-[10px] font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-1">
                {t('render_mode.label')}
              </p>
              <div className="flex gap-1">
                {(['auto', 'svg', 'canvas'] as const).map(mode => (
                  <button
                    key={mode}
                    onClick={() => setRenderMode(mode)}
                    className={
                      'flex-1 px-2 py-1 text-[10px] font-medium rounded border transition-colors ' +
                      (renderMode === mode
                        ? 'bg-brand/10 border-brand text-brand'
                        : 'bg-[var(--bg-primary)] border-[var(--border-default)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]')
                    }
                    title={t(`render_mode.${mode}_title`, { count: filtered.total })}
                  >
                    {t(`render_mode.${mode}`)}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-[var(--text-tertiary)] mt-1.5">
                {t('render_mode.active', { mode: t(`render_mode.${effectiveMode}`), count: filtered.total })}
              </p>
            </div>

            {sources.length > 1 && (
              <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm p-2">
                <p className="text-[10px] font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-1">{t('filters.sources_label')}</p>
                <div className="max-h-[200px] overflow-y-auto pr-1">
                  {sources.map(src => (
                    <label key={src} className="flex items-center gap-1.5 text-[11px] cursor-pointer py-0.5">
                      <input
                        type="checkbox"
                        checked={visibleSources.has(src)}
                        onChange={() => toggleSource(src)}
                        className="accent-brand"
                      />
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: colorMap.get(src) || '#94A3B8' }} />
                      <span className="truncate max-w-[120px]">{src}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="absolute bottom-3 left-3 bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg shadow-sm p-2.5 z-10">
            <p className="text-[10px] font-medium text-[var(--text-tertiary)] uppercase tracking-wide mb-1.5">{t('legend.title')}</p>
            <div className="flex flex-col gap-1.5 text-[10px] text-[var(--text-tertiary)]">
              <div className="flex items-center gap-2">
                <svg width="32" height="10">
                  <line x1="0" y1="5" x2="22" y2="5" stroke="#64748B" strokeWidth="1.4" />
                  <polygon points="22,1 30,5 22,9" fill="#64748B" />
                </svg>
                <span>{t('legend.edge_dir')}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-6 h-[2px] rounded" style={{ background: '#64748B' }} />
                <span>{t('legend.manual')}</span>
              </div>
              <div className="flex items-center gap-2">
                <svg width="24" height="2">
                  <line x1="0" y1="1" x2="24" y2="1" stroke="#64748B" strokeWidth="1.4" strokeDasharray="4 3" />
                </svg>
                <span>{t('legend.sqlglot')}</span>
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

/**
 * Compute a per-node target Y based on a topological rank (longest distance
 * from any root). Cheap O(V+E) BFS — good enough to nudge the force layout
 * into a top-down hierarchy without dragging in a full Sugiyama implementation.
 * Returns a function suitable for d3.forceY().
 */
function rankYTarget(nodes: SimNode[], edges: SimEdge[], height: number): (n: SimNode) => number {
  const incoming = new Map<string, string[]>()
  const outgoing = new Map<string, string[]>()
  const ids = new Set(nodes.map(n => n.id))
  for (const e of edges) {
    const s = typeof e.source === 'string' ? e.source : e.source.id
    const t = typeof e.target === 'string' ? e.target : e.target.id
    if (!ids.has(s) || !ids.has(t)) continue
    if (!incoming.has(t)) incoming.set(t, [])
    incoming.get(t)!.push(s)
    if (!outgoing.has(s)) outgoing.set(s, [])
    outgoing.get(s)!.push(t)
  }

  const rank = new Map<string, number>()
  const roots = nodes.filter(n => (incoming.get(n.id) ?? []).length === 0).map(n => n.id)
  const queue = roots.map(r => ({ id: r, depth: 0 }))
  while (queue.length > 0) {
    const cur = queue.shift()!
    const prev = rank.get(cur.id) ?? -1
    if (cur.depth <= prev) continue
    rank.set(cur.id, cur.depth)
    for (const child of outgoing.get(cur.id) ?? []) {
      queue.push({ id: child, depth: cur.depth + 1 })
    }
  }
  // Nodes only reachable inside cycles get rank = max-incoming + 1 fallback.
  for (const n of nodes) {
    if (!rank.has(n.id)) rank.set(n.id, 0)
  }
  let maxRank = 0
  for (const r of rank.values()) if (r > maxRank) maxRank = r
  const span = Math.max(maxRank, 1)
  const top = 60
  const bottom = Math.max(height - 60, top + 100)
  return (n: SimNode) => {
    const r = rank.get(n.id) ?? 0
    return top + (bottom - top) * (r / span)
  }
}
