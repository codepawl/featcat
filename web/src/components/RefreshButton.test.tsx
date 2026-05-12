import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RefreshButton } from './RefreshButton'

describe('RefreshButton', () => {
  it('uses the common.actions.refresh label by default', () => {
    render(<RefreshButton onClick={() => {}} loading={false} />)
    expect(screen.getByRole('button', { name: /Refresh|Làm mới/ })).toBeInTheDocument()
  })

  it('honors a custom label', () => {
    render(<RefreshButton onClick={() => {}} loading={false} label="Reload" />)
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  })

  it('calls onClick when not loading', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<RefreshButton onClick={onClick} loading={false} />)
    await user.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('disables itself while loading', () => {
    render(<RefreshButton onClick={() => {}} loading />)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('spins the icon while loading', () => {
    const { container } = render(<RefreshButton onClick={() => {}} loading />)
    const icon = container.querySelector('svg')
    expect(icon).toHaveClass('animate-spin')
  })

  it('does not spin when idle', () => {
    const { container } = render(<RefreshButton onClick={() => {}} loading={false} />)
    const icon = container.querySelector('svg')
    expect(icon).not.toHaveClass('animate-spin')
  })
})
