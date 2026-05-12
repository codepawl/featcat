import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FilterCountChip } from './FilterCountChip'

describe('FilterCountChip', () => {
  it('renders the count alone when no label', () => {
    render(<FilterCountChip count={42} />)
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders count + label with a space separator', () => {
    render(<FilterCountChip count={3} label="features" />)
    expect(screen.getByText(/3 features/)).toBeInTheDocument()
  })

  it('handles zero count', () => {
    render(<FilterCountChip count={0} label="rows" />)
    expect(screen.getByText(/0 rows/)).toBeInTheDocument()
  })
})
