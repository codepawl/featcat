/** Dev-only showcase page for the shared UI components. Registered at
 *  `/dev/components` only when `import.meta.env.DEV` is true so it never
 *  ships in production builds.
 *
 *  Purpose: visual review of every variant + sanity check that interactions
 *  work without launching all 14 page-level migrations. Keep examples short
 *  and self-contained.
 */

import { useState } from 'react'
import { Activity, Database, FolderKanban, HardDrive, Plus, Search as SearchIcon, Settings as SettingsIcon } from 'lucide-react'
import { PageHeader } from '../../components/PageHeader'
import { EmptyState } from '../../components/EmptyState'
import { RefreshButton } from '../../components/RefreshButton'
import { FilterSelect, FilterClearLink, FilterCountChip } from '../../components/filters'
import { Tabs, type TabDefinition } from '../../components/Tabs'
import { Alert } from '../../components/Alert'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { SegmentedBar } from '../../components/SegmentedBar'

type FilterValue = 'all' | 'local' | 's3'
type DemoTab = 'overview' | 'history' | 'docs'
type UrlSyncTab = 'graph' | 'matrix' | 'pairs'

const TABS: TabDefinition<DemoTab>[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'history', label: 'History' },
  { id: 'docs', label: 'Docs' },
]

const ICON_TABS: TabDefinition<DemoTab>[] = [
  { id: 'overview', label: 'Members', icon: FolderKanban },
  { id: 'history', label: 'Health', icon: Activity },
  { id: 'docs', label: 'Settings', icon: SettingsIcon },
]

const BADGE_TABS: TabDefinition<DemoTab>[] = [
  { id: 'overview', label: 'Inbox', badge: <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-brand text-white">3</span> },
  { id: 'history', label: 'Drafts', badge: <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-tertiary)]">12</span> },
  { id: 'docs', label: 'Archive' },
]

const URL_TABS: TabDefinition<UrlSyncTab>[] = [
  { id: 'graph', label: 'Graph' },
  { id: 'matrix', label: 'Matrix' },
  { id: 'pairs', label: 'Pairs' },
]

const FILTER_OPTIONS: { value: FilterValue; label: string }[] = [
  { value: 'all', label: 'All types' },
  { value: 'local', label: 'Local' },
  { value: 's3', label: 'S3' },
]

export function Components() {
  return (
    <div className="space-y-12">
      <PageHeader
        title="Shared UI components"
        subtitle="Visual showcase / dev-only at /dev/components"
        size="compact"
      />

      <Section title="PageHeader">
        <PageHeader title="Default header" />
        <Divider />
        <PageHeader title="With actions" actions={<button className="px-4 py-2 bg-brand text-white rounded-lg text-[13px] font-medium">Action</button>} />
        <Divider />
        <PageHeader title="Compact + subtitle" subtitle="Useful for Audit / Actions pages" size="compact" />
      </Section>

      <Section title="EmptyState">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Card label="empty (default icon)">
            <EmptyState title="No sources yet" />
          </Card>
          <Card label="empty + description + CTA">
            <EmptyState
              icon={HardDrive}
              title="No sources yet"
              description="Add a parquet path or S3 URI to get started."
              action={{ label: 'Add first source', onClick: () => alert('clicked') }}
            />
          </Card>
          <Card label="bordered surface">
            <EmptyState
              surface="bordered"
              title="No matches"
              description="Try removing some filters."
              action={{ label: 'Clear filters', onClick: () => alert('clicked') }}
            />
          </Card>
          <Card label="error variant">
            <EmptyState
              variant="error"
              title="Failed to load"
              description="Check the connection and try again."
              action={{ label: 'Retry', onClick: () => alert('retry') }}
            />
          </Card>
        </div>
      </Section>

      <Section title="RefreshButton">
        <RefreshButtonDemo />
      </Section>

      <Section title="Filters">
        <FilterDemo />
      </Section>

      <Section title="Tabs">
        <div className="space-y-6">
          <Card label="Plain tabs">
            <TabsBasicDemo tabs={TABS} />
          </Card>
          <Card label="With icons">
            <TabsBasicDemo tabs={ICON_TABS} />
          </Card>
          <Card label="With badges">
            <TabsBasicDemo tabs={BADGE_TABS} />
          </Card>
          <Card label="URL synced — open with ?view=matrix or click around">
            <TabsUrlSyncDemo />
          </Card>
        </div>
      </Section>

      <Section title="Alert">
        <AlertDemo />
      </Section>

      <Section title="ConfirmDialog">
        <ConfirmDialogDemo />
      </Section>

      <Section title="SegmentedBar">
        <SegmentedBarDemo />
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold mb-3">{title}</h2>
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-xl p-4 space-y-3">
        {children}
      </div>
    </section>
  )
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border border-[var(--border-subtle)] rounded-lg p-3">
      <p className="text-[11px] uppercase tracking-wider text-[var(--text-tertiary)] mb-2">{label}</p>
      {children}
    </div>
  )
}

function Divider() {
  return <hr className="border-[var(--border-subtle)] my-2" />
}

function RefreshButtonDemo() {
  const [loading, setLoading] = useState(false)
  const click = () => {
    setLoading(true)
    setTimeout(() => setLoading(false), 1200)
  }
  return (
    <div className="flex gap-3 items-center">
      <RefreshButton onClick={click} loading={loading} />
      <RefreshButton onClick={click} loading={loading} size="compact" label="Reload" />
      <span className="text-xs text-[var(--text-tertiary)]">Click to see the loading spin (1.2s).</span>
    </div>
  )
}

function FilterDemo() {
  const [type, setType] = useState<FilterValue>('all')
  const [sort, setSort] = useState<'name' | 'count'>('name')
  const showClear = type !== 'all' || sort !== 'name'
  return (
    <div className="flex gap-3 items-center flex-wrap">
      <FilterSelect<FilterValue> value={type} onChange={setType} options={FILTER_OPTIONS} ariaLabel="Storage type" />
      <FilterSelect
        value={sort}
        onChange={(v) => setSort(v as 'name' | 'count')}
        options={[
          { value: 'name', label: 'Sort: name' },
          { value: 'count', label: 'Sort: feature count' },
        ]}
        ariaLabel="Sort key"
      />
      <FilterClearLink show={showClear} onClick={() => { setType('all'); setSort('name') }} />
      <FilterCountChip count={42} label="features" />
    </div>
  )
}

function TabsBasicDemo({ tabs }: { tabs: TabDefinition<DemoTab>[] }) {
  const [value, setValue] = useState<DemoTab>('overview')
  return <Tabs<DemoTab> tabs={tabs} value={value} onChange={setValue} />
}

function TabsUrlSyncDemo() {
  const [value, setValue] = useState<UrlSyncTab>('graph')
  return <Tabs<UrlSyncTab> tabs={URL_TABS} value={value} onChange={setValue} syncToUrl={{ param: 'view' }} />
}

function AlertDemo() {
  const [errorOpen, setErrorOpen] = useState(true)
  return (
    <div className="space-y-3">
      <Alert severity="info" message="Build started" />
      <Alert severity="warning" message="Cache is stale — consider refreshing" />
      <Alert severity="success" message="Saved" />
      <Alert severity="danger" message="Uncontrolled: clicking × hides this alert internally." dismissible />
      <div>
        <Alert
          severity="danger"
          message={`Controlled (open=${errorOpen}): parent owns visibility.`}
          dismissible
          open={errorOpen}
          onOpenChange={setErrorOpen}
        />
        {!errorOpen && (
          <button onClick={() => setErrorOpen(true)} className="mt-2 text-xs text-brand hover:underline">
            Bring it back
          </button>
        )}
      </div>
    </div>
  )
}

function ConfirmDialogDemo() {
  const [simpleOpen, setSimpleOpen] = useState(false)
  const [matchOpen, setMatchOpen] = useState(false)
  const [pendingOpen, setPendingOpen] = useState(false)
  const [ackOpen, setAckOpen] = useState(false)
  const pendingConfirm = () => new Promise<void>((r) => setTimeout(r, 1500))

  return (
    <div className="flex gap-3 flex-wrap">
      <button onClick={() => setSimpleOpen(true)} className="px-3 py-1.5 text-sm border border-[var(--border-default)] rounded-lg">
        Plain destructive
      </button>
      <button onClick={() => setMatchOpen(true)} className="px-3 py-1.5 text-sm border border-[var(--border-default)] rounded-lg">
        With type-to-confirm
      </button>
      <button onClick={() => setPendingOpen(true)} className="px-3 py-1.5 text-sm border border-[var(--border-default)] rounded-lg">
        With async pending
      </button>
      <button onClick={() => setAckOpen(true)} className="px-3 py-1.5 text-sm border border-[var(--border-default)] rounded-lg">
        With checkbox gate
      </button>

      <ConfirmDialog
        open={simpleOpen}
        onClose={() => setSimpleOpen(false)}
        title="Delete source &quot;demo_v1&quot;?"
        message="3 features will be removed."
        warning="This action cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => { alert('deleted'); setSimpleOpen(false) }}
      />

      <ConfirmDialog
        open={matchOpen}
        onClose={() => setMatchOpen(false)}
        title="Delete source &quot;customer_events_v2&quot;?"
        message="42 features and 3 groups depend on this source."
        warning="This action cannot be undone."
        confirmLabel="Delete"
        requireTextMatch={{ value: 'customer_events_v2', label: 'Type the source name to confirm' }}
        onConfirm={() => { alert('deleted'); setMatchOpen(false) }}
      />

      <ConfirmDialog
        open={pendingOpen}
        onClose={() => setPendingOpen(false)}
        title="Run a long task"
        message="Click confirm — the dialog will stay open for ~1.5s while pending."
        confirmLabel="Run"
        pendingLabel="Running…"
        severity="info"
        onConfirm={async () => { await pendingConfirm(); setPendingOpen(false) }}
      />

      <ConfirmDialog
        open={ackOpen}
        onClose={() => setAckOpen(false)}
        title="Bulk delete 137 features"
        warning="Deleting features removes their docs, baselines, and group memberships."
        confirmLabel="Delete"
        requireCheckbox="I understand this is irreversible"
        onConfirm={() => { alert('confirmed'); setAckOpen(false) }}
      />
    </div>
  )
}

function SegmentedBarDemo() {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs text-[var(--text-tertiary)] mb-1">Grade distribution (decorative)</p>
        <SegmentedBar
          ariaLabel="Grade distribution"
          height={16}
          segments={[
            { value: 18, color: 'bg-green-500', label: 'A: 18' },
            { value: 22, color: 'bg-teal-500', label: 'B: 22' },
            { value: 9, color: 'bg-amber-500', label: 'C: 9' },
            { value: 4, color: 'bg-red-500', label: 'D: 4' },
          ]}
        />
      </div>
      <div>
        <p className="text-xs text-[var(--text-tertiary)] mb-1">Clickable segments (each is a button)</p>
        <SegmentedBar
          ariaLabel="Certification status"
          height={16}
          segments={[
            { value: 30, color: 'bg-[var(--text-tertiary)]', label: 'Draft (click)', onClick: () => alert('draft') },
            { value: 25, color: 'bg-amber-400', label: 'Reviewed', onClick: () => alert('reviewed') },
            { value: 40, color: 'bg-green-500', label: 'Certified', onClick: () => alert('certified') },
            { value: 5, color: 'bg-red-400', label: 'Deprecated', onClick: () => alert('deprecated') },
          ]}
        />
      </div>
      <div>
        <p className="text-xs text-[var(--text-tertiary)] mb-1">Thin variant (h-1.5, single segment style)</p>
        <SegmentedBar
          ariaLabel="Doc coverage"
          height={6}
          segments={[
            { value: 72, color: 'bg-[var(--brand)]', label: '72% documented' },
            { value: 28, color: 'bg-transparent' },
          ]}
        />
      </div>
    </div>
  )
}
