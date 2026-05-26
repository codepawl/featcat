import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import i18n from '../../i18n/config'

const mocks = vi.hoisted(() => ({
  materializationSchedules: vi.fn(),
  updateMaterializationSchedule: vi.fn(),
  runMaterializationSchedule: vi.fn(),
  invalidateCache: vi.fn(),
}))

vi.mock('../../api', () => ({
  invalidateCache: mocks.invalidateCache,
  api: {
    online: {
      materializationSchedules: mocks.materializationSchedules,
      updateMaterializationSchedule: mocks.updateMaterializationSchedule,
      runMaterializationSchedule: mocks.runMaterializationSchedule,
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

describe('MaterializationSchedules', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
  })

  it('renders schedules from the API', async () => {
    mocks.materializationSchedules.mockResolvedValueOnce([schedule])

    render(<MaterializationSchedules />)

    expect(await screen.findByRole('heading', { name: /materialization schedules/i, level: 1 })).toBeInTheDocument()
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

    render(<MaterializationSchedules />)

    expect(await screen.findByText(/No materialization schedules yet/i)).toBeInTheDocument()
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

    render(<MaterializationSchedules />)
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

    render(<MaterializationSchedules />)

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

    render(<MaterializationSchedules />)
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

    render(<MaterializationSchedules />)
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

    render(<MaterializationSchedules />)
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

    render(<MaterializationSchedules />)
    await screen.findByText('hourly-transactions')

    await user.click(screen.getByRole('button', { name: /run now/i }))

    expect(await screen.findByText('manual run failed')).toBeInTheDocument()
  })

  it('does not introduce create or edit controls', async () => {
    mocks.materializationSchedules.mockResolvedValueOnce([schedule])

    render(<MaterializationSchedules />)
    await screen.findByText('hourly-transactions')

    expect(screen.queryByRole('button', { name: /create/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument()
  })
})
