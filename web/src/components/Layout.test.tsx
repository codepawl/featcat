import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Layout } from './Layout'
import { api } from '../api'

// SearchBar fires `api.search.suggest` once it's mounted; mock to a no-op so
// the Layout render is deterministic and doesn't depend on the network.
vi.spyOn(api.search, 'suggest').mockResolvedValue([])

describe('Layout', () => {
  it('renders a sticky top bar with a global search combobox', () => {
    render(
      <MemoryRouter>
        <Layout>
          <p>child</p>
        </Layout>
      </MemoryRouter>,
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
      <MemoryRouter>
        <Layout>
          <p>hello world</p>
        </Layout>
      </MemoryRouter>,
    )
    expect(screen.getByText('hello world')).toBeInTheDocument()
  })
})
