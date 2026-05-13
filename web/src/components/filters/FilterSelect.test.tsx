import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterSelect } from './FilterSelect'

type Severity = 'all' | 'critical' | 'warning'

describe('FilterSelect', () => {
  const options = [
    { value: 'all' as Severity, label: 'All' },
    { value: 'critical' as Severity, label: 'Critical' },
    { value: 'warning' as Severity, label: 'Warning' },
  ]

  it('renders all options with the given labels', () => {
    render(<FilterSelect<Severity> value="all" onChange={() => {}} options={options} />)
    expect(screen.getByRole('option', { name: 'All' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Critical' })).toBeInTheDocument()
  })

  it('reflects the controlled value', () => {
    render(<FilterSelect<Severity> value="critical" onChange={() => {}} options={options} />)
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('critical')
  })

  it('calls onChange with the typed value when the user picks an option', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn<(v: Severity) => void>()
    render(<FilterSelect<Severity> value="all" onChange={onChange} options={options} />)
    await user.selectOptions(screen.getByRole('combobox'), 'warning')
    expect(onChange).toHaveBeenCalledWith('warning')
  })

  it('exposes the ariaLabel for assistive tech', () => {
    render(
      <FilterSelect<Severity>
        value="all"
        onChange={() => {}}
        options={options}
        ariaLabel="Severity filter"
      />,
    )
    expect(screen.getByRole('combobox', { name: 'Severity filter' })).toBeInTheDocument()
  })
})
