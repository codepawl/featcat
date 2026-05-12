import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialog } from './ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders title, message, warning', () => {
    render(
      <ConfirmDialog
        open
        onClose={() => {}}
        title="Delete source"
        message={<span>5 features will be removed.</span>}
        warning="This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {}}
      />,
    )
    expect(screen.getByText('Delete source')).toBeInTheDocument()
    expect(screen.getByText('5 features will be removed.')).toBeInTheDocument()
    expect(screen.getByText('This cannot be undone.')).toBeInTheDocument()
  })

  it('calls onConfirm on confirm click', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        onClose={() => {}}
        title="t"
        confirmLabel="Delete"
        onConfirm={onConfirm}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onClose on cancel click', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <ConfirmDialog
        open
        onClose={onClose}
        title="t"
        confirmLabel="Delete"
        onConfirm={() => {}}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Cancel|Hủy/ }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('swaps label and disables both buttons while onConfirm is pending', async () => {
    const user = userEvent.setup()
    let resolve!: () => void
    const onConfirm = vi.fn(() => new Promise<void>((r) => { resolve = r }))
    render(
      <ConfirmDialog
        open
        onClose={() => {}}
        title="t"
        confirmLabel="Delete"
        pendingLabel="Deleting…"
        onConfirm={onConfirm}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Cancel|Hủy/ })).toBeDisabled()
    resolve()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Delete' })).toBeEnabled()
    })
  })

  it('requireTextMatch: confirm disabled until input matches exactly', async () => {
    const user = userEvent.setup()
    render(
      <ConfirmDialog
        open
        onClose={() => {}}
        title="t"
        confirmLabel="Delete"
        requireTextMatch={{ value: 'my_source', label: 'Type the source name' }}
        onConfirm={() => {}}
      />,
    )
    const confirm = screen.getByRole('button', { name: 'Delete' })
    expect(confirm).toBeDisabled()
    const input = screen.getByLabelText('Type the source name')
    await user.type(input, 'wrong')
    expect(confirm).toBeDisabled()
    await user.clear(input)
    await user.type(input, 'my_source')
    expect(confirm).toBeEnabled()
  })

  it('requireCheckbox: confirm disabled until checked', async () => {
    const user = userEvent.setup()
    render(
      <ConfirmDialog
        open
        onClose={() => {}}
        title="t"
        confirmLabel="Delete"
        requireCheckbox="I understand"
        onConfirm={() => {}}
      />,
    )
    const confirm = screen.getByRole('button', { name: 'Delete' })
    expect(confirm).toBeDisabled()
    await user.click(screen.getByLabelText('I understand'))
    expect(confirm).toBeEnabled()
  })

  it('severity changes the confirm button background', () => {
    const { rerender } = render(
      <ConfirmDialog open onClose={() => {}} title="t" confirmLabel="X" severity="destructive" onConfirm={() => {}} />,
    )
    expect(screen.getByRole('button', { name: 'X' })).toHaveClass('bg-[var(--danger)]')
    rerender(
      <ConfirmDialog open onClose={() => {}} title="t" confirmLabel="X" severity="warning" onConfirm={() => {}} />,
    )
    expect(screen.getByRole('button', { name: 'X' })).toHaveClass('bg-[var(--warning)]')
  })
})
