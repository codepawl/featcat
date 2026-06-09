import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import i18n from '../../i18n/config'

const mocks = vi.hoisted(() => ({
  materializationSchedules: vi.fn(),
  updateMaterializationSchedule: vi.fn(),
  runMaterializationSchedule: vi.fn(),
  materializations: vi.fn(),
  invalidateCache: vi.fn(),
}))

vi.mock('../../api', () => ({
  invalidateCache: mocks.invalidateCache,
  api: {
    online: {
      materializationSchedules: mocks.materializationSchedules,
      updateMaterializationSchedule: mocks.updateMaterializationSchedule,
      runMaterializationSchedule: mocks.runMaterializationSchedule,
      materializations: mocks.materializations,
    },
  },
}))

import { MaterializationSchedules } from '../MaterializationSchedules'

const schedule = {
  id: 'sched-1',
  name: 'hourly-transactions',
  source_name: 'transactions',
  feature_columns: ['avg_spend_30d', 'txn_count_30d', 'region_score', 'loyalty_score', 'risk_score'],
  project: 'churn',
  feature_view: 'transactions',
  schedule_type: 'interval',
  interval_seconds: 3600,
  cron_expression: null,
  enabled: true,
  actor: 'sdk-job',
  last_run_at: '2026-05-26T11:00:00Z',
  next_run_at: '2026-05-26T12:00:00Z',
  lease_owner: 'runner-1',
  lease_until: '2026-05-26T11:30:00Z',
  created_at: '2026-05-25T10:00:00Z',
  updated_at: '2026-05-26T11:00:00Z',
}

const successRun = {
  id: 'mat-1',
  status: 'success',
  source_name: 'transactions',
  source_path: '/tmp/transactions.parquet',
  project: 'churn',
  feature_view: 'transactions',
  entity_key: 'customer_id',
  event_timestamp_column: 'event_ts',
  created_timestamp_column: null,
  feature_columns: ['avg_spend_30d', 'txn_count_30d'],
  entity_count: 2,
  feature_count: 2,
  requested: 4,
  written: 4,
  skipped_older: 0,
  skipped_same_timestamp: 0,
  errors: [],
  warnings: [],
  actor: 'api',
  created_at: '2026-05-25T10:00:00Z',
}

const validationRun = {
  ...successRun,
  id: 'mat-2',
  status: 'validation_failed',
  source_path: 's3://featcat-smoke/materialization/source.parquet',
  project: '',
  feature_view: '',
  feature_columns: ['missing_feature', 'txn_count_30d', 'region_score', 'loyalty_score'],
  entity_count: 0,
  requested: 0,
  written: 0,
  skipped_older: 1,
  skipped_same_timestamp: 2,
  errors: [
    {
      code: 'missing_feature_column',
      message: 'Parquet source is missing feature column: missing_feature',
      field: 'missing_feature',
    },
  ],
  warnings: [
    {
      code: 'partial_write',
      message: 'Some rows were skipped',
      field: null,
    },
  ],
}

describe('MaterializationSchedules', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
  })

  it('renders schedules from the API', async () => {
    mocks.materializationSchedules.mockResolvedValueOnce([schedule])
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: /^materialization$/i, level: 1 })).toBeInTheDocument()
    expect(screen.getByText('hourly-transactions')).toBeInTheDocument()
    expect(screen.getByText('transactions')).toBeInTheDocument()
    expect(screen.getByText('avg_spend_30d')).toBeInTheDocument()
    expect(screen.getByText('+1')).toBeInTheDocument()
    expect(screen.getByText('churn / transactions')).toBeInTheDocument()
    expect(screen.getByText('3600')).toBeInTheDocument()
    expect(screen.getByText('runner-1')).toBeInTheDocument()
    expect(mocks.materializationSchedules).toHaveBeenCalledWith({ limit: 20, enabled: null })
  })

  it('renders the empty state when no schedules exist', async () => {
    mocks.materializationSchedules.mockResolvedValueOnce([])
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )

    expect(await screen.findByText(/No materialization configurations yet/i)).toBeInTheDocument()
    expect(screen.getByText(/CLI, API, or SDK/i)).toBeInTheDocument()
  })

  it('passes the selected enabled filter to the API', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValueOnce([schedule]).mockResolvedValueOnce([
      {
        ...schedule,
        id: 'sched-2',
        name: 'disabled-transactions',
        enabled: false,
      },
    ])
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    await screen.findByText('hourly-transactions')

    await user.selectOptions(screen.getByLabelText('Enabled filter'), 'disabled')

    await waitFor(() => {
      expect(mocks.materializationSchedules).toHaveBeenLastCalledWith({ limit: 20, enabled: false })
    })
  })

  it('shows an error state with retry', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules
      .mockRejectedValueOnce(new Error('schedule API failed'))
      .mockResolvedValueOnce([schedule])
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )

    expect(await screen.findByText('schedule API failed')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /retry/i }))

    expect(await screen.findByText('hourly-transactions')).toBeInTheDocument()
    expect(mocks.materializationSchedules).toHaveBeenCalledTimes(2)
  })

  it('enable action calls PATCH with enabled=true and refreshes schedules', async () => {
    const user = userEvent.setup()
    const disabledSchedule = { ...schedule, enabled: false }
    mocks.materializationSchedules.mockResolvedValueOnce([disabledSchedule]).mockResolvedValueOnce([schedule])
    mocks.updateMaterializationSchedule.mockResolvedValueOnce(schedule)
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    await screen.findByText('hourly-transactions')

    await user.click(screen.getByRole('button', { name: /enable/i }))

    expect(mocks.updateMaterializationSchedule).toHaveBeenCalledWith('sched-1', { enabled: true })
    await waitFor(() => {
      expect(mocks.materializationSchedules).toHaveBeenCalledTimes(2)
    })
  })

  it('disable action calls PATCH with enabled=false and refreshes schedules', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValueOnce([schedule]).mockResolvedValueOnce([
      {
        ...schedule,
        enabled: false,
      },
    ])
    mocks.updateMaterializationSchedule.mockResolvedValueOnce({ ...schedule, enabled: false })
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    await screen.findByText('hourly-transactions')

    await user.click(screen.getByRole('button', { name: /disable/i }))

    expect(mocks.updateMaterializationSchedule).toHaveBeenCalledWith('sched-1', { enabled: false })
    await waitFor(() => {
      expect(mocks.materializationSchedules).toHaveBeenCalledTimes(2)
    })
  })

  it('manual run calls POST, refreshes schedules, and shows a summary', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValueOnce([schedule]).mockResolvedValueOnce([schedule])
    mocks.materializations.mockResolvedValue([successRun])
    mocks.runMaterializationSchedule.mockResolvedValueOnce({
      schedule_id: 'sched-1',
      schedule_name: 'hourly-transactions',
      status: 'success',
      requested: 4,
      written: 4,
      skipped_older: 0,
      skipped_same_timestamp: 0,
      audit_id: 'mat-1',
    })

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    await screen.findByText('hourly-transactions')

    await user.click(screen.getByRole('button', { name: /run now/i }))

    expect(mocks.runMaterializationSchedule).toHaveBeenCalledWith('sched-1')
    expect(await screen.findByText(/requested=4 written=4/i)).toBeInTheDocument()
    expect(screen.getByText(/status=success/i)).toBeInTheDocument()
    expect(mocks.materializationSchedules).toHaveBeenCalledTimes(2)
  })

  it('action error displays an inline error message', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValueOnce([schedule])
    mocks.runMaterializationSchedule.mockRejectedValueOnce(new Error('manual run failed'))
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    await screen.findByText('hourly-transactions')

    await user.click(screen.getByRole('button', { name: /run now/i }))

    expect(await screen.findByText('manual run failed')).toBeInTheDocument()
  })

  it('does not introduce create or edit controls', async () => {
    mocks.materializationSchedules.mockResolvedValueOnce([schedule])
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    await screen.findByText('hourly-transactions')

    expect(screen.queryByRole('button', { name: /create/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
  })

  // Runs Tab tests
  it('renders runs tab and displays runs when clicked', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValue([schedule])
    mocks.materializations.mockResolvedValue([successRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    expect(await screen.findByText('hourly-transactions')).toBeInTheDocument()

    const runsTab = screen.getByRole('tab', { name: /Recent Runs/i })
    await user.click(runsTab)

    expect(await screen.findByText('/tmp/transactions.parquet')).toBeInTheDocument()
    expect(screen.getAllByText('success').length).toBeGreaterThan(0)
    expect(screen.getByText('avg_spend_30d')).toBeInTheDocument()
    expect(screen.getByText('churn / transactions')).toBeInTheDocument()
    expect(mocks.materializations).toHaveBeenCalledWith({ limit: 20, status: '' })
  })

  it('renders empty state in runs tab when no audits exist', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValue([schedule])
    mocks.materializations.mockResolvedValue([])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    expect(await screen.findByText('hourly-transactions')).toBeInTheDocument()

    const runsTab = screen.getByRole('tab', { name: /Recent Runs/i })
    await user.click(runsTab)

    expect(await screen.findByText(/No materialization runs yet/i)).toBeInTheDocument()
  })

  it('passes the selected status filter to the API in runs tab', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValue([schedule])
    mocks.materializations.mockResolvedValueOnce([successRun]).mockResolvedValueOnce([validationRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    expect(await screen.findByText('hourly-transactions')).toBeInTheDocument()
    const runsTab = screen.getByRole('tab', { name: /Recent Runs/i })
    await user.click(runsTab)

    await screen.findByText('/tmp/transactions.parquet')

    await user.selectOptions(screen.getByLabelText('Status filter'), 'validation_failed')

    await waitFor(() => {
      expect(mocks.materializations).toHaveBeenLastCalledWith({ limit: 20, status: 'validation_failed' })
    })
  })

  it('summarizes warnings and errors in runs tab', async () => {
    const user = userEvent.setup()
    mocks.materializationSchedules.mockResolvedValue([schedule])
    mocks.materializations.mockResolvedValue([validationRun])

    render(
      <MemoryRouter>
        <MaterializationSchedules />
      </MemoryRouter>,
    )
    expect(await screen.findByText('hourly-transactions')).toBeInTheDocument()
    const runsTab = screen.getByRole('tab', { name: /Recent Runs/i })
    await user.click(runsTab)

    const badges = await screen.findAllByText('validation failed')
    expect(badges.length).toBeGreaterThan(0)
    expect(screen.getByText('1 error')).toBeInTheDocument()
    expect(screen.getByText('1 warning')).toBeInTheDocument()
    expect(screen.getByText(/missing_feature: Parquet source is missing feature column/i)).toBeInTheDocument()
  })
})
