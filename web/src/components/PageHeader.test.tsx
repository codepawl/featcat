import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  it('renders the title as a level-1 heading', () => {
    render(<PageHeader title="Sources" />)
    expect(screen.getByRole('heading', { level: 1, name: 'Sources' })).toBeInTheDocument()
  })

  it('omits the subtitle node when not provided', () => {
    const { container } = render(<PageHeader title="Sources" />)
    expect(container.querySelector('p')).toBeNull()
  })

  it('renders the subtitle when provided', () => {
    render(<PageHeader title="Audit" subtitle="Recent feature changes" />)
    expect(screen.getByText('Recent feature changes')).toBeInTheDocument()
  })

  it('renders actions in their slot', () => {
    render(<PageHeader title="Sources" actions={<button>Add</button>} />)
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()
  })

  it('applies text-xl when size=compact, text-2xl by default', () => {
    const { rerender } = render(<PageHeader title="X" />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveClass('text-2xl')
    rerender(<PageHeader title="X" size="compact" />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveClass('text-xl')
  })
})
