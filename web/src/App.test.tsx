import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import App from './App'
import { api } from './api'

vi.mock('./components/Layout', () => ({
  Layout: ({ children }: { children: ReactNode }) => <div data-testid="layout">{children}</div>,
}))

vi.mock('./pages/Dashboard', () => ({
  Dashboard: () => <h1>Dashboard</h1>,
}))

describe('App shell', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(api.auth, 'me').mockResolvedValue({
      authenticated: false,
      required: false,
      user: null,
    })
  })

  it('renders the public app without a blocking auth gate', async () => {
    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByTestId('layout')).toBeInTheDocument()
    expect(screen.queryByText(/access required/i)).not.toBeInTheDocument()
  })
})
