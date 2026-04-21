import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, RefreshCw, Check, AlertTriangle, Shield, FileText, FolderSearch, X, ChevronDown, ChevronRight, Pencil, Download } from 'lucide-react'
import { api, invalidateCache, timeAgo } from '../api'
import { DataTable } from '../components/DataTable'
import { Badge } from '../components/Badge'
import { ExportModal } from '../components/ExportModal'
import { FeatureSelector, toFeatureItems } from '../components/FeatureSelector'
import { Tag } from '../components/Tag'
import { Modal } from '../components/Modal'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

interface FeatureRow {
  name: string
  has_doc: boolean
  generation_hints: string | null
  dtype: string
  tags: string[]
  owner: string
  column_name: string
  stats: Record<string, number>
  created_at: string
  updated_at: string
  id: string
  data_source_id: string
  description: string
  definition: string | null
  definition_type: string | null
  health_score?: number
  health_grade?: string
  health_breakdown?: { documentation: number; drift: number; usage: number }
  search_score?: number
  highlight?: Record<string, string[]>
  short_description?: string
}

const GRADE_COLORS: Record<string, string> = {
  A: 'bg-green-500/15 text-green-600 dark:text-green-400',
  B: 'bg-teal-500/15 text-teal-600 dark:text-teal-400',
  C: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  D: 'bg-red-500/15 text-red-600 dark:text-red-400',
}

export function Features() {
  const { name: paramName } = useParams()
  const navigate = useNavigate()
  const [features, setFeatures] = useState<FeatureRow[]>([])
  const [sources, setSources] = useState<{ name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [filtered, setFiltered] = useState<FeatureRow[]>([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [selected, setSelected] = useState<FeatureRow | null>(null)
  const [healthFilter, setHealthFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [dtypeFilter, setDtypeFilter] = useState('')
  const [docFilter, setDocFilter] = useState(false)
  const [tagFilter, setTagFilter] = useState('')
  const [selectedForExport, setSelectedForExport] = useState<Set<string>>(new Set())
  const [exportOpen, setExportOpen] = useState(false)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [scanModalOpen, setScanModalOpen] = useState(false)
  const [genModalOpen, setGenModalOpen] = useState(false)
  const [genProgress, setGenProgress] = useState<string | null>(null)
  const [batchJob, setBatchJob] = useState<{ jobId: string; total: number } | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    invalidateCache('/features')
    const params: Record<string, string> = {}
    if (sourceFilter) params.source = sourceFilter
    if (searchQuery) params.search = searchQuery
    if (dtypeFilter) params.dtype = dtypeFilter
    if (healthFilter === 'attention') params.health_grade = ''  // handled client-side
    if (healthFilter === 'A') params.health_grade = 'A'
    if (docFilter) params.has_doc = 'false'
    if (tagFilter) params.tag = tagFilter
    if (searchQuery) {
      params.sort = 'name'  // server returns by relevance when search present
    }

    Promise.all([api.features.list(Object.keys(params).length > 0 ? params : undefined), api.sources.list().catch(() => [])])
      .then(([f, s]) => {
        let list = Array.isArray(f) ? f as FeatureRow[] : []
        // Client-side health filter for "attention" (C or D)
        if (healthFilter === 'attention') {
          list = list.filter(r => r.health_grade === 'C' || r.health_grade === 'D')
        }
        setFeatures(list)
        setFiltered(list)
        setSources(Array.isArray(s) ? s : [])
      })
      .finally(() => setLoading(false))
  }, [sourceFilter, searchQuery, dtypeFilter, healthFilter, docFilter, tagFilter])

  useEffect(() => { load() }, [load])

  // Poll batch job progress
  useEffect(() => {
    if (!batchJob) return
    const interval = setInterval(async () => {
      try {
        const status = await api.docs.batchStatus(batchJob.jobId)
        const done = status.completed + status.failed
        setGenProgress(`Generating... (${done}/${status.total})`)
        if (status.status === 'done') {
          clearInterval(interval)
          setGenProgress(null)
          setBatchJob(null)
          invalidateCache('/features')
          invalidateCache('/docs')
          load()
        }
      } catch {
        clearInterval(interval)
        setGenProgress(null)
        setBatchJob(null)
      }
    }, 2000)
    return () => clearInterval(interval)
  }, [batchJob])

  // Auto-open modal from URL param
  useEffect(() => {
    if (paramName && features.length > 0) {
      const decoded = decodeURIComponent(paramName)
      const feat = features.find((f) => f.name === decoded)
      if (feat) setSelected(feat)
    }
  }, [paramName, features])

  const hasActiveFilters = !!(sourceFilter || searchQuery || dtypeFilter || healthFilter || docFilter || tagFilter)

  const clearAllFilters = () => {
    setSourceFilter('')
    setSearchQuery('')
    setDtypeFilter('')
    setHealthFilter('')
    setDocFilter(false)
    setTagFilter('')
  }

  const selectFeature = (f: FeatureRow) => {
    setSelected(f)
    navigate(`/features/${encodeURIComponent(f.name)}`, { replace: true })
  }

  const closeModal = () => {
    setSelected(null)
    navigate('/features', { replace: true })
  }

  const undocCount = features.filter((f) => !f.has_doc).length

  const handleAddSource = async (form: Record<string, string>) => {
    try {
      const payload: Record<string, unknown> = { path: form.path }
      if (form.name) payload.name = form.name
      if (form.description) payload.description = form.description
      if (form.owner) payload.owner = form.owner
      if (form.tags) payload.tags = form.tags.split(',').map((t: string) => t.trim())
      const src = await api.sources.add(payload) as { name: string }
      await api.sources.scan(src.name)
      invalidateCache('/features')
      invalidateCache('/sources')
      setAddModalOpen(false)
      load()
    } catch { /* ignore */ }
  }

  const toggleExportSelect = (name: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedForExport(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const columns = [
    { key: '_select', label: '', sortable: false, render: (r: FeatureRow) => (
      <input
        type="checkbox"
        checked={selectedForExport.has(r.name)}
        onChange={() => undefined}
        onClick={(e) => toggleExportSelect(r.name, e)}
        className="accent-accent"
      />
    )},
    { key: 'name', label: 'Name', render: (r: FeatureRow) => {
      const hl = (r as FeatureRow & { highlight?: Record<string, string[]> }).highlight
      const terms = hl ? [...new Set(Object.values(hl).flat())] : []
      return <span className="font-medium text-accent"><HighlightedText text={r.name} terms={terms} /></span>
    }},
    { key: 'source', label: 'Source', sortable: false, render: (r: FeatureRow) => <span className="text-[var(--text-secondary)]">{r.name?.split('.')[0] || ''}</span> },
    { key: 'dtype', label: 'Dtype', render: (r: FeatureRow) => <span className="font-mono text-xs">{r.dtype}</span> },
    { key: 'tags', label: 'Tags', sortable: false, render: (r: FeatureRow) => (
      <div className="flex gap-1 flex-wrap">{(r.tags || []).map((t: string, i: number) => <Tag key={i}>{t}</Tag>)}</div>
    )},
    { key: 'has_doc', label: 'Docs', render: (r: FeatureRow) => r.has_doc ? <Check size={14} className="text-[var(--success)]" /> : <span className="text-[var(--text-tertiary)]">-</span> },
    { key: 'health_score', label: 'Health', render: (r: FeatureRow) => {
      const searchScore = (r as FeatureRow & { search_score?: number }).search_score
      if (searchScore != null) {
        const pct = Math.round(searchScore * 100)
        return (
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-[var(--bg-secondary)] rounded-full overflow-hidden">
              <div className="h-full bg-accent rounded-full" style={{ width: `${pct}%` }} />
            </div>
            <span className="text-[11px] font-mono text-[var(--text-tertiary)]">{pct}%</span>
          </div>
        )
      }
      const grade = r.health_grade || '-'
      const score = r.health_score ?? '-'
      const cls = GRADE_COLORS[grade] || 'bg-[var(--bg-secondary)] text-[var(--text-tertiary)]'
      return <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold ${cls}`}>{grade} {score}</span>
    }},
    { key: 'owner', label: 'Owner' },
  ]

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-semibold">Features</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[var(--text-tertiary)]">{filtered.length} features</span>
          <button onClick={load} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <SearchInput placeholder="Search features..." onSearch={setSearchQuery} className="w-full sm:max-w-xs" />
        <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">All Sources</option>
          {sources.map((s) => <option key={s.name} value={s.name}>{s.name}</option>)}
        </select>
        <select value={dtypeFilter} onChange={(e) => setDtypeFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">All Types</option>
          <option value="int64">int64</option>
          <option value="float64">float64</option>
          <option value="string">string</option>
          <option value="bool">bool</option>
        </select>
        <select value={healthFilter} onChange={(e) => setHealthFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]">
          <option value="">All Grades</option>
          <option value="attention">Needs Attention (C or D)</option>
          <option value="A">Grade A Only</option>
        </select>
        <button
          onClick={() => setDocFilter(!docFilter)}
          className={`px-3 py-2 text-[13px] rounded-lg border transition-colors ${docFilter ? 'bg-accent text-white border-accent' : 'bg-[var(--bg-primary)] border-[var(--border-default)] hover:bg-[var(--bg-secondary)]'}`}
        >
          Undocumented only
        </button>
        {hasActiveFilters && (
          <button onClick={clearAllFilters} className="text-xs text-accent hover:underline">
            Clear all filters
          </button>
        )}
        {(undocCount > 0 || genProgress) && (
          <button
            onClick={() => !genProgress && setGenModalOpen(true)}
            disabled={!!genProgress}
            className="flex items-center gap-1.5 px-4 py-2 border border-[var(--border-default)] rounded-lg text-[13px] font-medium hover:bg-[var(--bg-secondary)] disabled:opacity-50 transition-colors"
          >
            {genProgress ? <><RefreshCw size={14} className="animate-spin" /> {genProgress}</> : <><FileText size={14} /> Generate Docs ({undocCount} remaining)</>}
          </button>
        )}
        <button onClick={() => setScanModalOpen(true)} className="flex items-center gap-1.5 px-4 py-2 border border-[var(--border-default)] rounded-lg text-[13px] font-medium hover:bg-[var(--bg-secondary)] transition-colors">
          <FolderSearch size={16} /> Bulk Scan
        </button>
        {selectedForExport.size > 0 && (
          <button onClick={() => setExportOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium hover:bg-accent-emphasis transition-colors">
            <Download size={16} /> Export Selected ({selectedForExport.size})
          </button>
        )}
        <button onClick={() => setAddModalOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium hover:bg-accent-emphasis transition-colors">
          <Plus size={16} /> Add Source
        </button>
      </div>

      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
        {loading ? <div className="p-5"><Skeleton className="h-48" /></div> : (
          <DataTable columns={columns} data={filtered} onRowClick={selectFeature} />
        )}
      </div>

      {selected && (
        <FeatureDetailModal feature={selected} onClose={closeModal} onDocGenerated={load} />
      )}

      <GenerateDocsModal
        open={genModalOpen}
        onClose={() => setGenModalOpen(false)}
        features={features}
        selectedSpecs={selectedForExport}
        onStarted={(jobId, total) => {
          setGenModalOpen(false)
          setBatchJob({ jobId, total })
          setGenProgress(`Generating... (0/${total})`)
        }}
      />
      <AddSourceModal open={addModalOpen} onClose={() => setAddModalOpen(false)} onSubmit={handleAddSource} />
      <BulkScanModal open={scanModalOpen} onClose={() => setScanModalOpen(false)} onDone={() => { setScanModalOpen(false); load() }} />
      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        title={`${selectedForExport.size} features`}
        featureSpecs={[...selectedForExport]}
      />
    </div>
  )
}


function FeatureDetailModal({ feature, onClose, onDocGenerated }: { feature: FeatureRow; onClose: () => void; onDocGenerated: () => void }) {
  const [doc, setDoc] = useState<Record<string, unknown> | null>(null)
  const [docLoading, setDocLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [monitoring, setMonitoring] = useState<Record<string, unknown> | null>(null)
  const [monLoading, setMonLoading] = useState(true)
  const [blLoading, setBlLoading] = useState(false)
  const [definition, setDefinition] = useState<Record<string, unknown> | null>(null)
  const [defLoading, setDefLoading] = useState(true)
  const [defEditing, setDefEditing] = useState(false)
  const [defForm, setDefForm] = useState({ definition: '', definition_type: 'sql' })
  const [usageData, setUsageData] = useState<Record<string, unknown> | null>(null)
  const [usageLoading, setUsageLoading] = useState(true)
  const [hintData, setHintData] = useState<{ hints: string | null } | null>(null)
  const [hintEditing, setHintEditing] = useState(false)
  const [hintDraft, setHintDraft] = useState('')
  const [activeTab, setActiveTab] = useState<'overview' | 'history'>('overview')
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)

  useEffect(() => {
    setDocLoading(true)
    setMonLoading(true)
    setDefLoading(true)
    setUsageLoading(true)
    api.docs.get(feature.name).then(setDoc).catch(() => setDoc(null)).finally(() => setDocLoading(false))
    api.monitor.check({ feature_name: feature.name }).then(setMonitoring).catch(() => setMonitoring(null)).finally(() => setMonLoading(false))
    api.definitions.get(feature.name).then(setDefinition).catch(() => setDefinition(null)).finally(() => setDefLoading(false))
    api.usage.feature(feature.name, 30).then(setUsageData).catch(() => setUsageData(null)).finally(() => setUsageLoading(false))
    api.hints.get(feature.name).then(setHintData).catch(() => setHintData(null))
    setActiveTab('overview')
    setVersionsLoading(true)
    api.features.versions(feature.name).then(setVersions).catch(() => setVersions([])).finally(() => setVersionsLoading(false))
  }, [feature.name])

  const generateDoc = async () => {
    setGenerating(true)
    try {
      await api.docs.generate({ feature_name: feature.name })
      invalidateCache('/docs')
      invalidateCache('/features')
      const d = await api.docs.get(feature.name)
      setDoc(d)
      onDocGenerated()
    } catch { /* ignore */ }
    setGenerating(false)
  }

  const computeBaseline = async () => {
    setBlLoading(true)
    try {
      await api.monitor.baseline()
      invalidateCache('/monitor')
      const m = await api.monitor.check({ feature_name: feature.name })
      setMonitoring(m)
    } catch { /* ignore */ }
    setBlLoading(false)
  }

  const stats = feature.stats || {}
  const source = feature.name?.split('.')[0] || ''
  const statKeys = ['mean', 'std', 'min', 'max', 'null_ratio', 'unique_count']
  const hasStats = statKeys.some((k) => stats[k] != null)

  return (
    <Modal open={true} onClose={onClose} title={feature.name} maxWidth="max-w-2xl">
      {/* Tab bar */}
      <div className="flex gap-4 border-b border-[var(--border-subtle)] mb-5">
        <button
          onClick={() => setActiveTab('overview')}
          className={`pb-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'overview' ? 'border-accent text-accent' : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'}`}
        >Overview</button>
        <button
          onClick={() => setActiveTab('history')}
          className={`pb-2 text-sm font-medium border-b-2 transition-colors ${activeTab === 'history' ? 'border-accent text-accent' : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'}`}
        >History ({versions.length})</button>
      </div>

      {activeTab === 'history' ? (
        <VersionTimeline versions={versions} loading={versionsLoading} />
      ) : (<>

      {/* Header badges */}
      <div className="flex items-center gap-2 flex-wrap mb-5">
        <Badge variant="info">{source}</Badge>
        {(feature.tags || []).map((t: string, i: number) => <Tag key={i}>{t}</Tag>)}
      </div>

      {/* Health Score */}
      {feature.health_score != null && (
        <Section title="Health Score">
          <HealthBreakdown feature={feature} />
        </Section>
      )}

      {/* Metadata */}
      <Section title="Metadata">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-4">
          <MetaItem label="Data Type" value={feature.dtype} mono />
          <MetaItem label="Column" value={feature.column_name} mono />
          <MetaItem label="Owner" value={feature.owner || '-'} />
          {feature.created_at && <MetaItem label="Created" value={timeAgo(feature.created_at)} />}
          {feature.updated_at && <MetaItem label="Updated" value={timeAgo(feature.updated_at)} />}
        </div>
      </Section>

      {/* Statistics */}
      {hasStats && (
        <Section title="Statistics">
          <div className="grid grid-cols-3 gap-x-6 gap-y-4">
            {([
              { label: 'Mean',         value: stats.mean,         format: 'decimal' as const },
              { label: 'Std',          value: stats.std,          format: 'decimal' as const },
              { label: 'Min',          value: stats.min,          format: 'decimal' as const },
              { label: 'Max',          value: stats.max,          format: 'decimal' as const },
              { label: 'Null Ratio',   value: stats.null_ratio,   format: 'decimal' as const },
              { label: 'Unique Count', value: stats.unique_count, format: 'integer' as const },
            ] as const)
              .filter(s => s.value !== null && s.value !== undefined)
              .map(s => (
                <div key={s.label}>
                  <div className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)] font-medium mb-1">
                    {s.label}
                  </div>
                  <div className="text-sm font-mono text-[var(--text-primary)] tabular-nums">
                    {s.format === 'integer'
                      ? Math.round(s.value as number).toLocaleString()
                      : (s.value as number).toFixed(4)}
                  </div>
                </div>
              ))}
          </div>
        </Section>
      )}

      {/* Documentation */}
      <Section title="Documentation">
        {docLoading ? (
          <Skeleton className="h-12" />
        ) : doc ? (
          <div className="space-y-2 text-sm">
            <p>{String(doc.short_description || '')}</p>
            {doc.long_description ? <p className="text-[var(--text-secondary)]">{String(doc.long_description)}</p> : null}
            {doc.expected_range ? (
              <p className="text-xs text-[var(--text-tertiary)]">
                <span className="font-medium">Expected range:</span> {String(doc.expected_range)}
              </p>
            ) : null}
            {doc.potential_issues ? (
              <p className="text-xs text-[var(--text-tertiary)]">
                <span className="font-medium">Potential issues:</span> {String(doc.potential_issues)}
              </p>
            ) : null}
            {(doc.context_features || doc.hints_used) ? (
              <div className="mt-2 pt-2 border-t border-[var(--border-subtle)] flex items-center gap-2 flex-wrap text-[11px] text-[var(--text-tertiary)]">
                {doc.hints_used ? <Badge variant="info">hints used</Badge> : null}
                {doc.context_features ? (
                  <span>Context: {JSON.parse(String(doc.context_features)).length} related features</span>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">No documentation yet</span>
            <button onClick={generateDoc} disabled={generating} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent text-white rounded-lg disabled:opacity-50">
              <RefreshCw size={12} className={generating ? 'animate-spin' : ''} />
              {generating ? 'Generating...' : 'Generate'}
            </button>
          </div>
        )}
      </Section>

      {/* Generation Hints */}
      <Section title="Generation Hints">
        {hintEditing ? (
          <div className="space-y-2">
            <textarea value={hintDraft} onChange={(e) => setHintDraft(e.target.value)} rows={2}
              placeholder="e.g. Computed from last 30 days. 1=churned, 0=active."
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-xs focus:border-accent outline-none" />
            <div className="flex gap-2">
              <button onClick={async () => {
                await api.hints.save(feature.name, hintDraft)
                invalidateCache('/features')
                setHintData({ hints: hintDraft })
                setHintEditing(false)
              }} className="px-3 py-1.5 text-xs bg-accent text-white rounded-lg">Save</button>
              <button onClick={() => setHintEditing(false)} className="px-3 py-1.5 text-xs border border-[var(--border-default)] rounded-lg">Cancel</button>
            </div>
          </div>
        ) : hintData?.hints ? (
          <div>
            <p className="text-sm text-[var(--text-secondary)] mb-1">{hintData.hints}</p>
            <button onClick={() => { setHintDraft(hintData.hints || ''); setHintEditing(true) }}
              className="text-xs text-accent hover:underline">Edit</button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">No hint set</span>
            <button onClick={() => { setHintDraft(''); setHintEditing(true) }}
              className="text-xs text-accent hover:underline">Add hint</button>
            <span className="text-[10px] text-[var(--text-tertiary)]" title="Hints are treated as ground truth by the AI generator">ℹ</span>
          </div>
        )}
      </Section>

      {/* Definition */}
      <Section title="Definition">
        {defLoading ? (
          <Skeleton className="h-10" />
        ) : defEditing ? (
          <div className="space-y-2">
            <select value={defForm.definition_type} onChange={(e) => setDefForm((f) => ({ ...f, definition_type: e.target.value }))}
              className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-2 py-1 text-xs">
              <option value="sql">SQL</option>
              <option value="python">Python</option>
              <option value="manual">Manual</option>
            </select>
            <textarea value={defForm.definition} onChange={(e) => setDefForm((f) => ({ ...f, definition: e.target.value }))}
              rows={4} className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-xs font-mono focus:border-accent outline-none" />
            <div className="flex gap-2">
              <button onClick={async () => {
                await api.definitions.save(feature.name, defForm)
                invalidateCache('/features')
                const d = await api.definitions.get(feature.name)
                setDefinition(d)
                setDefEditing(false)
              }} className="px-3 py-1.5 text-xs bg-accent text-white rounded-lg">Save</button>
              <button onClick={() => setDefEditing(false)} className="px-3 py-1.5 text-xs border border-[var(--border-default)] rounded-lg">Cancel</button>
            </div>
          </div>
        ) : definition?.definition ? (
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="info">{String(definition.definition_type)}</Badge>
              <button onClick={() => { setDefForm({ definition: String(definition.definition), definition_type: String(definition.definition_type) }); setDefEditing(true) }}
                className="text-xs text-accent hover:underline">Edit</button>
            </div>
            <pre className="bg-[var(--bg-secondary)] rounded-lg p-3 text-xs font-mono overflow-x-auto whitespace-pre-wrap">{String(definition.definition)}</pre>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">No definition set</span>
            <button onClick={() => { setDefForm({ definition: '', definition_type: 'sql' }); setDefEditing(true) }}
              className="text-xs text-accent hover:underline">Add definition</button>
          </div>
        )}
      </Section>

      {/* Usage */}
      <Section title="Usage">
        {usageLoading ? (
          <Skeleton className="h-10" />
        ) : usageData ? (
          <div>
            <p className="text-sm">
              <span className="font-medium">{Number(usageData.views || 0)}</span> views
              {' \u00b7 '}
              <span className="font-medium">{Number(usageData.queries || 0)}</span> queries
              <span className="text-[var(--text-tertiary)]"> (last 30 days)</span>
            </p>
            {(usageData.daily as { date: string; count: number }[] | undefined)?.length ? <MiniBarChart data={usageData.daily as { date: string; count: number }[]} /> : null}
            {usageData.last_seen ? (
              <p className="text-xs text-[var(--text-tertiary)] mt-1">Last seen: {timeAgo(String(usageData.last_seen))}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-[var(--text-tertiary)]">No usage data</p>
        )}
      </Section>

      {/* Monitoring */}
      <Section title="Monitoring" last>
        {monLoading ? (
          <Skeleton className="h-10" />
        ) : (() => { const details = (monitoring?.details || []) as { severity: string; psi: number | null; checked_at?: string }[]; return details.length > 0 })() ? (
          <div className="flex items-center gap-4 flex-wrap">
            {(() => {
              const details = (monitoring?.details || []) as { severity: string; psi: number | null; checked_at?: string }[]
              const r = details[0]
              const status = r.severity || 'unknown'
              const variant = status === 'healthy' ? 'success' : status === 'warning' ? 'warning' : status === 'critical' ? 'critical' : 'info'
              return (
                <>
                  <Badge variant={variant} icon={status === 'healthy' ? Shield : AlertTriangle}>
                    {status}
                  </Badge>
                  {r.psi != null && <span className="text-xs text-[var(--text-secondary)]">PSI: {r.psi.toFixed(4)}</span>}
                  {r.checked_at && <span className="text-xs text-[var(--text-tertiary)]">Checked {timeAgo(r.checked_at)}</span>}
                </>
              )
            })()}
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-sm text-[var(--text-tertiary)]">No baseline</span>
            <button onClick={computeBaseline} disabled={blLoading} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent text-white rounded-lg disabled:opacity-50">
              {blLoading ? 'Computing...' : 'Compute Baseline'}
            </button>
          </div>
        )}
      </Section>
      </>)}
    </Modal>
  )
}


function Section({ title, children, last }: { title: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className={last ? '' : 'mb-4 pb-4 border-b border-[var(--border-subtle)]'}>
      <h4 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2.5">{title}</h4>
      {children}
    </div>
  )
}


function MetaItem({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wide">{label}</div>
      <div className={`text-sm ${mono ? 'font-mono' : ''}`}>{value || '-'}</div>
    </div>
  )
}


function GenerateDocsModal({ open, onClose, features, selectedSpecs, onStarted }: {
  open: boolean
  onClose: () => void
  features: FeatureRow[]
  selectedSpecs?: Set<string>
  onStarted: (jobId: string, total: number) => void
}) {
  const [scope, setScope] = useState<'undocumented' | 'all' | 'group' | 'selected'>('undocumented')
  const [globalHint, setGlobalHint] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [editingHint, setEditingHint] = useState<string | null>(null)
  const [hintDrafts, setHintDrafts] = useState<Record<string, string>>({})
  const [hintsOverrides, setHintsOverrides] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [groups, setGroups] = useState<{ name: string; member_count: number }[]>([])
  const [selectedGroup, setSelectedGroup] = useState('')
  const [groupMembers, setGroupMembers] = useState<string[]>([])
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set())

  const undocumented = features.filter(f => !f.has_doc)
  const hasTableSelection = (selectedSpecs?.size ?? 0) > 0

  let targetFeatures: FeatureRow[]
  if (scope === 'group') {
    targetFeatures = features.filter(f => groupMembers.includes(f.name))
  } else if (scope === 'selected') {
    targetFeatures = features.filter(f => manualSelected.has(f.name))
  } else if (scope === 'all') {
    targetFeatures = features
  } else {
    targetFeatures = undocumented
  }
  const targetCount = targetFeatures.length
  const canGenerate = targetCount > 0 && !(scope === 'group' && !selectedGroup)

  const getHint = (f: FeatureRow) => hintsOverrides[f.name] ?? f.generation_hints

  const saveHint = async (featureName: string) => {
    const draft = hintDrafts[featureName] ?? ''
    try {
      await api.hints.save(featureName, draft)
      setHintsOverrides(prev => ({ ...prev, [featureName]: draft }))
      setEditingHint(null)
    } catch { /* ignore */ }
  }

  const handleGenerate = async () => {
    if (!canGenerate) return
    setSubmitting(true)
    try {
      const specs = targetFeatures.map(f => f.name)
      const res = await api.docs.generateBatch({
        feature_specs: specs,
        regenerate_existing: scope === 'all',
        global_hint: globalHint.trim() || null,
      })
      onStarted(res.job_id, res.total)
    } catch { /* ignore */ }
    setSubmitting(false)
  }

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setScope(hasTableSelection ? 'selected' : 'undocumented')
      setGlobalHint('')
      setShowPreview(false)
      setEditingHint(null)
      setHintDrafts({})
      setHintsOverrides({})
      setSubmitting(false)
      setSelectedGroup('')
      setGroupMembers([])
      setManualSelected(new Set(selectedSpecs || []))
      api.groups.list().then(g => setGroups(Array.isArray(g) ? g : [])).catch(() => setGroups([]))
    }
  }, [open, hasTableSelection])

  // Fetch group members when group selection changes
  useEffect(() => {
    if (scope === 'group' && selectedGroup) {
      api.groups.get(selectedGroup)
        .then((g: Record<string, unknown>) => {
          const members = (g.members || []) as { name: string }[]
          setGroupMembers(members.map(m => m.name))
        })
        .catch(() => setGroupMembers([]))
    }
  }, [scope, selectedGroup])

  return (
    <Modal open={open} onClose={onClose} title="Generate Documentation" maxWidth="max-w-2xl" actions={
      <>
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">Cancel</button>
        <button onClick={handleGenerate} disabled={submitting || !canGenerate}
          className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">
          {submitting ? 'Starting...' : `Generate ${targetCount} Docs`}
        </button>
      </>
    }>
      <div className="space-y-5">
        {/* Scope selector */}
        <div>
          <label className="block text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">Scope</label>
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="radio" name="scope" checked={scope === 'undocumented'} onChange={() => setScope('undocumented')} className="accent-accent" />
              All undocumented ({undocumented.length} features)
            </label>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="radio" name="scope" checked={scope === 'all'} onChange={() => setScope('all')} className="accent-accent" />
              All features — regenerate existing docs too ({features.length} features)
            </label>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="radio" name="scope" checked={scope === 'group'} onChange={() => setScope('group')} className="accent-accent" />
              By feature group
            </label>
            {scope === 'group' && (
              <div className="ml-6">
                <select
                  value={selectedGroup}
                  onChange={e => setSelectedGroup(e.target.value)}
                  className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none"
                >
                  <option value="">Select a group...</option>
                  {groups.map(g => (
                    <option key={g.name} value={g.name}>
                      {g.name} ({g.member_count ?? 0} features)
                    </option>
                  ))}
                </select>
                {!selectedGroup && (
                  <p className="text-[11px] text-[var(--text-tertiary)] mt-1">Select a group to continue</p>
                )}
                {selectedGroup && groupMembers.length > 0 && (
                  <p className="text-[11px] text-accent mt-1">
                    Will generate docs for {groupMembers.length} features in group {selectedGroup}
                  </p>
                )}
              </div>
            )}
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input
                type="radio"
                name="scope"
                checked={scope === 'selected'}
                onChange={() => setScope('selected')}
                className="accent-accent"
              />
              Selected features ({manualSelected.size})
            </label>
            {scope === 'selected' && (
              <div className="ml-6 mt-2">
                <FeatureSelector
                  features={toFeatureItems(features as unknown as Record<string, unknown>[])}
                  selected={manualSelected}
                  onChange={setManualSelected}
                  showAISuggest={false}
                  maxHeight="240px"
                />
              </div>
            )}
          </div>
        </div>

        {/* Global hint */}
        <div>
          <label className="block text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">Context hint for this batch</label>
          <textarea
            value={globalHint}
            onChange={(e) => setGlobalHint(e.target.value)}
            rows={2}
            placeholder="e.g. All features are computed from the last 30 days of telecom usage data. Dataset covers FPT Telecom subscribers in Vietnam."
            className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none resize-none"
          />
          <p className="text-[11px] text-[var(--text-tertiary)] mt-1">Applied to all features in this batch. Individual feature hints take priority.</p>
        </div>

        {/* Preview table toggle */}
        <div>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="flex items-center gap-1.5 text-[13px] font-medium text-accent hover:underline"
          >
            {showPreview ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {showPreview ? 'Hide' : 'Show'} features to be documented ({targetCount})
          </button>

          {showPreview && (
            <div className="mt-2 max-h-60 overflow-y-auto overscroll-contain border border-[var(--border-subtle)] rounded-lg">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-[var(--text-tertiary)] border-b border-[var(--border-default)] bg-[var(--bg-secondary)] sticky top-0">
                    <th className="text-left py-1.5 px-2 font-medium">Feature</th>
                    <th className="text-left py-1.5 px-2 font-medium">Individual hint</th>
                    <th className="text-center py-1.5 px-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {targetFeatures.map(f => {
                    const hint = getHint(f)
                    const isEditing = editingHint === f.name
                    return (
                      <tr key={f.name} className="border-b border-[var(--border-subtle)]">
                        <td className="py-1.5 px-2 font-mono text-[11px] max-w-[180px] truncate" title={f.name}>{f.name}</td>
                        <td className="py-1.5 px-2">
                          {isEditing ? (
                            <div className="space-y-1">
                              <textarea
                                value={hintDrafts[f.name] ?? hint ?? ''}
                                onChange={(e) => setHintDrafts(prev => ({ ...prev, [f.name]: e.target.value }))}
                                rows={2}
                                className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded px-2 py-1 text-[11px] focus:border-accent outline-none resize-none"
                                placeholder="Add a hint..."
                              />
                              <div className="flex gap-1">
                                <button onClick={() => saveHint(f.name)} className="px-2 py-0.5 text-[10px] bg-accent text-white rounded">Save</button>
                                <button onClick={() => setEditingHint(null)} className="px-2 py-0.5 text-[10px] border border-[var(--border-default)] rounded">Cancel</button>
                              </div>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1">
                              {hint ? (
                                <span className="text-[11px] text-[var(--text-secondary)] truncate max-w-[150px]" title={hint}>{hint}</span>
                              ) : (
                                <span className="text-[11px] text-[var(--text-tertiary)]">none</span>
                              )}
                              <button
                                onClick={() => { setHintDrafts(prev => ({ ...prev, [f.name]: hint ?? '' })); setEditingHint(f.name) }}
                                className="text-[var(--text-tertiary)] hover:text-accent shrink-0 p-0.5"
                                title="Edit hint"
                              >
                                <Pencil size={10} />
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="py-1.5 px-2 text-center">
                          {f.has_doc
                            ? <Badge variant="success">has doc</Badge>
                            : <Badge variant="warning">no doc</Badge>
                          }
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Summary */}
        <p className="text-sm text-[var(--text-secondary)]">
          Will generate docs for <span className="font-semibold">{targetCount}</span> feature{targetCount !== 1 ? 's' : ''}.
          {globalHint.trim() && ` Global hint will be applied to features without individual hints.`}
        </p>
      </div>
    </Modal>
  )
}


function AddSourceModal({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (form: Record<string, string>) => void }) {
  const [form, setForm] = useState({ path: '', name: '', description: '', owner: '', tags: '' })
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  return (
    <Modal open={open} onClose={onClose} title="Add Source" actions={
      <>
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">Cancel</button>
        <button onClick={() => onSubmit(form)} disabled={!form.path} className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">Add</button>
      </>
    }>
      <div className="space-y-3">
        {[
          { k: 'path', label: 'Path', placeholder: '/path/to/data', required: true },
          { k: 'name', label: 'Name', placeholder: 'Optional name' },
          { k: 'description', label: 'Description', placeholder: 'Describe this source' },
          { k: 'owner', label: 'Owner', placeholder: 'Owner name' },
          { k: 'tags', label: 'Tags', placeholder: 'Comma-separated tags' },
        ].map(({ k, label, placeholder, required }) => (
          <div key={k}>
            <label className="block text-xs font-medium mb-1">{label} {required && <span className="text-[var(--danger)]">*</span>}</label>
            <input
              value={form[k as keyof typeof form]}
              onChange={(e) => set(k, e.target.value)}
              placeholder={placeholder}
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none"
            />
          </div>
        ))}
      </div>
    </Modal>
  )
}


function BulkScanModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({ path: '', recursive: true, owner: localStorage.getItem('featcat_user') || '', dry_run: false })
  const [tags, setTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  const addTag = () => {
    const t = tagInput.trim()
    if (t && !tags.includes(t)) setTags([...tags, t])
    setTagInput('')
  }

  const submit = async () => {
    setScanning(true)
    try {
      const res = await api.scanBulk({ path: form.path, recursive: form.recursive, owner: form.owner, tags, dry_run: form.dry_run })
      setResult(res)
      if (!form.dry_run) {
        invalidateCache('/features')
        invalidateCache('/sources')
      }
    } catch { /* ignore */ }
    setScanning(false)
  }

  const reset = () => {
    setResult(null)
    setForm({ path: '', recursive: true, owner: localStorage.getItem('featcat_user') || '', dry_run: false })
    setTags([])
  }

  return (
    <Modal open={open} onClose={() => { reset(); onClose() }} title="Bulk Scan" maxWidth="max-w-lg" actions={
      result ? (
        <button onClick={() => { reset(); onDone() }} className="px-4 py-2 text-sm bg-accent text-white rounded-lg">Done</button>
      ) : (
        <>
          <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">Cancel</button>
          <button onClick={submit} disabled={!form.path || scanning} className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">
            {scanning ? 'Scanning...' : 'Scan'}
          </button>
        </>
      )
    }>
      {result ? (
        <div className="space-y-3">
          <p className="text-sm">
            Found <span className="font-medium">{result.found as number}</span> files.
            {form.dry_run ? ' (dry run)' : (
              <> Registered <span className="font-medium">{result.registered_sources as number}</span> new sources,{' '}
              <span className="font-medium">{result.registered_features as number}</span> new features.
              {(result.skipped as number) > 0 && <> Skipped <span className="font-medium">{result.skipped as number}</span> already registered.</>}</>
            )}
          </p>
          {((result.details || []) as { file: string; status: string; feature_count: number }[]).length > 0 && (
            <div className="max-h-48 overflow-y-auto overscroll-contain">
              <table className="w-full text-[13px]">
                <thead><tr className="text-xs text-[var(--text-tertiary)] border-b border-[var(--border-default)]">
                  <th className="text-left py-1">File</th>
                  <th className="text-left py-1">Status</th>
                  <th className="text-right py-1">Features</th>
                </tr></thead>
                <tbody>
                  {((result.details || []) as { file: string; status: string; feature_count: number }[]).map((d, i) => (
                    <tr key={i} className="border-b border-[var(--border-subtle)]">
                      <td className="py-1 truncate max-w-[200px]">{d.file.split('/').pop()}</td>
                      <td className="py-1"><Badge variant={d.status === 'registered' || d.status === 'would_register' ? 'success' : d.status === 'skipped' ? 'warning' : 'error'}>{d.status}</Badge></td>
                      <td className="py-1 text-right font-mono">{d.feature_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium mb-1">Directory Path <span className="text-[var(--danger)]">*</span></label>
            <input value={form.path} onChange={(e) => setForm((f) => ({ ...f, path: e.target.value }))} placeholder="/path/to/data"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none" />
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="checkbox" checked={form.recursive} onChange={(e) => setForm((f) => ({ ...f, recursive: e.target.checked }))} className="accent-accent" />
              Recursive
            </label>
            <label className="flex items-center gap-2 text-[13px] cursor-pointer">
              <input type="checkbox" checked={form.dry_run} onChange={(e) => setForm((f) => ({ ...f, dry_run: e.target.checked }))} className="accent-accent" />
              Dry run
            </label>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Owner</label>
            <input value={form.owner} onChange={(e) => setForm((f) => ({ ...f, owner: e.target.value }))} placeholder="Owner name"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none" />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Tags</label>
            <div className="flex gap-1 flex-wrap mb-1">
              {tags.map((t) => (
                <span key={t} className="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--bg-tertiary)] rounded text-xs font-mono">
                  {t} <button onClick={() => setTags(tags.filter((x) => x !== t))} className="hover:text-[var(--danger)]"><X size={10} /></button>
                </span>
              ))}
            </div>
            <input value={tagInput} onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addTag() } }}
              placeholder="Type and press Enter"
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-accent outline-none" />
          </div>
        </div>
      )}
    </Modal>
  )
}


function MiniBarChart({ data }: { data: { date: string; count: number }[] }) {
  if (!data || data.length === 0) return null
  const max = Math.max(...data.map((d) => d.count), 1)
  const w = data.length * 20
  return (
    <svg viewBox={`0 0 ${w} 40`} className="w-full max-w-[200px] h-8 mt-2">
      {data.map((d, i) => (
        <rect key={i} x={i * 20 + 2} y={40 - (d.count / max) * 36} width={16} height={Math.max((d.count / max) * 36, 1)}
          className="fill-accent/60" rx={2} />
      ))}
    </svg>
  )
}


function HealthBar({ value, max, label, detail }: { value: number; max: number; label: string; detail?: string }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="grid grid-cols-[112px_1fr_auto] gap-3 items-center">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
        <div className="h-full bg-[var(--accent)] transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="flex items-center gap-2 whitespace-nowrap">
        <span className="text-xs font-mono text-[var(--text-secondary)] tabular-nums">{value}/{max}</span>
        {detail && <span className="text-xs text-[var(--text-tertiary)]">{detail}</span>}
      </div>
    </div>
  )
}


function HealthBreakdown({ feature }: { feature: FeatureRow }) {
  const score = feature.health_score ?? 0
  const grade = feature.health_grade ?? '-'
  const bd = feature.health_breakdown || { documentation: 0, drift: 0, usage: 0 }
  const cls = GRADE_COLORS[grade] || ''

  const tips: string[] = []
  if (bd.documentation < 25) tips.push('Generate documentation for this feature (+25pts)')
  if (bd.documentation < 40 && bd.documentation >= 25) tips.push('Add a generation hint to improve doc score (+15pts)')
  if (bd.drift === 0) tips.push('Feature has critical drift — investigate data quality')
  if (bd.usage === 0) tips.push('Feature not queried recently (+10pts if used)')

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl font-bold">{score}</span>
        <span className="text-[var(--text-tertiary)] text-sm">/ 100</span>
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${cls}`}>{grade}</span>
      </div>
      <div className="space-y-2">
        <HealthBar value={bd.documentation} max={40} label="Documentation" />
        <HealthBar value={bd.drift} max={40} label="Drift" detail={bd.drift === 40 ? 'healthy' : bd.drift === 0 ? 'critical' : bd.drift === 20 ? 'warning' : 'unknown'} />
        <HealthBar value={bd.usage} max={20} label="Usage" detail={bd.usage === 0 ? 'no recent usage' : undefined} />
      </div>
      {tips.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[var(--border-subtle)] space-y-1">
          {tips.map((tip, i) => (
            <p key={i} className="text-xs text-[var(--text-tertiary)]">{'\u{1F4A1}'} {tip}</p>
          ))}
        </div>
      )}
    </div>
  )
}


const TYPE_DOT_COLORS: Record<string, string> = {
  doc: 'bg-teal-500',
  hints: 'bg-purple-500',
  tags: 'bg-slate-400',
  definition: 'bg-amber-500',
  metadata: 'bg-gray-400',
}


function VersionTimeline({ versions, loading }: { versions: Record<string, unknown>[]; loading: boolean }) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (loading) return <Skeleton className="h-32" />

  if (versions.length === 0) {
    return (
      <p className="text-sm text-[var(--text-tertiary)] py-8 text-center">
        No changes recorded yet. History is tracked from this point forward.
      </p>
    )
  }

  const toggle = (v: number) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(v)) next.delete(v)
      else next.add(v)
      return next
    })
  }

  return (
    <div className="space-y-0">
      {versions.map((v, i) => {
        const version = v.version as number
        const dotColor = TYPE_DOT_COLORS[v.change_type as string] || 'bg-gray-400'
        const isExpanded = expanded.has(version)
        const prev = v.previous_value as Record<string, unknown> | null
        const next = v.new_value as Record<string, unknown> | null

        return (
          <div key={i} className="flex gap-3 relative">
            {/* Timeline line */}
            {i < versions.length - 1 && (
              <div className="absolute left-[7px] top-[18px] bottom-0 w-px bg-[var(--border-subtle)]" />
            )}
            {/* Dot */}
            <div className={`w-[15px] h-[15px] rounded-full ${dotColor} shrink-0 mt-0.5 border-2 border-[var(--bg-primary)]`} />
            {/* Content */}
            <div className="flex-1 pb-4">
              <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                <span className="font-semibold text-[var(--text-primary)]">v{version}</span>
                <span>{v.created_at ? timeAgo(v.created_at as string) : ''}</span>
                <span>{v.changed_by as string}</span>
              </div>
              <p className="text-sm text-[var(--text-secondary)] mt-0.5">{v.change_summary as string}</p>
              {prev && next && (
                <button onClick={() => toggle(version)} className="text-[11px] text-accent hover:underline mt-1">
                  {isExpanded ? 'Hide diff' : 'Show diff'}
                </button>
              )}
              {isExpanded && prev && next && (
                <div className="mt-2 bg-[var(--bg-secondary)] rounded-lg p-2.5 text-xs font-mono space-y-1">
                  {Object.keys(next).map(key => (
                    <div key={key}>
                      <span className="text-[var(--text-tertiary)]">{key}:</span>
                      <div className="text-[var(--danger)]">- {String(prev[key] ?? '(empty)')}</div>
                      <div className="text-[var(--success)]">+ {String(next[key] ?? '(empty)')}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}


function HighlightedText({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length) return <span>{text}</span>
  const escaped = terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')
  const parts = text.split(regex)
  return (
    <span>
      {parts.map((part, i) =>
        terms.some(t => t.toLowerCase() === part.toLowerCase())
          ? <mark key={i} className="bg-[var(--accent-subtle-bg)] text-[var(--accent)] rounded px-0.5">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </span>
  )
}
