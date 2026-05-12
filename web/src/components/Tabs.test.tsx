import { describe, expect, it, vi } from 'vitest'
import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useSearchParams } from 'react-router-dom'
import { Tabs, type TabDefinition } from './Tabs'

type Id = 'overview' | 'history' | 'docs'

const TABS: TabDefinition<Id>[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'history', label: 'History' },
  { id: 'docs', label: 'Docs' },
]

function ControlledTabs({
  initial = 'overview' as Id,
  onChange,
  syncToUrl,
}: {
  initial?: Id
  onChange?: (id: Id) => void
  syncToUrl?: boolean | { param: string }
}) {
  const [value, setValue] = useState<Id>(initial)
  return (
    <Tabs<Id>
      tabs={TABS}
      value={value}
      onChange={(id) => {
        setValue(id)
        onChange?.(id)
      }}
      syncToUrl={syncToUrl}
    />
  )
}

function withRouter(ui: React.ReactNode, initialEntries: string[] = ['/']) {
  return render(<MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>)
}

describe('Tabs', () => {
  it('renders one tab button per definition', () => {
    withRouter(<ControlledTabs />)
    expect(screen.getByRole('tab', { name: /Overview/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /History/ })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Docs/ })).toBeInTheDocument()
  })

  it('marks the active tab via aria-selected and brand color', () => {
    withRouter(<ControlledTabs initial="history" />)
    const history = screen.getByRole('tab', { name: /History/ })
    const overview = screen.getByRole('tab', { name: /Overview/ })
    expect(history).toHaveAttribute('aria-selected', 'true')
    expect(history).toHaveClass('border-brand')
    expect(overview).toHaveAttribute('aria-selected', 'false')
  })

  it('changes the active tab on click', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    withRouter(<ControlledTabs onChange={onChange} />)
    await user.click(screen.getByRole('tab', { name: /Docs/ }))
    expect(onChange).toHaveBeenCalledWith('docs')
    expect(screen.getByRole('tab', { name: /Docs/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('cycles tabs with ArrowRight / ArrowLeft', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    withRouter(<ControlledTabs onChange={onChange} />)
    const overview = screen.getByRole('tab', { name: /Overview/ })
    overview.focus()
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith('history')
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith('docs')
    // wraps from last → first
    await user.keyboard('{ArrowRight}')
    expect(onChange).toHaveBeenLastCalledWith('overview')
    // ArrowLeft wraps backwards
    await user.keyboard('{ArrowLeft}')
    expect(onChange).toHaveBeenLastCalledWith('docs')
  })

  it('Home / End jump to first / last tab', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    withRouter(<ControlledTabs initial="history" onChange={onChange} />)
    screen.getByRole('tab', { name: /History/ }).focus()
    await user.keyboard('{End}')
    expect(onChange).toHaveBeenLastCalledWith('docs')
    await user.keyboard('{Home}')
    expect(onChange).toHaveBeenLastCalledWith('overview')
  })

  it('syncToUrl=true restores from ?tab on mount and writes on change', async () => {
    const user = userEvent.setup()
    let capturedParams = ''
    function ParamCapture() {
      const [sp] = useSearchParams()
      capturedParams = sp.toString()
      return null
    }
    withRouter(
      <>
        <ControlledTabs syncToUrl />
        <ParamCapture />
      </>,
      ['/page?tab=docs'],
    )
    // restored: docs is active immediately
    expect(screen.getByRole('tab', { name: /Docs/ })).toHaveAttribute('aria-selected', 'true')
    // change writes back
    await user.click(screen.getByRole('tab', { name: /History/ }))
    expect(capturedParams).toContain('tab=history')
  })

  it('syncToUrl with custom param name', async () => {
    const user = userEvent.setup()
    let capturedParams = ''
    function ParamCapture() {
      const [sp] = useSearchParams()
      capturedParams = sp.toString()
      return null
    }
    withRouter(
      <>
        <ControlledTabs syncToUrl={{ param: 'view' }} />
        <ParamCapture />
      </>,
    )
    await user.click(screen.getByRole('tab', { name: /Docs/ }))
    expect(capturedParams).toContain('view=docs')
  })
})
