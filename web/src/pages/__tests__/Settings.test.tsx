import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import i18n from '../../i18n/config'
import { Settings } from '../Settings'
import { AuthProvider, type AuthContextValue } from '../../auth'

const mocks = vi.hoisted(() => ({
  health: vi.fn(),
  cacheStats: vi.fn(),
  cacheClear: vi.fn(),
  cacheClearExpired: vi.fn(),
}))

vi.mock('../../api', () => ({
  invalidateCache: vi.fn(),
  api: {
    health: mocks.health,
    auth: {
      accessRequests: vi.fn(async () => []),
    },
    admin: {
      cacheStats: mocks.cacheStats,
      cacheClear: mocks.cacheClear,
      cacheClearExpired: mocks.cacheClearExpired,
    },
  },
}))

describe('Settings page and SystemStatus', () => {
  const authValue: AuthContextValue = {
    auth: {
      authenticated: true,
      required: true,
      user: {
        email: 'admin@example.com',
        role: 'admin',
        groups: [],
        auth_type: 'token',
      },
    },
    loading: false,
    refreshAuth: vi.fn(async () => {}),
    signInWithToken: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
  }

  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
    mocks.health.mockResolvedValue({ status: 'ok', llm: true, model: 'claude-3-5-sonnet' })
    mocks.cacheStats.mockResolvedValue({ total: 10, active: 8, expired: 2 })
  })

  it('renders the Settings page and the SystemStatus component', async () => {
    render(
      <AuthProvider value={authValue}>
        <Settings />
      </AuthProvider>,
    )

    expect(await screen.findByRole('heading', { name: /Settings/i, level: 1 })).toBeInTheDocument()

    expect(await screen.findByText('Server:')).toBeInTheDocument()
    expect(await screen.findByText('Connected')).toBeInTheDocument()

    expect(await screen.findByText('AI / LLM:')).toBeInTheDocument()
    expect(await screen.findByText('claude-3-5-sonnet')).toBeInTheDocument()
  })

  it('renders system status correctly when server is offline', async () => {
    mocks.health.mockRejectedValue(new Error('Backend offline'))
    render(
      <AuthProvider value={authValue}>
        <Settings />
      </AuthProvider>,
    )

    expect(await screen.findByText('Server:')).toBeInTheDocument()
    const disconnectedLabels = await screen.findAllByText('Disconnected')
    expect(disconnectedLabels.length).toBeGreaterThan(0)
  })
})
