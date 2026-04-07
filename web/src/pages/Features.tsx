import { useEffect, useState, useCallback } from 'react'
import { Plus, X, RefreshCw, Check } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { DataTable } from '../components/DataTable'
import { Badge } from '../components/Badge'
import { Tag } from '../components/Tag'
import { Modal } from '../components/Modal'
import { SearchInput } from '../components/SearchInput'
import { Skeleton } from '../components/Skeleton'

export function Features() {
  const [features, setFeatures] = useState<any[]>([])
  const [sources, setSources] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [filtered, setFiltered] = useState<any[]>([])
  const [sourceFilter, setSourceFilter] = useState('')
  const [selected, setSelected] = useState<any>(null)
  const [doc, setDoc] = useState<any>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [generating, setGenerating] = useState(false)

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

  const selectFeature = async (f: any) => {
    setSelected(f)
    setDoc(null)
    try {
      const d = await api.docs.get(f.name)
      setDoc(d)
    } catch { /* no doc */ }
  }

  const generateDoc = async () => {
    if (!selected) return
    setGenerating(true)
    try {
      await api.docs.generate({ feature_name: selected.name })
      invalidateCache('/docs')
      const d = await api.docs.get(selected.name)
      setDoc(d)
    } catch { /* ignore */ }
    setGenerating(false)
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
      setModalOpen(false)
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
        <button onClick={() => setModalOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium hover:bg-accent-emphasis transition-colors">
          <Plus size={16} /> Add Source
        </button>
      </div>

      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl overflow-hidden">
        {loading ? <div className="p-5"><Skeleton className="h-48" /></div> : (
          <DataTable columns={columns} data={filtered} onRowClick={selectFeature} />
        )}
      </div>

      {/* Detail Panel */}
      {selected && (
        <div className="mt-4 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 animate-fade-in">
          <div className="flex justify-between items-start mb-4">
            <div>
              <h3 className="font-semibold text-accent">{selected.name}</h3>
              <p className="text-xs text-[var(--text-tertiary)]">{selected.dtype} &middot; {selected.column_name}</p>
            </div>
            <button onClick={() => setSelected(null)} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"><X size={16} /></button>
          </div>

          {selected.stats && Object.keys(selected.stats).length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
              {['mean', 'std', 'min', 'max', 'null_ratio'].map((k) => (
                selected.stats[k] != null && (
                  <div key={k} className="text-center">
                    <div className="text-xs text-[var(--text-tertiary)] uppercase">{k}</div>
                    <div className="font-mono text-sm">{typeof selected.stats[k] === 'number' ? selected.stats[k].toFixed(4) : selected.stats[k]}</div>
                  </div>
                )
              ))}
            </div>
          )}

          {doc ? (
            <div className="text-sm space-y-2">
              <p>{doc.short_description}</p>
              {doc.long_description && <p className="text-[var(--text-secondary)]">{doc.long_description}</p>}
              {doc.expected_range && <p className="text-xs text-[var(--text-tertiary)]">Range: {doc.expected_range}</p>}
            </div>
          ) : (
            <button onClick={generateDoc} disabled={generating} className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-accent text-white rounded-lg disabled:opacity-50">
              <RefreshCw size={12} className={generating ? 'animate-spin' : ''} />
              {generating ? 'Generating...' : 'Generate Doc'}
            </button>
          )}
        </div>
      )}

      {/* Add Source Modal */}
      <AddSourceModal open={modalOpen} onClose={() => setModalOpen(false)} onSubmit={handleAddSource} />
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
