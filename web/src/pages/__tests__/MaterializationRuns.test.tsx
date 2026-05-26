import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import i18n from '../../i18n/config'

const mocks = vi.hoisted(() => ({
  materializations: vi.fn(),
  invalidateCache: vi.fn(),
}))

vi.mock('../../api', () => ({
  invalidateCache: mocks.invalidateCache,
  api: {
    online: {
      materializations: mocks.materializations,
    },
  },
}))

import { MaterializationRuns } from '../MaterializationRuns'

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

describe('MaterializationRuns', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
  })

  it('renders recent materialization runs from the API', async () => {
    mocks.materializations.mockResolvedValueOnce([successRun])

    render(<MaterializationRuns />)

    expect(await screen.findByRole('heading', { name: /materialization runs/i, level: 1 })).toBeInTheDocument()
    expect(screen.getAllByText('success').length).toBeGreaterThan(0)
    expect(screen.getByText('transactions')).toBeInTheDocument()
    expect(screen.getByText('/tmp/transactions.parquet')).toBeInTheDocument()
    expect(screen.getByText('avg_spend_30d')).toBeInTheDocument()
    expect(screen.getByText('churn / transactions')).toBeInTheDocument()
    expect(mocks.materializations).toHaveBeenCalledWith({ limit: 20, status: '' })
  })

  it('renders the empty state when no audits exist', async () => {
    mocks.materializations.mockResolvedValueOnce([])

    render(<MaterializationRuns />)

    expect(await screen.findByText(/No materialization runs yet/i)).toBeInTheDocument()
    expect(screen.getByText(/API, CLI, or SDK/i)).toBeInTheDocument()
  })

  it('passes the selected status filter to the API', async () => {
    const user = userEvent.setup()
    mocks.materializations.mockResolvedValueOnce([successRun]).mockResolvedValueOnce([validationRun])

    render(<MaterializationRuns />)
    await screen.findByText('/tmp/transactions.parquet')

    await user.selectOptions(screen.getByLabelText('Status filter'), 'validation_failed')

    await waitFor(() => {
      expect(mocks.materializations).toHaveBeenLastCalledWith({ limit: 20, status: 'validation_failed' })
    })
  })

  it('summarizes warnings and errors', async () => {
    mocks.materializations.mockResolvedValueOnce([validationRun])

    render(<MaterializationRuns />)

    expect(await screen.findByText('validation failed')).toBeInTheDocument()
    expect(screen.getByText('1 error')).toBeInTheDocument()
    expect(screen.getByText('1 warning')).toBeInTheDocument()
    expect(screen.getByText(/missing_feature: Parquet source is missing feature column/i)).toBeInTheDocument()
    expect(screen.getByText('s3://featcat-smoke/materialization/source.parquet')).toBeInTheDocument()
  })
})
