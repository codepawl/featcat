import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FloatingPanel } from '../FloatingPanel'

/**
 * Pins the contract that powers the project's UI convention "all detail
 * views use FloatingPanel" (see CLAUDE.md > UI conventions). Failure
 * modes that would silently break the contract:
 *   - close button doesn't fire onClose
 *   - ESC doesn't fire onClose
 *   - size prop doesn't change the max-width class
 *   - footer / subtitle slots don't render
 */

describe('FloatingPanel', () => {
  it('renders nothing when closed', () => {
    render(
      <FloatingPanel open={false} onClose={() => {}} title="Hidden">
        body
      </FloatingPanel>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders title, subtitle, and body when open', () => {
    render(
      <FloatingPanel open onClose={() => {}} title="Feature detail" subtitle="src.col_a">
        <p>body-content</p>
      </FloatingPanel>,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Feature detail', level: 2 })).toBeInTheDocument()
    expect(screen.getByText('src.col_a')).toBeInTheDocument()
    expect(screen.getByText('body-content')).toBeInTheDocument()
  })

  it('renders the footer slot at the bottom', () => {
    render(
      <FloatingPanel
        open
        onClose={() => {}}
        title="With footer"
        footer={<button>Save</button>}
      >
        body
      </FloatingPanel>,
    )
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('omits the footer DOM when no footer prop is passed', () => {
    render(
      <FloatingPanel open onClose={() => {}} title="No footer">
        body
      </FloatingPanel>,
    )
    // The footer wrapper carries a `border-t` class; absence means the slot
    // didn't render.
    const dialog = screen.getByRole('dialog')
    expect(dialog.querySelector('.border-t')).toBeNull()
  })

  it('fires onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <FloatingPanel open onClose={onClose} title="Close me">
        body
      </FloatingPanel>,
    )
    await user.click(screen.getByTestId('floating-panel-close'))
    // The component animates close over ~150ms before firing onClose.
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('fires onClose on Escape key', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(
      <FloatingPanel open onClose={onClose} title="ESC me">
        body
      </FloatingPanel>,
    )
    await user.keyboard('{Escape}')
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('applies the large size class when size="large"', () => {
    render(
      <FloatingPanel open onClose={() => {}} title="Large" size="large" data-testid="fp-large">
        body
      </FloatingPanel>,
    )
    expect(screen.getByTestId('fp-large')).toHaveClass('max-w-3xl')
  })

  it('applies the medium size class by default', () => {
    render(
      <FloatingPanel open onClose={() => {}} title="Medium" data-testid="fp-medium">
        body
      </FloatingPanel>,
    )
    expect(screen.getByTestId('fp-medium')).toHaveClass('max-w-2xl')
  })

  it('renders headerActions next to the close button', () => {
    render(
      <FloatingPanel
        open
        onClose={() => {}}
        title="With header actions"
        headerActions={<button>Pin</button>}
      >
        body
      </FloatingPanel>,
    )
    expect(screen.getByRole('button', { name: 'Pin' })).toBeInTheDocument()
  })
})
