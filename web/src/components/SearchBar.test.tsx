import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { SearchBar } from './SearchBar'
import { api } from '../api'

type SuggestFn = typeof api.search.suggest

const SUGGESTIONS = [
  { id: '1', name: 'demo.churn_flag', dtype: 'int64', source: 'demo', rank: 0.9 },
  { id: '2', name: 'demo.usage_gb', dtype: 'double', source: 'demo', rank: 0.7 },
]

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="probe">{loc.pathname + loc.search}</div>
}

function renderBar(initialEntries: string[] = ['/']) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <SearchBar />
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SearchBar', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.spyOn(api.search, 'suggest').mockImplementation(((q: string) => {
      return Promise.resolve(
        SUGGESTIONS.filter((s) => s.name.includes(q.toLowerCase())),
      )
    }) as SuggestFn)
  })

  it('renders the input as a combobox', () => {
    renderBar()
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('shows debounced suggestions after typing', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderBar()
    await user.click(screen.getByRole('combobox'))
    await user.keyboard('churn')
    vi.advanceTimersByTime(250)
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /demo\.churn_flag/ })).toBeInTheDocument()
    })
    expect(api.search.suggest).toHaveBeenCalledWith('churn', 5)
  })

  it('Enter without an active suggestion navigates to /search?q=', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderBar()
    await user.click(screen.getByRole('combobox'))
    await user.keyboard('churn')
    vi.advanceTimersByTime(250)
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /demo\.churn_flag/ })).toBeInTheDocument()
    })
    await user.keyboard('{Enter}')
    expect(screen.getByTestId('probe').textContent).toBe('/search?q=churn')
  })

  it('ArrowDown + Enter picks the active suggestion and navigates to /features/<name>', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderBar()
    await user.click(screen.getByRole('combobox'))
    await user.keyboard('demo')
    vi.advanceTimersByTime(250)
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /demo\.usage_gb/ })).toBeInTheDocument()
    })
    await user.keyboard('{ArrowDown}{Enter}')
    expect(screen.getByTestId('probe').textContent).toBe('/features/demo.churn_flag')
  })

  it('Escape closes the dropdown without navigating', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderBar(['/groups'])
    await user.click(screen.getByRole('combobox'))
    await user.keyboard('demo')
    vi.advanceTimersByTime(250)
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).toBeInTheDocument()
    })
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
    expect(screen.getByTestId('probe').textContent).toBe('/groups')
  })

  it('refills input from ?q= when present', () => {
    renderBar(['/search?q=hello'])
    expect(screen.getByRole('combobox')).toHaveValue('hello')
  })
})
