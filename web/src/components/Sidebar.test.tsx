import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import i18n from '../i18n/config'

const mocks = vi.hoisted(() => ({
  health: vi.fn(),
  count: vi.fn(),
}))

vi.mock('../api', () => ({
  api: {
    health: mocks.health,
    actions: {
      count: mocks.count,
    },
  },
}))

import { Sidebar } from './Sidebar'

describe('Sidebar', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    await i18n.changeLanguage('en')
    window.localStorage.clear()
    mocks.health.mockResolvedValue({ status: 'ok', llm: false })
    mocks.count.mockResolvedValue({ count: 0 })
  })

  it('includes the materialization navigation entry', async () => {
    render(
      <MemoryRouter initialEntries={['/online/materialization-schedules']}>
        <Sidebar />
      </MemoryRouter>,
    )

    const link = await screen.findByRole('link', { name: /^materialization$/i })
    expect(link).toHaveAttribute('href', '/online/materialization-schedules')
  })
})
