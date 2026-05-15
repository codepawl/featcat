import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Checkbox } from '../Checkbox'

/**
 * Keyboard accessibility is the core contract here — the goal explicitly
 * calls out "space toggles checkbox". Using the native input under the
 * hood means we get that, tab focus, and screen-reader semantics for
 * free. Tests pin the contract so a future "let's roll our own div with
 * role=checkbox" refactor fails loud.
 */

describe('Checkbox', () => {
  it('renders with the label and reflects checked state', () => {
    render(<Checkbox checked label="Recursive" onCheckedChange={() => {}} />)
    const input = screen.getByRole('checkbox', { name: /recursive/i })
    expect(input).toBeChecked()
  })

  it('fires onCheckedChange with the new boolean on mouse click', async () => {
    const onCheckedChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Checkbox checked={false} label="Dry run" onCheckedChange={onCheckedChange} />,
    )
    await user.click(screen.getByRole('checkbox'))
    expect(onCheckedChange).toHaveBeenCalledWith(true)
  })

  it('toggles via the space key when focused', async () => {
    const onCheckedChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Checkbox checked={false} label="Recursive" onCheckedChange={onCheckedChange} />,
    )
    const cb = screen.getByRole('checkbox')
    cb.focus()
    await user.keyboard(' ')
    expect(onCheckedChange).toHaveBeenCalledWith(true)
  })

  it('does not fire onCheckedChange when disabled', async () => {
    const onCheckedChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Checkbox
        checked={false}
        label="Disabled"
        disabled
        onCheckedChange={onCheckedChange}
      />,
    )
    await user.click(screen.getByRole('checkbox'))
    expect(onCheckedChange).not.toHaveBeenCalled()
  })

  it('renders description text below the label', () => {
    render(
      <Checkbox
        checked
        label="Regenerate existing"
        description="Overwrites prior docs"
        onCheckedChange={() => {}}
      />,
    )
    expect(screen.getByText('Overwrites prior docs')).toBeInTheDocument()
  })

  it('sets the underlying input to indeterminate when prop is true', () => {
    render(
      <Checkbox checked={false} indeterminate onCheckedChange={() => {}} />,
    )
    const input = screen.getByRole('checkbox') as HTMLInputElement
    expect(input.indeterminate).toBe(true)
  })

  it('exposes aria-invalid when error prop is set', () => {
    render(
      <Checkbox checked={false} label="X" error onCheckedChange={() => {}} />,
    )
    expect(screen.getByRole('checkbox')).toHaveAttribute('aria-invalid', 'true')
  })
})
