import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SegmentedBar } from './SegmentedBar'

describe('SegmentedBar', () => {
  it('renders one element per non-zero segment by default', () => {
    const { container } = render(
      <SegmentedBar
        ariaLabel="Grade distribution"
        segments={[
          { value: 10, color: 'bg-green-500' },
          { value: 0, color: 'bg-red-500' },
          { value: 5, color: 'bg-amber-500' },
        ]}
      />,
    )
    // Children of the track that have width style
    const track = container.firstChild as HTMLElement
    expect(track.children.length).toBe(2)
  })

  it('includes zero segments when showZero is true', () => {
    const { container } = render(
      <SegmentedBar
        ariaLabel="x"
        showZero
        segments={[
          { value: 1, color: 'bg-green-500' },
          { value: 0, color: 'bg-red-500' },
        ]}
      />,
    )
    const track = container.firstChild as HTMLElement
    expect(track.children.length).toBe(2)
  })

  it('computes segment widths as percentages of total', () => {
    const { container } = render(
      <SegmentedBar
        ariaLabel="x"
        segments={[
          { value: 30, color: 'bg-a' },
          { value: 70, color: 'bg-b' },
        ]}
      />,
    )
    const segs = (container.firstChild as HTMLElement).children
    expect((segs[0] as HTMLElement).style.width).toBe('30%')
    expect((segs[1] as HTMLElement).style.width).toBe('70%')
  })

  it('renders clickable segments as buttons and fires onClick', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(
      <SegmentedBar
        ariaLabel="x"
        segments={[
          { value: 5, color: 'bg-a', label: 'Active', onClick },
          { value: 5, color: 'bg-b' },
        ]}
      />,
    )
    const btn = screen.getByRole('button', { name: 'Active' })
    await user.click(btn)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('exposes the ariaLabel on the track container', () => {
    render(
      <SegmentedBar
        ariaLabel="Health grades"
        segments={[{ value: 1, color: 'bg-a' }]}
      />,
    )
    expect(screen.getByRole('img', { name: 'Health grades' })).toBeInTheDocument()
  })
})
