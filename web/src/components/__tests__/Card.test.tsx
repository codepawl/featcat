import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Card } from '../Card'

/**
 * Visual fidelity contract for the shared Card panel. Each variant
 * pin matches one of the inline `<div className="bg-[var(--bg-primary)]
 * border ... rounded-xl ...">` patterns that lived in pages before this
 * refactor, so a regression that drops padding / border / header
 * structure fails the test instead of shipping silently.
 */
describe('Card', () => {
  it('renders title and children with default padding', () => {
    render(
      <Card title="Execution History" data-testid="card-default">
        <p>body</p>
      </Card>,
    )
    const card = screen.getByTestId('card-default')
    expect(card).toHaveClass('p-5')
    expect(card).toHaveClass('rounded-xl')
    expect(screen.getByRole('heading', { name: 'Execution History', level: 3 })).toBeInTheDocument()
    expect(screen.getByText('body')).toBeInTheDocument()
  })

  it('renders header actions when supplied', () => {
    render(
      <Card
        title="Drift Table"
        actions={<button>Refresh</button>}
        data-testid="card-with-actions"
      >
        <p>body</p>
      </Card>,
    )
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })

  it('omits the header row when no title and no actions are supplied', () => {
    render(
      <Card data-testid="card-bare">
        <p>just-body</p>
      </Card>,
    )
    // The h3 element should not render at all.
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
    expect(screen.getByText('just-body')).toBeInTheDocument()
  })

  it('respects the padding="none" variant (used to host edge-to-edge tables)', () => {
    render(
      <Card padding="none" data-testid="card-edge">
        <p>flush</p>
      </Card>,
    )
    const card = screen.getByTestId('card-edge')
    expect(card).not.toHaveClass('p-5')
    expect(card).not.toHaveClass('p-3')
  })

  it('respects the padding="compact" variant (used for list-row groupings)', () => {
    render(
      <Card padding="compact" data-testid="card-compact">
        <p>row</p>
      </Card>,
    )
    expect(screen.getByTestId('card-compact')).toHaveClass('p-3')
  })

  it('renders a fully-custom header slot when `header` is supplied', () => {
    render(
      <Card
        header={
          <div data-testid="custom-header">
            <span>Custom-shaped header</span>
          </div>
        }
        data-testid="card-custom-header"
      >
        <p>body</p>
      </Card>,
    )
    expect(screen.getByTestId('custom-header')).toBeInTheDocument()
    // The default title/actions slot must NOT render when `header` overrides.
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
  })

  it('passes className through for layout tweaks like margins', () => {
    render(<Card className="mb-6 flex-1" data-testid="card-classes" />)
    const card = screen.getByTestId('card-classes')
    expect(card).toHaveClass('mb-6')
    expect(card).toHaveClass('flex-1')
  })
})
