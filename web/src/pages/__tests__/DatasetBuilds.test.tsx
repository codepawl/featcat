import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import i18n from '../../i18n/config'

const mocks = vi.hoisted(() => ({
  builds: vi.fn(),
  invalidateCache: vi.fn(),
}))

vi.mock('../../api', () => ({
  invalidateCache: mocks.invalidateCache,
  api: {
    datasets: {
      builds: mocks.builds,
    },
  },
}))

import { DatasetBuilds } from '../DatasetBuilds'

const successBuild = {
  id: 'build-1',
  status: 'success',
  entity_df_path: '/tmp/entities.parquet',
  source_path: '/tmp/features.parquet',
  source_name: null,
  output_path: '/tmp/training.parquet',
  entity_key: 'customer_id',
  entity_timestamp_column: 'event_ts',
  source_event_timestamp_column: 'feature_ts',
  feature_columns: ['avg_spend_30d', 'txn_count_30d'],
  row_count: 2,
  feature_count: 2,
  unresolved_row_count: 0,
  missing_feature_value_count: 0,
  errors: [],
  warnings: [],
  actor: 'api',
  created_at: '2026-05-25T10:00:00Z',
}

const validationBuild = {
  ...successBuild,
  id: 'build-2',
  status: 'validation_failed',
  source_path: null,
  source_name: 'warehouse_features',
  output_path: null,
  row_count: 0,
  unresolved_row_count: 3,
  missing_feature_value_count: 4,
  feature_columns: ['avg_spend_30d', 'txn_count_30d', 'region_score', 'loyalty_score'],
  errors: [
    {
      code: 'source_dataframe_missing_entity_key',
      message: 'Missing customer_id in source dataframe',
      field: 'entity_key',
    },
  ],
  warnings: [
    {
      code: 'unresolved_rows',
      message: '3 entity rows did not resolve',
      field: null,
    },
  ],
}

describe('DatasetBuilds', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
  })

  it('renders recent dataset builds from the API', async () => {
    mocks.builds.mockResolvedValueOnce([successBuild])

    render(<DatasetBuilds />)

    expect(await screen.findByRole('heading', { name: /dataset builds/i, level: 1 })).toBeInTheDocument()
    expect(screen.getAllByText('success').length).toBeGreaterThan(0)
    expect(screen.getByText('/tmp/entities.parquet')).toBeInTheDocument()
    expect(screen.getByText('/tmp/training.parquet')).toBeInTheDocument()
    expect(screen.getByText('avg_spend_30d')).toBeInTheDocument()
    expect(mocks.builds).toHaveBeenCalledWith({ limit: 20, status: '' })
  })

  it('renders the empty state when no audits exist', async () => {
    mocks.builds.mockResolvedValueOnce([])

    render(<DatasetBuilds />)

    expect(await screen.findByText(/No dataset builds yet/i)).toBeInTheDocument()
    expect(screen.getByText(/API builder/i)).toBeInTheDocument()
  })

  it('passes the selected status filter to the API', async () => {
    const user = userEvent.setup()
    mocks.builds.mockResolvedValueOnce([successBuild]).mockResolvedValueOnce([validationBuild])

    render(<DatasetBuilds />)
    await screen.findByText('success')

    await user.selectOptions(screen.getByLabelText('Status filter'), 'validation_failed')

    await waitFor(() => {
      expect(mocks.builds).toHaveBeenLastCalledWith({ limit: 20, status: 'validation_failed' })
    })
  })

  it('summarizes warnings and errors', async () => {
    mocks.builds.mockResolvedValueOnce([validationBuild])

    render(<DatasetBuilds />)

    expect(await screen.findByText('validation failed')).toBeInTheDocument()
    expect(screen.getByText('1 error')).toBeInTheDocument()
    expect(screen.getByText('1 warning')).toBeInTheDocument()
    expect(screen.getByText(/entity_key: Missing customer_id/i)).toBeInTheDocument()
  })
})
