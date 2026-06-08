import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ReactElement } from 'react'

vi.mock('../../api', () => {
  const entities = [
    {
      id: 'e1',
      name: 'customer',
      primary_keys: ['customer_id'],
      join_keys: ['customer_id'],
      description: 'Customer entity',
      owner: 'data-platform',
      source_of_truth: 'crm',
      lifecycle_status: 'validated',
      created_at: '2026-06-01T00:00:00.000Z',
      updated_at: '2026-06-01T00:00:00.000Z',
    },
  ]
  const relationships = [
    {
      id: 'r1',
      name: 'customer_has_contracts',
      left_entity: 'customer',
      right_entity: 'contract',
      relation_type: 'one_to_many',
      join_keys: [{ left_key: 'customer_id', right_key: 'customer_id' }],
      valid_from: null,
      valid_to: null,
      event_time: 'contract_start_date',
      description: 'One customer can have many contracts',
      owner: 'data-platform',
      lifecycle_status: 'validated',
      created_at: '2026-06-01T00:00:00.000Z',
      updated_at: '2026-06-01T00:00:00.000Z',
    },
  ]

  return {
    invalidateCache: vi.fn(),
    api: {
      entities: {
        list: vi.fn(async () => entities),
        get: vi.fn(async (name: string) => entities.find((row) => row.name === name) ?? entities[0]),
        upsert: vi.fn(async () => entities[0]),
      },
      entityRelationships: {
        list: vi.fn(async () => relationships),
        get: vi.fn(async (name: string) => relationships.find((row) => row.name === name) ?? relationships[0]),
        upsert: vi.fn(async () => relationships[0]),
      },
    },
  }
})

import { Entities } from '../Entities'
import { EntityRelationships } from '../EntityRelationships'

function renderPage(path: string, element: ReactElement) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/entities" element={element} />
        <Route path="/entities/:name" element={element} />
        <Route path="/entity-relationships" element={element} />
        <Route path="/entity-relationships/:name" element={element} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('Entity registry views', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders entities and opens detail', async () => {
    const user = userEvent.setup()
    renderPage('/entities', <Entities />)

    expect(await screen.findByRole('heading', { name: /entities/i, level: 1 })).toBeInTheDocument()
    expect(screen.getByText('customer')).toBeInTheDocument()

    await user.click(screen.getByText('customer'))
    await waitFor(() => {
      expect(screen.getByText('Customer entity')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /open relationships/i })).toBeInTheDocument()
  })

  it('renders relationships and opens detail', async () => {
    const user = userEvent.setup()
    renderPage('/entity-relationships', <EntityRelationships />)

    expect(await screen.findByRole('heading', { name: /relationships/i, level: 1 })).toBeInTheDocument()
    expect(screen.getByText('customer_has_contracts')).toBeInTheDocument()

    await user.click(screen.getByText('customer_has_contracts'))
    await waitFor(() => {
      expect(screen.getByText('One customer can have many contracts')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /open entity/i })).toBeInTheDocument()
  })
})
