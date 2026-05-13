import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Database } from 'lucide-react'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders the title', () => {
    render(<EmptyState title="No sources yet" />)
    expect(screen.getByText('No sources yet')).toBeInTheDocument()
  })

  it('omits the description when not provided', () => {
    render(<EmptyState title="Empty" />)
    expect(screen.queryByText(/./, { selector: '.text-xs' })).toBeNull()
  })

  it('renders the description when provided', () => {
    render(<EmptyState title="Empty" description="Try adjusting your filters" />)
    expect(screen.getByText('Try adjusting your filters')).toBeInTheDocument()
  })

  it('renders the default empty icon (Inbox) when no override given', () => {
    const { container } = render(<EmptyState title="Empty" />)
    // The default icon should sit inside the wrapper; presence of an SVG with
    // the muted tertiary tint is enough — testing the exact lucide name is brittle.
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(svg).toHaveClass('text-[var(--text-tertiary)]')
  })

  it('uses an override icon when provided', () => {
    const { container } = render(<EmptyState title="Empty" icon={Database} />)
    const svg = container.querySelector('svg')
    expect(svg).not.toBeNull()
  })

  it('error variant tints the icon with the danger color', () => {
    const { container } = render(<EmptyState variant="error" title="Failed to load" />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveClass('text-[var(--danger)]')
  })

  it('renders the CTA button and calls onClick', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<EmptyState title="Empty" action={{ label: 'Add first source', onClick }} />)
    const btn = screen.getByRole('button', { name: 'Add first source' })
    await user.click(btn)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('bordered surface adds the dashed border class', () => {
    const { container } = render(<EmptyState title="X" surface="bordered" />)
    expect(container.firstChild).toHaveClass('border-dashed')
  })
})
