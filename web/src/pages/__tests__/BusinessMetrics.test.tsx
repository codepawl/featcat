import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../../api', () => {
  const rows = [
    {
      id: 'bm1',
      name: 'billing.payment_delay',
      business_metric_name: 'Payment delay count 30d',
      business_definition: 'Number of delayed payments in the last 30 days',
      metric_domain: 'billing',
      lifecycle_stage: 'manage',
      metric_group: 'payment_risk',
      metric_level: 'contract',
      entity_grain: 'contract_id',
      aggregation_rule: 'sum(device delays) by contract_id',
      mapped_features: ['billing.payment_delay_count_30d'],
      owner: 'billing-team',
      lifecycle_status: 'validated',
      allowed_use_cases: ['churn_model', 'collections_model'],
      external_id: 'ME-C-CT-56',
      source_systems: ['Billing & Payment System'],
      implementation_status: 'done',
      source_view: 'Per-Contract',
      created_at: '2026-06-01T00:00:00.000Z',
      updated_at: '2026-06-01T00:00:00.000Z',
    },
    {
      id: 'bm2',
      name: 'cx360.me-c-d-01.product-net-device-clients',
      business_metric_name: 'product-net-device-clients',
      business_definition: 'Connected clients per device',
      metric_domain: 'product',
      lifecycle_stage: 'consume',
      metric_group: 'cx360',
      metric_level: 'device',
      entity_grain: 'device_id',
      aggregation_rule: '',
      mapped_features: [],
      owner: 'cx-team',
      lifecycle_status: 'validated',
      allowed_use_cases: ['cx360'],
      external_id: 'ME-C-D-01',
      source_systems: ['ACS Server & TR-069'],
      implementation_status: 'done',
      source_view: 'Device',
      created_at: '2026-06-01T00:00:00.000Z',
      updated_at: '2026-06-01T00:00:00.000Z',
    },
  ]

  return {
    invalidateCache: vi.fn(),
    api: {
      businessMetrics: {
        list: vi.fn(async () => rows),
        get: vi.fn(async (name: string) => rows.find((row) => row.name === name) ?? rows[0]),
        upsert: vi.fn(async () => rows[0]),
        importCsv: vi.fn(async () => ({ total: 1, created: 1, updated: 0, skipped: 0, errors: [] })),
      },
    },
  }
})

import { BusinessMetrics } from '../BusinessMetrics'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/business-metrics" element={<BusinessMetrics />} />
        <Route path="/business-metrics/:name" element={<BusinessMetrics />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('BusinessMetrics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the registry list', async () => {
    renderAt('/business-metrics')
    expect(await screen.findByRole('heading', { name: /business metrics/i, level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Payment delay count 30d')).toBeInTheDocument()
    expect(screen.getByText('billing.payment_delay')).toBeInTheDocument()
  })

  it('opens the mapping detail and links mapped features', async () => {
    const user = userEvent.setup()
    renderAt('/business-metrics')

    await screen.findByText('Payment delay count 30d')
    await user.click(screen.getByText('Payment delay count 30d'))

    await waitFor(() => {
      expect(screen.getByTestId('business-metric-detail')).toBeInTheDocument()
    })
    expect(screen.getAllByText('Number of delayed payments in the last 30 days').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /billing\.payment_delay_count_30d/i })).toBeInTheDocument()
  })

  it('renders the CX matrix view', async () => {
    const user = userEvent.setup()
    renderAt('/business-metrics')

    await screen.findByText('Payment delay count 30d')
    await user.click(screen.getByRole('button', { name: /cx matrix/i }))

    expect(screen.getByText('Total metrics')).toBeInTheDocument()
    expect(screen.getByText('Device-level')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /product-net-device-clients/i })).toBeInTheDocument()
  })
})
