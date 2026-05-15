import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Download, Trash2, UserPlus } from 'lucide-react'
import { api, invalidateCache } from '../api'
import { Alert } from '../components/Alert'
import { Badge } from '../components/Badge'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { DataTable } from '../components/DataTable'
import { ExportModal } from '../components/ExportModal'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import {
  AddFeaturesModal,
  GroupDocsTab,
  GroupHealthTab,
  GroupMonitoringTab,
  GroupVersionsTab,
} from './Groups'

interface GroupMember {
  id: string
  name: string
  dtype: string
  has_doc: boolean
}

interface GroupDetailPayload {
  name: string
  description?: string
  project?: string
  owner?: string
  members?: GroupMember[]
}

/**
 * Dedicated route for a single group's detail. Reuses the tab components
 * from Groups.tsx (members table is inlined here since it's small and
 * needs the page-local remove handler).
 *
 * Sections mirror the in-place detail panel on /groups so the deep-link
 * lands the operator on the same view they would have built by clicking
 * a card. The UAT finding "groups/<name> route missing" was specifically
 * about not being able to share a URL that pre-selects a group.
 */
export function GroupDetail() {
  const { t } = useTranslation('groups')
  const navigate = useNavigate()
  const { name } = useParams<{ name: string }>()

  const [detail, setDetail] = useState<GroupDetailPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addOpen, setAddOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const load = (): void => {
    if (!name) return
    setLoading(true)
    setError(null)
    invalidateCache(`/groups/${encodeURIComponent(name)}`)
    api.groups
      .get(name)
      .then((d) => setDetail(d as GroupDetailPayload))
      .catch((e: unknown) => {
        setDetail(null)
        setError(e instanceof Error ? e.message : t('errors.load_failed', { defaultValue: 'Failed to load group' }))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name])

  const removeMember = async (spec: string): Promise<void> => {
    if (!name) return
    await api.groups.removeMember(name, spec)
    invalidateCache('/groups')
    load()
  }

  const deleteGroup = async (): Promise<void> => {
    if (!name) return
    await api.groups.delete(name)
    invalidateCache('/groups')
    navigate('/groups')
  }

  if (!name) {
    return (
      <Alert
        severity="danger"
        message={t('errors.missing_name', { defaultValue: 'Missing group name' })}
        className="mb-4"
      />
    )
  }

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-32" />
        <Skeleton className="h-48" />
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div>
        <Link
          to="/groups"
          className="inline-flex items-center gap-1.5 text-[13px] text-brand hover:underline mb-3"
        >
          <ArrowLeft size={14} /> {t('detail.back_to_list', { defaultValue: 'Back to groups' })}
        </Link>
        <Alert severity="danger" message={error ?? t('errors.not_found', { defaultValue: 'Group not found' })} />
      </div>
    )
  }

  const members = detail.members ?? []
  const memberCount = members.length

  const memberColumns = [
    {
      key: 'name',
      label: t('member_table.feature'),
      render: (r: GroupMember) => <span className="font-medium text-brand">{r.name}</span>,
    },
    {
      key: 'dtype',
      label: t('member_table.dtype'),
      render: (r: GroupMember) => <span className="font-mono text-xs">{r.dtype}</span>,
    },
    {
      key: 'has_doc',
      label: t('member_table.docs'),
      sortable: false,
      render: (r: GroupMember) =>
        r.has_doc ? (
          <Badge variant="success">{t('member_table.has_docs_yes')}</Badge>
        ) : (
          <span className="text-[var(--text-tertiary)]">-</span>
        ),
    },
    {
      key: '_remove',
      label: '',
      sortable: false,
      render: (r: GroupMember) => (
        <button
          onClick={(e) => {
            e.stopPropagation()
            void removeMember(r.name)
          }}
          className="text-[var(--text-tertiary)] hover:text-[var(--danger)] transition-colors p-1"
          aria-label={`Remove ${r.name}`}
        >
          <Trash2 size={13} />
        </button>
      ),
    },
  ]

  return (
    <div data-testid="group-detail-page">
      <Link
        to="/groups"
        className="inline-flex items-center gap-1.5 text-[13px] text-brand hover:underline mb-3"
      >
        <ArrowLeft size={14} /> {t('detail.back_to_list', { defaultValue: 'Back to groups' })}
      </Link>

      <PageHeader
        title={detail.name}
        actions={
          <div className="flex gap-2">
            <button
              onClick={() => setAddOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]"
            >
              <UserPlus size={14} /> {t('actions.add_features')}
            </button>
            {memberCount > 0 && (
              <button
                onClick={() => setExportOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg hover:bg-[var(--bg-secondary)]"
              >
                <Download size={14} /> {t('actions.export')}
              </button>
            )}
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--danger-subtle-bg)] text-[var(--danger)] rounded-lg hover:bg-[var(--danger-subtle-bg)]"
            >
              <Trash2 size={14} /> {t('actions.delete')}
            </button>
          </div>
        }
      />

      {/* Header metadata */}
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-4">
        <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)] mb-2">
          {detail.project && <Badge variant="info">{detail.project}</Badge>}
          {detail.owner && (
            <span>
              {t('detail.owner_label')}: {detail.owner}
            </span>
          )}
        </div>
        {detail.description && (
          <p className="text-sm text-[var(--text-secondary)]">{detail.description}</p>
        )}
      </div>

      {/* Members */}
      <section
        data-testid="group-detail-members"
        className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-4"
      >
        <h3 className="text-sm font-semibold mb-3">
          {t('tabs.members', { defaultValue: 'Members' })} ({memberCount})
        </h3>
        {memberCount > 0 ? (
          <DataTable columns={memberColumns} data={members} pageSize={20} />
        ) : (
          <p className="text-sm text-[var(--text-tertiary)] py-4 text-center">
            {t('detail.members_empty', { defaultValue: 'This group has no features yet. Add some.' })}
          </p>
        )}
      </section>

      {/* Health */}
      <section
        data-testid="group-detail-health"
        className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-4"
      >
        <h3 className="text-sm font-semibold mb-3">
          {t('tabs.health', { defaultValue: 'Health' })}
        </h3>
        <GroupHealthTab groupName={detail.name} />
      </section>

      {/* Monitoring */}
      <section
        data-testid="group-detail-monitoring"
        className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-4"
      >
        <h3 className="text-sm font-semibold mb-3">
          {t('tabs.monitoring', { defaultValue: 'Monitoring' })}
        </h3>
        <GroupMonitoringTab groupName={detail.name} />
      </section>

      {/* Versions */}
      <section
        data-testid="group-detail-versions"
        className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-4"
      >
        <h3 className="text-sm font-semibold mb-3">
          {t('tabs.versions', { defaultValue: 'Versions' })}
        </h3>
        <GroupVersionsTab groupName={detail.name} memberCount={memberCount} />
      </section>

      {/* Docs */}
      <section
        data-testid="group-detail-docs"
        className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-5 mb-4"
      >
        <h3 className="text-sm font-semibold mb-3">
          {t('tabs.docs', { defaultValue: 'Docs' })}
        </h3>
        <GroupDocsTab groupName={detail.name} memberCount={memberCount} />
      </section>

      <AddFeaturesModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        groupName={detail.name}
        description={detail.description ?? ''}
        existingMemberIds={members.map((m) => m.id).filter(Boolean)}
        onAdded={() => {
          setAddOpen(false)
          load()
        }}
      />

      <ExportModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        title={t('export_title', { name: detail.name, count: memberCount })}
        featureSpecs={members.map((m) => m.name)}
        groupName={detail.name}
      />

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        title={t('confirm_delete', { name: detail.name })}
        confirmLabel={t('actions.delete')}
        onConfirm={deleteGroup}
      />
    </div>
  )
}
