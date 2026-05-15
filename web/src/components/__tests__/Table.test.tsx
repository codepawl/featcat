import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DataTable } from '../DataTable'

/**
 * Pins the contract of the shared DataTable abstraction (already used
 * by Features, Groups, GroupDetail; this PR adds Audit as the 4th
 * consumer). Each test maps to a "variant observed in the audit"
 * documented in the DataTable docstring.
 */

interface Row {
  name: string
  count: number
}

const SAMPLE: Row[] = [
  { name: 'beta', count: 5 },
  { name: 'alpha', count: 12 },
  { name: 'gamma', count: 1 },
]

const COLUMNS = [
  { key: 'name', label: 'Name' },
  { key: 'count', label: 'Count' },
]

describe('DataTable', () => {
  it('renders one row per data record with the provided columns', () => {
    render(<DataTable columns={COLUMNS} data={SAMPLE} />)
    expect(screen.getByRole('columnheader', { name: /Name/ })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Count/ })).toBeInTheDocument()
    // Three data rows + 1 header row.
    expect(screen.getAllByRole('row')).toHaveLength(4)
  })

  it('renders the empty state when data is empty', () => {
    render(<DataTable columns={COLUMNS} data={[]} />)
    expect(screen.getByText(/empty|no/i)).toBeInTheDocument()
  })

  it('sorts ascending then descending when a sortable header is clicked', async () => {
    const user = userEvent.setup()
    render(<DataTable columns={COLUMNS} data={SAMPLE} />)

    const countHeader = screen.getByRole('columnheader', { name: /Count/ })
    await user.click(countHeader)
    let cells = screen
      .getAllByRole('row')
      .slice(1)
      .map((r) => within(r).getAllByRole('cell')[1].textContent)
    expect(cells).toEqual(['1', '5', '12'])

    await user.click(countHeader)
    cells = screen
      .getAllByRole('row')
      .slice(1)
      .map((r) => within(r).getAllByRole('cell')[1].textContent)
    expect(cells).toEqual(['12', '5', '1'])
  })

  it('fires onRowClick with the clicked row', async () => {
    const user = userEvent.setup()
    const onRowClick = vi.fn()
    render(<DataTable columns={COLUMNS} data={SAMPLE} onRowClick={onRowClick} />)
    const dataRows = screen.getAllByRole('row').slice(1)
    await user.click(dataRows[0])
    expect(onRowClick).toHaveBeenCalledTimes(1)
    expect(onRowClick).toHaveBeenCalledWith(SAMPLE[0])
  })

  it('honors sortable: false on a column (no sort toggle on click)', async () => {
    const user = userEvent.setup()
    const cols = [
      { key: 'name', label: 'Name' },
      { key: 'count', label: 'Count', sortable: false },
    ]
    render(<DataTable columns={cols} data={SAMPLE} />)
    const countHeader = screen.getByRole('columnheader', { name: /Count/ })
    await user.click(countHeader)
    // Order must stay the original insertion order — no sort applied.
    const cells = screen
      .getAllByRole('row')
      .slice(1)
      .map((r) => within(r).getAllByRole('cell')[0].textContent)
    expect(cells).toEqual(['beta', 'alpha', 'gamma'])
  })

  it('renders custom cell content via column.render', () => {
    const cols = [
      { key: 'name', label: 'Name' },
      {
        key: 'count',
        label: 'Count',
        render: (r: Row) => <span data-testid="count-cell">{r.count} times</span>,
      },
    ]
    render(<DataTable columns={cols} data={SAMPLE} />)
    expect(screen.getAllByTestId('count-cell')).toHaveLength(3)
    expect(screen.getByText('5 times')).toBeInTheDocument()
  })

  it('paginates when rows exceed pageSize', async () => {
    const user = userEvent.setup()
    const many: Row[] = Array.from({ length: 6 }, (_, i) => ({
      name: `row-${i}`,
      count: i,
    }))
    render(<DataTable columns={COLUMNS} data={many} pageSize={3} />)
    // Page 1: 3 rows
    expect(screen.getAllByRole('row').slice(1)).toHaveLength(3)
    expect(screen.getByText('row-0')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /next/i }))
    expect(screen.getByText('row-3')).toBeInTheDocument()
    expect(screen.queryByText('row-0')).not.toBeInTheDocument()
  })
})
