import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { FilterClearLink } from './FilterClearLink'

describe('FilterClearLink', () => {
  it('returns null when show is false', () => {
    const { container } = render(<FilterClearLink show={false} onClick={() => {}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders a button when show is true', () => {
    render(<FilterClearLink show onClick={() => {}} />)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('uses the common namespace default label', () => {
    render(<FilterClearLink show onClick={() => {}} />)
    expect(
      screen.getByRole('button', { name: /Clear all filters|Xóa toàn bộ bộ lọc/ }),
    ).toBeInTheDocument()
  })

  it('honors a custom label', () => {
    render(<FilterClearLink show onClick={() => {}} label="Reset" />)
    expect(screen.getByRole('button', { name: 'Reset' })).toBeInTheDocument()
  })

  it('fires onClick', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<FilterClearLink show onClick={onClick} />)
    await user.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })
})
