import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ReactElement } from 'react'
import { AuthProvider, type AuthContextValue } from '../../auth'

vi.mock('../../api', () => {
  const featureViews = [
    {
      id: 'fv1',
      name: 'billing.contract_health_view',
      entity: 'contract',
      source_name: 'billing_daily',
      source_entity: 'device',
      relationship: 'contract_to_device',
      aggregation: 'sum by contract_id',
      feature_names: ['billing.payment_delay_count_30d'],
      description: 'Contract health view',
      owner: 'billing-team',
      lifecycle_status: 'validated',
      created_at: '2026-06-01T00:00:00.000Z',
      updated_at: '2026-06-01T00:00:00.000Z',
    },
  ]
  const featureSets = [
    {
      id: 'fs1',
      name: 'churn.contract_serving_set',
      target_entity: 'contract',
      feature_names: ['billing.payment_delay_count_30d'],
      rollup_rules: { 'billing.payment_delay_count_30d': 'sum(device delays) by contract_id' },
      use_case: 'churn_model',
      description: 'Serving bundle for churn',
      owner: 'ml-platform',
      lifecycle_status: 'production',
      created_at: '2026-06-01T00:00:00.000Z',
      updated_at: '2026-06-01T00:00:00.000Z',
    },
  ]
  const features = [
    {
      name: 'billing.payment_delay_count_30d',
      leakage_risk: 'high',
    },
  ]

  return {
    invalidateCache: vi.fn(),
    api: {
      features: {
        get: vi.fn(async (name: string) => features.find((row) => row.name === name) ?? features[0]),
      },
      featureViews: {
        list: vi.fn(async () => featureViews),
        get: vi.fn(async (name: string) => featureViews.find((row) => row.name === name) ?? featureViews[0]),
        upsert: vi.fn(async () => featureViews[0]),
      },
      featureSets: {
        list: vi.fn(async () => featureSets),
        get: vi.fn(async (name: string) => featureSets.find((row) => row.name === name) ?? featureSets[0]),
        upsert: vi.fn(async () => featureSets[0]),
      },
    },
  }
})

import { FeatureViews } from '../FeatureViews'
import { FeatureSets } from '../FeatureSets'

function renderViews(path: string, element: ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/feature-views" element={element} />
        <Route path="/feature-views/:name" element={element} />
        <Route path="/feature-sets" element={element} />
        <Route path="/feature-sets/:name" element={element} />
      </Routes>
    </MemoryRouter>,
  )
}

const viewerAuth: AuthContextValue = {
  auth: {
    authenticated: true,
    required: true,
    user: {
      email: 'viewer@example.com',
      role: 'viewer',
      groups: [],
      auth_type: 'token',
    },
  },
  loading: false,
  refreshAuth: vi.fn(async () => {}),
  signInWithToken: vi.fn(async () => {}),
  signOut: vi.fn(async () => {}),
}

describe('Feature registry views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders feature views and opens detail', async () => {
    const user = userEvent.setup()
    renderViews('/feature-views', <FeatureViews />)

    expect(await screen.findByRole('heading', { name: /feature views/i, level: 1 })).toBeInTheDocument()
    expect(screen.getByText('billing.contract_health_view')).toBeInTheDocument()

    await user.click(screen.getByText('billing.contract_health_view'))
    await waitFor(() => {
      expect(screen.getByText('Contract health view')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /billing\.payment_delay_count_30d/i })).toBeInTheDocument()
  })

  it('renders feature sets and opens detail', async () => {
    const user = userEvent.setup()
    renderViews('/feature-sets', <FeatureSets />)

    expect(await screen.findByRole('heading', { name: /feature sets/i, level: 1 })).toBeInTheDocument()
    expect(screen.getByText('churn.contract_serving_set')).toBeInTheDocument()

    await user.click(screen.getByText('churn.contract_serving_set'))
    await waitFor(() => {
      expect(screen.getByText('Serving bundle for churn')).toBeInTheDocument()
    })
    expect(screen.getByText('sum(device delays) by contract_id')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/high leakage risk/i)
  })

  it('hides write actions for a viewer', async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider value={viewerAuth}>
        <MemoryRouter initialEntries={['/feature-views']}>
          <Routes>
            <Route path="/feature-views" element={<FeatureViews />} />
            <Route path="/feature-views/:name" element={<FeatureViews />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    )

    expect(await screen.findByRole('heading', { name: /feature views/i, level: 1 })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^new$/i })).not.toBeInTheDocument()

    await user.click(screen.getByText('billing.contract_health_view'))
    await waitFor(() => {
      expect(screen.getByText('Contract health view')).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument()
  })
})
