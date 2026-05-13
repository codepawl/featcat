import { describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Alert } from './Alert'

describe('Alert', () => {
  it('renders the message inside a role=alert region', () => {
    render(<Alert severity="info" message="Heads up" />)
    expect(screen.getByRole('alert')).toHaveTextContent('Heads up')
  })

  it('applies the danger color tokens for danger severity', () => {
    render(<Alert severity="danger" message="Bad" />)
    expect(screen.getByRole('alert')).toHaveClass('text-[var(--danger)]')
  })

  it('omits the icon when icon=false', () => {
    const { container } = render(<Alert severity="info" message="x" icon={false} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('does not render a dismiss button by default', () => {
    render(<Alert severity="info" message="x" />)
    expect(screen.queryByRole('button')).toBeNull()
  })

  it('uncontrolled: clicking × hides the alert and fires onDismiss', async () => {
    const user = userEvent.setup()
    const onDismiss = vi.fn()
    render(<Alert severity="warning" message="warn" dismissible onDismiss={onDismiss} />)
    await user.click(screen.getByRole('button', { name: /Dismiss|Đóng/ }))
    expect(onDismiss).toHaveBeenCalledOnce()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('controlled: parent visibility persists until parent clears open', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    function ParentFixed() {
      // The parent ignores onOpenChange — visibility stays true.
      return (
        <Alert
          severity="danger"
          message="err"
          dismissible
          open
          onOpenChange={onOpenChange}
        />
      )
    }
    render(<ParentFixed />)
    await user.click(screen.getByRole('button', { name: /Dismiss|Đóng/ }))
    // onOpenChange was called even though we ignore it
    expect(onOpenChange).toHaveBeenCalledWith(false)
    // …and because parent never flipped `open` to false, the alert stays visible
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('controlled: parent that respects onOpenChange does hide the alert', async () => {
    const user = userEvent.setup()
    function ParentReactive() {
      const [open, setOpen] = useState(true)
      return (
        <Alert
          severity="danger"
          message="err"
          dismissible
          open={open}
          onOpenChange={setOpen}
        />
      )
    }
    render(<ParentReactive />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Dismiss|Đóng/ }))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
