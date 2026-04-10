import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Plus, RefreshCw, Check, AlertTriangle, Shield, FileText } from 'lucide-react'
import { api, invalidateCache, timeAgo } from '../api'
import { DataTable } from '../components/DataTable'
import { Badge } from '../components/Badge'
import { Tag } from '../components/Tag'
import { Modal } from '../components/Modal'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

export function Features() {
  const { name: paramName } = useParams()
  const navigate = useNavigate()
  const [features, setFeatures] = useState<any[]>([])
  const [sources, setSources] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filtered, setFiltered] = useState<any[]>([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [selected, setSelected] = useState<any>(null)
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [genProgress, setGenProgress] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    Promise.all([api.features.list(), api.sources.list().catch(() => [])])
      .then(([f, s]) => {
        const list = Array.isArray(f) ? f : []
        setFeatures(list)
        setFiltered(list)
        setSources(Array.isArray(s) ? s : [])
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  // Auto-open modal from URL param
  useEffect(() => {
    if (paramName && features.length > 0) {
      const decoded = decodeURIComponent(paramName)
      const feat = features.find((f) => f.name === decoded)
      if (feat) setSelected(feat)
    }
  }, [paramName, features])

  const onSearch = useCallback((q: string) => {
    const query = q.toLowerCase()
    setFiltered(
      features.filter((f) => {
        if (sourceFilter && !f.name?.startsWith(sourceFilter + '.')) return false
        if (!query) return true
        return (
          f.name?.toLowerCase().includes(query) ||
          f.column_name?.toLowerCase().includes(query) ||
          (f.tags || []).some((t: string) => t.toLowerCase().includes(query))
        )
      })
    )
  }, [features, sourceFilter])

  useEffect(() => { onSearch('') }, [sourceFilter, onSearch])

  const selectFeature = (f: any) => {
    setSelected(f)
    navigate(`/features/${encodeURIComponent(f.name)}`, { replace: true })
  }

  const closeModal = () => {
    setSelected(null)
    navigate('/features', { replace: true })
  }

  const undocCount = features.filter((f) => !f.has_doc).length

  const generateAllDocs = async () => {
    if (genProgress) return
    if (!window.confirm(`Generate docs for ${undocCount} undocumented features? This may take 1-2 minutes.`)) return
    setGenProgress('Generating...')
    try {
      await api.docs.generate({})
      invalidateCache('/features')
      invalidateCache('/docs')
      load()
    } catch { /* ignore */ } finally {
      setGenProgress(null)
    }
  }

  const handleAddSource = async (form: Record<string, string>) => {
    try {
      const payload: any = { path: form.path }
      if (form.name) payload.name = form.name
      if (form.description) payload.description = form.description
      if (form.owner) payload.owner = form.owner
      if (form.tags) payload.tags = form.tags.split(',').map((t: string) => t.trim())
      const src = await api.sources.add(payload)
      await api.sources.scan(src.name)
      invalidateCache('/features')
      invalidateCache('/sources')
      setAddModalOpen(false)
      load()
    } catch { /* ignore */ }
  }

  const columns = [
    { key: 'name', label: 'Name', render: (r: any) => <span className="font-medium text-accent">{r.name}</span> },
    { key: 'source', label: 'Source', sortable: false, render: (r: any) => <span className="text-[var(--text-secondary)]">{r.name?.split('.')[0] || ''}</span> },
    { key: 'dtype', label: 'Dtype', render: (r: any) => <span className="font-mono text-xs">{r.dtype}</span> },
    { key: 'tags', label: 'Tags', sortable: false, render: (r: any) => (
      <div className="flex gap-1 flex-wrap">{(r.tags || []).map((t: string, i: number) => <Tag key={i}>{t}</Tag>)}</div>
    )},
    { key: 'has_doc', label: 'Docs', render: (r: any) => r.has_doc ? <Check size={14} className="text-green-500" /> : <span className="text-[var(--text-tertiary)]">-</span> },
    { key: 'owner', label: 'Owner' },
  ]

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-semibold">Features</h1>
        <span className="text-xs text-[var(--text-tertiary)]">{filtered.length} features</span>
      </div>

      <div className="flex gap-3 items-center mb-4 flex-wrap">
        <SearchInput placeholder="Search features..." onSearch={onSearch} className="max-w-xs" />
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] max-w-[200px]"
        >
          <option value="">All Sources</option>
          {sources.map((s: any) => <option key={s.name} value={s.name}>{s.name}</option>)}
        </select>
        {undocCount > 0 && (
          <button
            onClick={generateAllDocs}
            disabled={!!genProgress}
            className="flex items-center gap-1.5 px-4 py-2 border border-[var(--border-default)] rounded-lg text-[13px] font-medium hover:bg-[var(--bg-secondary)] disabled:opacity-50 transition-colors"
          >
            {genProgress ? <><RefreshCw size={14} className="animate-spin" /> {genProgress}</> : <><FileText size={14} /> Generate Docs ({undocCount} remaining)</>}
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
        <FeatureDetailModal feature={selected} onClose={closeModal} />
      )}

      <AddSourceModal open={addModalOpen} onClose={() => setAddModalOpen(false)} onSubmit={handleAddSource} />
    </div>
  )
}


function FeatureDetailModal({ feature, onClose }: { feature: any; onClose: () => void }) {
  const [doc, setDoc] = useState<any>(null)
  const [docLoading, setDocLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [monitoring, setMonitoring] = useState<any>(null)
  const [monLoading, setMonLoading] = useState(true)

  useEffect(() => {
    setDocLoading(true)
    setMonLoading(true)
    api.docs.get(feature.name).then(setDoc).catch(() => setDoc(null)).finally(() => setDocLoading(false))
    api.monitor.check({ feature_name: feature.name }).then(setMonitoring).catch(() => setMonitoring(null)).finally(() => setMonLoading(false))
  }, [feature.name])

  const generateDoc = async () => {
    setGenerating(true)
    try {
      await api.docs.generate({ feature_name: feature.name })
      invalidateCache('/docs')
      const d = await api.docs.get(feature.name)
      setDoc(d)
    } catch { /* ignore */ }
    setGenerating(false)
  }

  const computeBaseline = async () => {
    try {
      await api.monitor.baseline()
      const m = await api.monitor.check({ feature_name: feature.name })
      setMonitoring(m)
    } catch { /* ignore */ }
  }

  const stats = feature.stats || {}
  const source = feature.name?.split('.')[0] || ''
  const statKeys = ['mean', 'std', 'min', 'max', 'null_ratio', 'unique_count']
  const hasStats = statKeys.some((k) => stats[k] != null)

  return (
    <Modal open={true} onClose={onClose} title={feature.name} maxWidth="max-w-2xl">
      {/* Header badges */}
      <div className="flex items-center gap-2 flex-wrap mb-5">
        <Badge variant="info">{source}</Badge>
        {(feature.tags || []).map((t: string, i: number) => <Tag key={i}>{t}</Tag>)}
      </div>

      {/* Metadata */}
      <Section title="Metadata">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
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
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {statKeys.map((k) =>
              stats[k] != null && (
                <div key={k} className="bg-[var(--bg-secondary)] rounded-lg p-2.5 text-center">
                  <div className="text-[10px] text-[var(--text-tertiary)] uppercase tracking-wide mb-0.5">{k.replace('_', ' ')}</div>
                  <div className="font-mono text-sm">{typeof stats[k] === 'number' ? stats[k].toFixed(4) : stats[k]}</div>
                </div>
              )
            )}
          </div>
        </Section>
      )}

      {/* Documentation */}
      <Section title="Documentation">
        {docLoading ? (
          <Skeleton className="h-12" />
        ) : doc ? (
          <div className="space-y-2 text-sm">
            <p>{doc.short_description}</p>
            {doc.long_description && <p className="text-[var(--text-secondary)]">{doc.long_description}</p>}
            {doc.expected_range && (
              <p className="text-xs text-[var(--text-tertiary)]">
                <span className="font-medium">Expected range:</span> {doc.expected_range}
              </p>
            )}
            {doc.potential_issues && (
              <p className="text-xs text-[var(--text-tertiary)]">
                <span className="font-medium">Potential issues:</span> {doc.potential_issues}
              </p>
            )}
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

      {/* Monitoring */}
      <Section title="Monitoring" last>
        {monLoading ? (
          <Skeleton className="h-10" />
        ) : monitoring?.results?.length > 0 ? (
          <div className="flex items-center gap-4 flex-wrap">
            {(() => {
              const r = monitoring.results[0]
              const status = r.status || 'unknown'
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
            <button onClick={computeBaseline} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent text-white rounded-lg">
              Compute Baseline
            </button>
          </div>
        )}
      </Section>
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
            <label className="block text-xs font-medium mb-1">{label} {required && <span className="text-red-500">*</span>}</label>
            <input
              value={(form as any)[k]}
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
