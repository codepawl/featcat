import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Layout } from './Layout'
import { api } from '../api'
import { AuthProvider, type AuthContextValue } from '../auth'

// SearchBar fires `api.search.suggest` once it's mounted; mock to a no-op so
// the Layout render is deterministic and doesn't depend on the network.
vi.spyOn(api.search, 'suggest').mockResolvedValue([])
vi.spyOn(api.auth, 'config').mockResolvedValue({
  company_name: 'FPT',
  allowed_email_domains: ['fpt.com'],
  request_access_enabled: true,
})

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

const guestAuthValue: AuthContextValue = {
  auth: {
    authenticated: false,
    required: false,
    user: null,
  },
  loading: false,
  refreshAuth: vi.fn(async () => {}),
  signInWithToken: vi.fn(async () => {}),
  signOut: vi.fn(async () => {}),
}

describe('Layout', () => {
  it('renders a sticky top bar with a global search combobox', () => {
    render(
      <AuthProvider value={authValue}>
        <MemoryRouter>
          <Layout>
            <p>child</p>
          </Layout>
        </MemoryRouter>
      </AuthProvider>,
    )
    const banner = screen.getByRole('banner')
    expect(banner).toBeInTheDocument()
    expect(banner.className).toContain('sticky')
    expect(banner.className).toContain('top-0')
    // SearchBar lives inside the banner.
    const combobox = screen.getByRole('combobox')
    expect(banner.contains(combobox)).toBe(true)
  })

  it('still renders the page children below the bar', () => {
    render(
      <AuthProvider value={authValue}>
        <MemoryRouter>
          <Layout>
            <p>hello world</p>
          </Layout>
        </MemoryRouter>
      </AuthProvider>,
    )
    expect(screen.getByText('hello world')).toBeInTheDocument()
  })

  it('exposes a visible sign-in entry point when signed out', async () => {
    const user = userEvent.setup()
    render(
      <AuthProvider value={guestAuthValue}>
        <MemoryRouter>
          <Layout>
            <p>child</p>
          </Layout>
        </MemoryRouter>
      </AuthProvider>,
    )

    await user.click(screen.getByRole('button', { name: /account/i }))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/FPT account/i)).toBeInTheDocument()
  })
})
