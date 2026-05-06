import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, UserPlus, X, Download } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { ExportModal } from '../components/ExportModal'
import { FeatureSelector, toFeatureItems } from '../components/FeatureSelector'
import { Modal } from '../components/Modal'
import { Skeleton } from '../components/Skeleton'

export function Groups() {
  const { t } = useTranslation('groups')
  const [groups, setGroups] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<any>(null)
  const [detail, setDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  const load = () => {
    setLoading(true)
    invalidateCache('/groups')
    api.groups.list()
      .then((g) => setGroups(Array.isArray(g) ? g : []))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const selectGroup = (g: any) => {
    setSelected(g)
    setDetailLoading(true)
    invalidateCache('/groups')
    api.groups.get(g.name)
      .then(setDetail)
      .finally(() => setDetailLoading(false))
  }

  const deleteGroup = async (name: string) => {
    if (!window.confirm(t('confirm_delete', { name }))) return
    await api.groups.delete(name)
    invalidateCache('/groups')
    setSelected(null)
    setDetail(null)
    load()
  }

  const removeMember = async (spec: string) => {
    if (!selected) return
    await api.groups.removeMember(selected.name, spec)
    invalidateCache('/groups')
    selectGroup(selected)
  }

  const memberColumns = [
    { key: 'name', label: t('member_table.feature'), render: (r: any) => <span className="font-medium text-accent">{r.name}</span> },
    { key: 'dtype', label: t('member_table.dtype'), render: (r: any) => <span className="font-mono text-xs">{r.dtype}</span> },
    { key: 'has_doc', label: t('member_table.docs'), sortable: false, render: (r: any) => r.has_doc ? <Badge variant="success">{t('member_table.has_docs_yes')}</Badge> : <span className="text-[var(--text-tertiary)]">-</span> },
    { key: '_remove', label: '', sortable: false, render: (r: any) => (
      <button onClick={(e) => { e.stopPropagation(); removeMember(r.name) }} className="text-[var(--text-tertiary)] hover:text-[var(--danger)] transition-colors p-1">
        <Trash2 size={13} />
      </button>
    )},
  ]

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
        <button onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded-lg text-[13px] font-medium hover:bg-accent-emphasis transition-colors">
          <Plus size={16} /> {t('actions.new_group')}
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-4" style={{ minHeight: '500px' }}>
        {/* Left: group list */}
        <div className="w-full md:w-1/3 bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-3 flex flex-col">
          <div className="space-y-2 flex-1 overflow-y-auto">
            {loading ? (
              <Skeleton className="h-32" />
            ) : groups.length === 0 ? (
              <p className="text-[var(--text-tertiary)] text-sm py-4 text-center">{t('list.empty')}</p>
            ) : (
              groups.map((g) => (
                <div
                  key={g.name}
                  onClick={() => selectGroup(g)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    selected?.name === g.name
                      ? 'border-accent bg-accent-muted'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] hover:border-[var(--border-default)]'
                  }`}
                >
                  <div className="font-medium text-sm mb-1">{g.name}</div>
                  <div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                    {g.project && <Badge variant="info">{g.project}</Badge>}
                    <span>{t('list.members_count', { count: g.member_count ?? 0 })}</span>
                    {g.owner && <span className="ml-auto">{g.owner}</span>}
                  </div>
                  {g.description && <p className="text-xs text-[var(--text-secondary)] mt-1 line-clamp-2">{g.description}</p>}
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right: detail */}
        <div className="flex-1 flex flex-col">
          {!selected ? (
            <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-8 text-center text-[var(--text-tertiary)] text-sm flex-1 flex items-center justify-center">
              {t('detail.select_hint')}
            </div>
          ) : detailLoading ? (
            <Skeleton className="h-48 flex-1" />
          ) : detail ? (
            <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 flex-1 flex flex-col">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-lg font-semibold">{detail.name}</h2>
                  <div className="flex items-center gap-2 mt-1 text-xs text-[var(--text-secondary)]">
                    {detail.project && <Badge variant="info">{detail.project}</Badge>}
                    {detail.owner && <span>{t('detail.owner_label')}: {detail.owner}</span>}
                  </div>
                  {detail.description && <p className="text-sm text-[var(--text-secondary)] mt-2">{detail.description}</p>}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setAddOpen(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]">
                    <UserPlus size={14} /> {t('actions.add_features')}
                  </button>
                  {detail.members?.length > 0 && (
                    <button onClick={() => setExportOpen(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]">
                      <Download size={14} /> {t('actions.export')}
                    </button>
                  )}
                  <button onClick={() => deleteGroup(detail.name)} className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--danger-subtle-bg)] text-[var(--danger)] rounded-lg hover:bg-[var(--danger-subtle-bg)]">
                    <Trash2 size={14} /> {t('actions.delete')}
                  </button>
                </div>
              </div>

              <h3 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide mb-2">
                {t('detail.members_heading', { count: detail.members?.length || 0 })}
              </h3>
              {detail.members?.length > 0 ? (
                <DataTable columns={memberColumns} data={detail.members} pageSize={20} />
              ) : (
                <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">{t('detail.members_empty')}</p>
              )}
            </div>
          ) : null}
        </div>
      </div>

      <CreateGroupModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); load() }} />
      {selected && <AddFeaturesModal open={addOpen} onClose={() => setAddOpen(false)} groupName={selected.name} onAdded={() => { setAddOpen(false); load(); selectGroup(selected) }} />}
      {detail && (
        <ExportModal
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          title={t('export_title', { name: detail.name, count: detail.members?.length || 0 })}
          featureSpecs={(detail.members || []).map((m: Record<string, unknown>) => m.name as string)}
          groupName={detail.name}
        />
      )}
    </div>
  )
}


function CreateGroupModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const { t } = useTranslation('groups')
  const [form, setForm] = useState({ name: '', description: '', project: '', owner: '' })
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const submit = async () => {
    await api.groups.create(form)
    invalidateCache('/groups')
    setForm({ name: '', description: '', project: '', owner: '' })
    onCreated()
  }

  return (
    <Modal open={open} onClose={onClose} title={t('create_modal.title')} actions={
      <>
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
        <button onClick={submit} disabled={!form.name} className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">{t('actions.create')}</button>
      </>
    }>
      <div className="space-y-3">
        {[
          { k: 'name', label: t('create_modal.fields.name'), placeholder: t('create_modal.fields.name_placeholder'), required: true },
          { k: 'description', label: t('create_modal.fields.description'), placeholder: t('create_modal.fields.description_placeholder') },
          { k: 'project', label: t('create_modal.fields.project'), placeholder: t('create_modal.fields.project_placeholder') },
          { k: 'owner', label: t('create_modal.fields.owner'), placeholder: t('create_modal.fields.owner_placeholder') },
        ].map(({ k, label, placeholder, required }) => (
          <div key={k}>
            <label className="block text-xs font-medium mb-1">{label} {required && <span className="text-[var(--danger)]">*</span>}</label>
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


function AddFeaturesModal({ open, onClose, groupName, onAdded }: { open: boolean; onClose: () => void; groupName: string; onAdded: () => void }) {
  const { t } = useTranslation('groups')
  const [features, setFeatures] = useState<ReturnType<typeof toFeatureItems>>([])
  const [selectedSpecs, setSelectedSpecs] = useState<Set<string>>(new Set())
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    if (open) {
      api.features.list().then((f) => {
        setFeatures(toFeatureItems(Array.isArray(f) ? f : []))
      })
      setSelectedSpecs(new Set())
    }
  }, [open])

  const submit = async () => {
    if (selectedSpecs.size === 0) return
    setAdding(true)
    await api.groups.addMembers(groupName, Array.from(selectedSpecs))
    invalidateCache('/groups')
    setSelectedSpecs(new Set())
    setAdding(false)
    onAdded()
  }

  return (
    <Modal open={open} onClose={onClose} title={t('add_modal.title', { group: groupName })} maxWidth="max-w-xl" actions={
      <>
        <button onClick={onClose} className="px-4 py-2 text-sm border border-[var(--border-default)] rounded-lg">{t('actions.cancel', { ns: 'common' })}</button>
        <button onClick={submit} disabled={selectedSpecs.size === 0 || adding} className="px-4 py-2 text-sm bg-accent text-white rounded-lg disabled:opacity-50">
          {t('actions.add')} {selectedSpecs.size > 0 ? `(${selectedSpecs.size})` : ''}
        </button>
      </>
    }>
      <FeatureSelector
        features={features}
        selected={selectedSpecs}
        onChange={setSelectedSpecs}
        groupName={groupName}
        showAISuggest
      />
    </Modal>
  )
}
