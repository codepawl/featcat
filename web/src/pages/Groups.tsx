import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, UserPlus, X, Download, Activity, HeartPulse, FileText, RefreshCw, Sparkles, AlertTriangle, Clock } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { api, invalidateCache } from '../api'
import { Badge } from '../components/Badge'
import { DataTable } from '../components/DataTable'
import { ExportModal } from '../components/ExportModal'
import { FeatureSelector, toFeatureItems } from '../components/FeatureSelector'
import { Modal } from '../components/Modal'
import { Skeleton } from '../components/Skeleton'

type GroupTab = 'members' | 'health' | 'monitoring' | 'docs'

const GRADE_COLORS: Record<string, string> = {
  A: 'bg-green-500',
  B: 'bg-emerald-400',
  C: 'bg-amber-400',
  D: 'bg-red-400',
}

const SEVERITY_COLORS: Record<string, string> = {
  healthy: 'bg-green-500',
  warning: 'bg-amber-500',
  critical: 'bg-red-500',
  unknown: 'bg-[var(--border-default)]',
}

// Hex equivalents for Recharts (which can't read Tailwind classes).
// Matches the SEVERITY_COLORS palette in components/charts/PsiTimeline.tsx.
const SEVERITY_HEX: Record<string, string> = {
  healthy: '#1D9E75',
  warning: '#F59E0B',
  critical: '#EF4444',
  unknown: '#94A3B8',
}

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
  const [tab, setTab] = useState<GroupTab>('members')

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
    setTab('members')
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
    { key: 'name', label: t('member_table.feature'), render: (r: any) => <span className="font-medium text-brand">{r.name}</span> },
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
        <button onClick={() => setCreateOpen(true)} className="flex items-center gap-1.5 px-4 py-2 bg-brand text-white rounded-lg text-[13px] font-medium hover:bg-brand-emphasis transition-colors">
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
                      ? 'border-brand bg-brand-muted'
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

              <div className="flex gap-1 mb-3 border-b border-[var(--border-subtle)]">
                {([
                  { id: 'members', labelKey: 'tabs.members', icon: UserPlus, withCount: true },
                  { id: 'health', labelKey: 'tabs.health', icon: HeartPulse, withCount: false },
                  { id: 'monitoring', labelKey: 'tabs.monitoring', icon: Activity, withCount: false },
                  { id: 'docs', labelKey: 'tabs.docs', icon: FileText, withCount: false },
                ] as { id: GroupTab; labelKey: string; icon: typeof UserPlus; withCount: boolean }[]).map((entry) => {
                  const Icon = entry.icon
                  const label = entry.withCount
                    ? `${t(entry.labelKey, { defaultValue: 'Members' })} (${detail.members?.length || 0})`
                    : t(entry.labelKey, { defaultValue: entry.id })
                  return (
                    <button
                      key={entry.id}
                      onClick={() => setTab(entry.id)}
                      className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-medium border-b-2 transition-colors ${
                        tab === entry.id
                          ? 'border-brand text-brand'
                          : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
                      }`}
                    >
                      <Icon size={13} />
                      {label}
                    </button>
                  )
                })}
              </div>

              {tab === 'members' && (
                detail.members?.length > 0 ? (
                  <DataTable columns={memberColumns} data={detail.members} pageSize={20} />
                ) : (
                  <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">{t('detail.members_empty')}</p>
                )
              )}

              {tab === 'health' && <GroupHealthTab groupName={detail.name} />}
              {tab === 'monitoring' && <GroupMonitoringTab groupName={detail.name} />}
              {tab === 'docs' && <GroupDocsTab groupName={detail.name} memberCount={detail.members?.length || 0} />}
            </div>
          ) : null}
        </div>
      </div>

      <CreateGroupModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); load() }} />
      {selected && (
        <AddFeaturesModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          groupName={selected.name}
          description={detail?.description ?? selected.description ?? ''}
          existingMemberIds={(detail?.members ?? []).map((m: { id: string }) => m.id).filter(Boolean)}
          onAdded={() => { setAddOpen(false); load(); selectGroup(selected) }}
        />
      )}
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
        <button onClick={submit} disabled={!form.name} className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50">{t('actions.create')}</button>
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
              className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px] focus:border-brand outline-none"
            />
          </div>
        ))}
      </div>
    </Modal>
  )
}


function AddFeaturesModal({
  open,
  onClose,
  groupName,
  description,
  existingMemberIds,
  onAdded,
}: {
  open: boolean
  onClose: () => void
  groupName: string
  description: string
  existingMemberIds: string[]
  onAdded: () => void
}) {
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
        <button onClick={submit} disabled={selectedSpecs.size === 0 || adding} className="px-4 py-2 text-sm bg-brand text-white rounded-lg disabled:opacity-50">
          {t('actions.add')} {selectedSpecs.size > 0 ? `(${selectedSpecs.size})` : ''}
        </button>
      </>
    }>
      <FeatureSelector
        features={features}
        selected={selectedSpecs}
        onChange={setSelectedSpecs}
        groupName={groupName}
        useCase={description || groupName}
        excludeIds={existingMemberIds}
        showAISuggest
      />
    </Modal>
  )
}


function GroupHealthTab({ groupName }: { groupName: string }) {
  const { t } = useTranslation('groups')
  const [data, setData] = useState<Awaited<ReturnType<typeof api.groups.health>> | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    invalidateCache(`/groups/${encodeURIComponent(groupName)}/health`)
    api.groups.health(groupName).then(setData).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [groupName]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <Skeleton className="h-32" />
  if (!data || data.member_count === 0) {
    return <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">{t('health.empty', { defaultValue: 'No members to score yet' })}</p>
  }

  const total = Object.values(data.grade_distribution).reduce((a, b) => a + b, 0) || 1
  const documentedCount = data.members.filter(m => m.has_doc).length
  const docPct = data.member_count > 0 ? Math.round((documentedCount / data.member_count) * 100) : 0
  const criticalMembers = data.members.filter(m => m.drift_status === 'critical')

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="border border-[var(--border-subtle)] rounded-xl p-3">
          <div className="text-[11px] uppercase text-[var(--text-tertiary)] tracking-wide">{t('health.average', { defaultValue: 'Average score' })}</div>
          <div className="text-2xl font-semibold mt-1">{data.average_score}<span className="text-sm text-[var(--text-tertiary)]">/100</span></div>
        </div>
        <div className="border border-[var(--border-subtle)] rounded-xl p-3">
          <div className="text-[11px] uppercase text-[var(--text-tertiary)] tracking-wide">{t('health.doc_coverage', { defaultValue: 'Doc coverage' })}</div>
          <div className="text-2xl font-semibold mt-1">{docPct}<span className="text-sm text-[var(--text-tertiary)]">%</span></div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
            {t('health.doc_coverage_hint', { documented: documentedCount, total: data.member_count, defaultValue: '{{documented}} of {{total}} documented' })}
          </div>
        </div>
        <div className="border border-[var(--border-subtle)] rounded-xl p-3">
          <div className="text-[11px] uppercase text-[var(--text-tertiary)] tracking-wide mb-2">{t('health.distribution', { defaultValue: 'Grade distribution' })}</div>
          <div className="flex h-2.5 rounded overflow-hidden">
            {(['A','B','C','D'] as const).map(g => {
              const n = data.grade_distribution[g] || 0
              const pct = (n / total) * 100
              return pct > 0 ? <div key={g} className={GRADE_COLORS[g]} style={{ width: `${pct}%` }} title={`${g}: ${n}`} /> : null
            })}
          </div>
          <div className="flex gap-3 mt-2 text-[11px] text-[var(--text-secondary)] flex-wrap">
            {(['A','B','C','D'] as const).map(g => (
              <span key={g} className="flex items-center gap-1">
                <span className={`size-2 rounded-sm ${GRADE_COLORS[g]}`} /> {g}: {data.grade_distribution[g] || 0}
              </span>
            ))}
          </div>
        </div>
      </div>

      {criticalMembers.length > 0 && (
        <div className="border border-[var(--danger-subtle-bg)] bg-[var(--danger-subtle-bg)] rounded-xl p-3">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle size={14} className="text-[var(--danger)]" />
            <h4 className="text-xs font-semibold uppercase text-[var(--danger)] tracking-wide">
              {t('health.currently_critical', { count: criticalMembers.length, defaultValue: 'Currently critical ({{count}})' })}
            </h4>
          </div>
          <div className="divide-y divide-[var(--border-subtle)]">
            {criticalMembers.map(m => (
              <a
                key={m.spec}
                href={`/monitoring?feature=${encodeURIComponent(m.spec)}`}
                className="flex items-center justify-between py-1.5 text-[13px] hover:underline"
              >
                <span className="font-mono text-[var(--danger)] truncate">{m.spec}</span>
                <span className="flex items-center gap-2 shrink-0 text-[11px]">
                  <Badge variant="critical">{m.grade}</Badge>
                  <span className="font-mono">{m.score}/100</span>
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide">{t('health.lowest', { defaultValue: 'Lowest scoring members' })}</h4>
          <button onClick={load} className="flex items-center gap-1 text-[11px] text-[var(--text-tertiary)] hover:text-brand">
            <RefreshCw size={11} /> {t('health.refresh', { defaultValue: 'Refresh' })}
          </button>
        </div>
        <div className="border border-[var(--border-subtle)] rounded-xl divide-y divide-[var(--border-subtle)]">
          {data.lowest_scored.length === 0 ? (
            <p className="text-sm text-[var(--text-tertiary)] py-3 text-center">{t('health.all_healthy', { defaultValue: 'All members healthy' })}</p>
          ) : data.lowest_scored.map(m => (
            <div key={m.spec} className="flex items-center justify-between px-3 py-2 text-[13px]">
              <span className="font-mono text-brand truncate">{m.spec}</span>
              <span className="flex items-center gap-2 shrink-0">
                <Badge variant={m.grade === 'A' ? 'success' : m.grade === 'B' ? 'info' : m.grade === 'C' ? 'warning' : 'critical'}>{m.grade}</Badge>
                <span className="font-mono text-xs">{m.score}/100</span>
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}


function SeverityTooltip({ active, payload }: { active?: boolean; payload?: { payload: { severity: string; count: number } }[] }) {
  const { t } = useTranslation('groups')
  if (!active || !payload?.[0]) return null
  const { severity, count } = payload[0].payload
  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[12px] shadow-lg">
      <p className="capitalize font-medium">{severity}</p>
      <p className="text-[var(--text-tertiary)]">{count} {t('monitoring.severity_count', { defaultValue: 'Members' }).toLowerCase()}</p>
    </div>
  )
}


function GroupMonitoringTab({ groupName }: { groupName: string }) {
  const { t } = useTranslation('groups')
  const [data, setData] = useState<Awaited<ReturnType<typeof api.groups.monitoring>> | null>(null)
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    invalidateCache(`/groups/${encodeURIComponent(groupName)}/monitoring`)
    api.groups.monitoring(groupName).then(setData).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [groupName]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <Skeleton className="h-32" />
  if (!data || data.member_count === 0) {
    return <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">{t('monitoring.empty', { defaultValue: 'No members' })}</p>
  }

  const severityChartData = (['critical', 'warning', 'healthy', 'unknown'] as const)
    .map(s => ({ severity: s, count: data.severity_counts[s] || 0 }))
    .filter(d => d.count > 0)

  return (
    <div className="space-y-4">
      {data.last_check_at && (
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)]">
          <Clock size={12} className="text-[var(--text-tertiary)]" />
          <span>{t('monitoring.last_check', { defaultValue: 'Last check' })}:</span>
          <span className="font-mono">{new Date(data.last_check_at).toLocaleString()}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="border border-[var(--border-subtle)] rounded-xl p-3">
          <div className="text-[11px] uppercase text-[var(--text-tertiary)] tracking-wide mb-2">{t('monitoring.severity', { defaultValue: 'Severity distribution' })}</div>
          {severityChartData.length === 0 ? (
            <p className="text-[12px] text-[var(--text-tertiary)] py-4 text-center">
              {t('monitoring.no_severity_data', { defaultValue: 'No severity data yet' })}
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={severityChartData} margin={{ top: 5, right: 5, bottom: 5, left: 5 }}>
                <XAxis
                  dataKey="severity"
                  tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                  axisLine={{ stroke: 'var(--border-default)' }}
                  tickFormatter={(s: string) => s.charAt(0).toUpperCase() + s.slice(1)}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                  axisLine={{ stroke: 'var(--border-default)' }}
                  width={28}
                />
                <Tooltip cursor={{ fill: 'var(--bg-secondary)' }} content={<SeverityTooltip />} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {severityChartData.map(entry => (
                    <Cell key={entry.severity} fill={SEVERITY_HEX[entry.severity] || SEVERITY_HEX.unknown} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="border border-[var(--border-subtle)] rounded-xl p-3 flex flex-col">
          <div className="text-[11px] uppercase text-[var(--text-tertiary)] tracking-wide">{t('monitoring.psi_avg', { defaultValue: 'Avg PSI' })}</div>
          <div className="text-2xl font-semibold mt-1 font-mono">
            {data.psi_average === null ? '—' : data.psi_average.toFixed(4)}
          </div>
          <div className="text-[11px] text-[var(--text-tertiary)] mt-auto pt-2">
            {t('monitoring.psi_thresholds', { defaultValue: '0.10 warning · 0.20 critical' })}
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-xs font-semibold uppercase text-[var(--text-tertiary)] tracking-wide">{t('monitoring.with_drift', { defaultValue: 'Members with drift' })}</h4>
          <button onClick={load} className="flex items-center gap-1 text-[11px] text-[var(--text-tertiary)] hover:text-brand">
            <RefreshCw size={11} /> {t('health.refresh', { defaultValue: 'Refresh' })}
          </button>
        </div>
        <div className="border border-[var(--border-subtle)] rounded-xl divide-y divide-[var(--border-subtle)]">
          {data.members_with_drift.length === 0 ? (
            <p className="text-sm text-[var(--text-tertiary)] py-3 text-center">{t('monitoring.no_drift', { defaultValue: 'No drifting members' })}</p>
          ) : data.members_with_drift.map(m => (
            <a key={m.spec} href={`/monitoring?feature=${encodeURIComponent(m.spec)}`} className="flex items-center justify-between px-3 py-2 text-[13px] hover:bg-[var(--bg-secondary)]">
              <span className="font-mono text-brand truncate">{m.spec}</span>
              <span className="flex items-center gap-2 shrink-0">
                <Badge variant={m.severity === 'critical' ? 'critical' : 'warning'}>{m.severity}</Badge>
                <span className="font-mono text-xs">{m.psi !== null ? m.psi.toFixed(4) : '-'}</span>
              </span>
            </a>
          ))}
        </div>
      </div>
    </div>
  )
}


function GroupDocsTab({ groupName, memberCount }: { groupName: string; memberCount: number }) {
  const { t } = useTranslation('groups')
  const [regenerate, setRegenerate] = useState(false)
  const [hint, setHint] = useState('')
  const [job, setJob] = useState<{ job_id: string; total: number } | null>(null)
  const [progress, setProgress] = useState<{ completed: number; failed: number; total: number; status: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = async () => {
    setError(null)
    setProgress(null)
    try {
      const res = await api.groups.regenerateDocs(groupName, { regenerate_existing: regenerate, global_hint: hint || null })
      setJob(res)
      setProgress({ completed: 0, failed: 0, total: res.total, status: 'running' })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start job')
    }
  }

  useEffect(() => {
    if (!job) return
    const id = setInterval(async () => {
      try {
        const st = await api.docs.batchStatus(job.job_id)
        setProgress({ completed: st.completed, failed: st.failed, total: st.total, status: st.status })
        if (st.status !== 'running') clearInterval(id)
      } catch {
        // ignore poll errors
      }
    }, 1500)
    return () => clearInterval(id)
  }, [job])

  if (memberCount === 0) {
    return <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">{t('docs.empty', { defaultValue: 'Add members before regenerating docs' })}</p>
  }

  return (
    <div className="space-y-4 max-w-xl">
      <p className="text-[13px] text-[var(--text-secondary)]">
        {t('docs.help', { defaultValue: 'Generate AI documentation for every member in this group. Existing docs are skipped unless regenerate is on.' })}
      </p>

      <label className="flex items-start gap-2 text-[13px] cursor-pointer">
        <input type="checkbox" checked={regenerate} onChange={(e) => setRegenerate(e.target.checked)} className="mt-0.5" />
        <span>
          {t('docs.regenerate_label', { defaultValue: 'Regenerate existing docs' })}
          <span className="block text-[11px] text-[var(--text-tertiary)]">{t('docs.regenerate_hint', { defaultValue: 'Overwrite docs for members that already have one.' })}</span>
        </span>
      </label>

      <div>
        <label className="block text-[12px] font-medium mb-1">{t('docs.hint_label', { defaultValue: 'Global hint (optional)' })}</label>
        <textarea
          rows={2}
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          placeholder={t('docs.hint_placeholder', { defaultValue: 'e.g. these features describe payment events' })}
          className="w-full bg-[var(--bg-primary)] border border-[var(--border-default)] rounded-lg px-3 py-2 text-[13px]"
        />
      </div>

      <button
        onClick={start}
        disabled={!!progress && progress.status === 'running'}
        className="flex items-center gap-1.5 px-4 py-2 bg-brand text-white rounded-lg text-[13px] font-medium hover:bg-brand-emphasis disabled:opacity-50"
      >
        <Sparkles size={14} />
        {progress?.status === 'running' ? t('docs.running', { defaultValue: 'Running…' }) : t('docs.start', { defaultValue: 'Regenerate docs' })}
      </button>

      {error && <p className="text-[12px] text-[var(--danger)]">{error}</p>}

      {progress && (
        <div className="border border-[var(--border-subtle)] rounded-xl p-3">
          <div className="flex items-center justify-between text-[12px] mb-2">
            <span>{t('docs.status', { defaultValue: 'Status' })}: <span className="font-mono">{progress.status}</span></span>
            <span className="font-mono">{progress.completed + progress.failed} / {progress.total}</span>
          </div>
          <div className="h-2 bg-[var(--bg-secondary)] rounded">
            <div
              className="h-full bg-brand rounded transition-all"
              style={{ width: `${progress.total === 0 ? 0 : Math.round(((progress.completed + progress.failed) / progress.total) * 100)}%` }}
            />
          </div>
          {progress.failed > 0 && (
            <p className="text-[11px] text-amber-500 mt-2">{t('docs.failed_count', { count: progress.failed, defaultValue: '{{count}} failure(s)' })}</p>
          )}
        </div>
      )}
    </div>
  )
}
