import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

/** Mock the entire api module so the GroupDetail page can mount without
 *  hitting fetch. Each api.groups.* method gets a stub that returns an
 *  empty-but-shaped payload — enough for the sub-tabs to render their
 *  loading / empty states without crashing.
 */
vi.mock('../../api', () => {
  const groupPayload = {
    name: 'churn_signals',
    project: 'demo',
    owner: 'uat-tester',
    description: 'Features for churn prediction',
    members: [
      { id: 'f1', name: 'demo.churn_flag', dtype: 'int64', has_doc: true },
      { id: 'f2', name: 'demo.usage_gb', dtype: 'double', has_doc: false },
    ],
  }

  return {
    invalidateCache: vi.fn(),
    api: {
      health: vi.fn(async () => ({ status: 'ok', llm: false })),
      groups: {
        get: vi.fn(async () => groupPayload),
        delete: vi.fn(async () => ({})),
        removeMember: vi.fn(async () => ({})),
        addMembers: vi.fn(async () => ({})),
        health: vi.fn(async () => ({
          group: 'churn_signals',
          member_count: 2,
          average_score: 70,
          grade_distribution: { A: 0, B: 1, C: 1, D: 0 },
          status_distribution: { healthy: 1, warning: 1, critical: 0, unknown: 0 },
          members: [
            { spec: 'demo.churn_flag', grade: 'B', score: 75, has_doc: true, drift_status: 'healthy' },
            { spec: 'demo.usage_gb', grade: 'C', score: 65, has_doc: false, drift_status: 'warning' },
          ],
          lowest_scored: [],
        })),
        monitoring: vi.fn(async () => ({
          group: 'churn_signals',
          member_count: 2,
          severity_counts: { healthy: 1, warning: 1, critical: 0, unknown: 0 },
          psi_average: 0.12,
          last_check_at: null,
          members_with_drift: [],
        })),
        driftMatrix: vi.fn(async () => ({
          date_range: [],
          features: [],
          truncated: false,
          total_count: 0,
        })),
        versions: vi.fn(async () => []),
        freeze: vi.fn(async () => ({})),
        regenerateDocs: vi.fn(async () => ({ status: 'success', queued: 0 })),
        exportUrl: vi.fn(() => '/api/groups/churn_signals/versions/1/export?format=md'),
      },
      features: {
        list: vi.fn(async () => []),
      },
    },
  }
})

import { GroupDetail } from '../GroupDetail'

/** Renders GroupDetail under MemoryRouter pointing at /groups/churn_signals
 *  so the useParams hook resolves the same way it would in production.
 */
function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/groups/:name" element={<GroupDetail />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('GroupDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the group header + members table from the mocked API payload', async () => {
    renderAt('/groups/churn_signals')

    // Header title (page header h1)
    expect(await screen.findByRole('heading', { name: /churn_signals/i, level: 1 })).toBeInTheDocument()
    // Description from payload
    expect(screen.getByText(/Features for churn prediction/i)).toBeInTheDocument()
    // Project badge
    expect(screen.getByText('demo')).toBeInTheDocument()
    // Both member names in the table
    expect(screen.getByText('demo.churn_flag')).toBeInTheDocument()
    expect(screen.getByText('demo.usage_gb')).toBeInTheDocument()
  })

  it('renders each required section landmark', async () => {
    renderAt('/groups/churn_signals')
    await screen.findByTestId('group-detail-page')
    expect(screen.getByTestId('group-detail-members')).toBeInTheDocument()
    expect(screen.getByTestId('group-detail-health')).toBeInTheDocument()
    expect(screen.getByTestId('group-detail-monitoring')).toBeInTheDocument()
    expect(screen.getByTestId('group-detail-versions')).toBeInTheDocument()
    expect(screen.getByTestId('group-detail-docs')).toBeInTheDocument()
  })

  it('opens the AddFeaturesModal (FeatureSelector inside) when "Add members" is clicked', async () => {
    const user = userEvent.setup()
    renderAt('/groups/churn_signals')

    const addBtn = await screen.findByRole('button', { name: /add members|add features/i })
    await user.click(addBtn)

    // The modal title contains the group name and renders a dialog
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })
})
