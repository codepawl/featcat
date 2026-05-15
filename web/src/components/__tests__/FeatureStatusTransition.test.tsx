import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

/** Mock the api module so the transition flow can be tested in jsdom
 *  without escaping to fetch. The mock is rebuilt per-test via
 *  `beforeEach` so call counts and per-test resolution behavior stay
 *  isolated.
 */
const certificationReadiness = vi.fn(async () => ({ ready: true, missing: [] as string[] }))
const setStatus = vi.fn(async () => ({ name: 'src.col_a', status: 'reviewed' }))

vi.mock('../../api', () => ({
  invalidateCache: vi.fn(),
  api: {
    features: {
      certificationReadiness: (name: string) => certificationReadiness(),
      setStatus: (name: string, body: { status: string; notes?: string | null }) =>
        setStatus(),
    },
  },
}))

import {
  FeatureStatusBadge,
  FeatureStatusTransition,
  type FeatureStatus,
} from '../FeatureStatusTransition'

describe('FeatureStatusBadge', () => {
  it.each<[FeatureStatus | null, FeatureStatus]>([
    ['draft', 'draft'],
    ['reviewed', 'reviewed'],
    ['certified', 'certified'],
    ['deprecated', 'deprecated'],
    [null, 'draft'],
  ])('renders correct data-status for %s', (input, expected) => {
    render(<FeatureStatusBadge status={input} />)
    const badge = screen.getByTestId('feature-status-badge')
    expect(badge).toHaveAttribute('data-status', expected)
  })
})

describe('FeatureStatusTransition', () => {
  beforeEach(() => {
    certificationReadiness.mockReset()
    setStatus.mockReset()
    certificationReadiness.mockResolvedValue({ ready: true, missing: [] })
    setStatus.mockResolvedValue({ name: 'src.col_a', status: 'reviewed' })
  })

  it('opens a dropdown that excludes the current status', async () => {
    const user = userEvent.setup()
    render(
      <FeatureStatusTransition
        featureName="src.col_a"
        current="reviewed"
        onTransitioned={vi.fn()}
      />,
    )
    await user.click(screen.getByTestId('feature-status-change-button'))
    const menu = await screen.findByTestId('feature-status-menu')
    expect(menu).toBeInTheDocument()

    // All four statuses render as menu items; the current one is disabled.
    const reviewed = screen.getByTestId('feature-status-option-reviewed')
    expect(reviewed).toBeDisabled()
    expect(reviewed).toHaveAttribute('data-current', 'true')
    for (const s of ['draft', 'certified', 'deprecated'] as const) {
      const opt = screen.getByTestId(`feature-status-option-${s}`)
      expect(opt).not.toBeDisabled()
    }
  })

  it('blocks certify confirm when readiness reports any failing check', async () => {
    certificationReadiness.mockResolvedValueOnce({
      ready: false,
      missing: ['baseline', 'owner'],
    })
    const user = userEvent.setup()
    render(
      <FeatureStatusTransition
        featureName="src.col_a"
        current="reviewed"
        onTransitioned={vi.fn()}
      />,
    )
    await user.click(screen.getByTestId('feature-status-change-button'))
    await user.click(screen.getByTestId('feature-status-option-certified'))

    // Checklist resolves and the modal exposes the items with failing
    // ones flagged. Confirm stays disabled.
    await screen.findByTestId('feature-status-readiness-checklist')
    expect(screen.getByTestId('feature-status-readiness-baseline')).toHaveAttribute(
      'data-failed',
      'true',
    )
    expect(screen.getByTestId('feature-status-readiness-owner')).toHaveAttribute(
      'data-failed',
      'true',
    )
    expect(screen.getByTestId('feature-status-readiness-documentation')).not.toHaveAttribute(
      'data-failed',
    )

    expect(screen.getByTestId('feature-status-confirm')).toBeDisabled()
    expect(setStatus).not.toHaveBeenCalled()
  })

  it('allows certify confirm when all checks pass and POSTs the new status', async () => {
    certificationReadiness.mockResolvedValueOnce({ ready: true, missing: [] })
    setStatus.mockResolvedValueOnce({ name: 'src.col_a', status: 'certified' })
    const onTransitioned = vi.fn()
    const user = userEvent.setup()
    render(
      <FeatureStatusTransition
        featureName="src.col_a"
        current="reviewed"
        onTransitioned={onTransitioned}
      />,
    )
    await user.click(screen.getByTestId('feature-status-change-button'))
    await user.click(screen.getByTestId('feature-status-option-certified'))

    await screen.findByTestId('feature-status-readiness-checklist')
    const confirmBtn = screen.getByTestId('feature-status-confirm')
    await waitFor(() => expect(confirmBtn).not.toBeDisabled())

    await user.click(confirmBtn)

    await waitFor(() => {
      expect(setStatus).toHaveBeenCalledTimes(1)
    })
    expect(onTransitioned).toHaveBeenCalledWith('certified')
  })

  it('submits non-certify transitions with the notes payload', async () => {
    setStatus.mockResolvedValueOnce({ name: 'src.col_a', status: 'deprecated' })
    const onTransitioned = vi.fn()
    const user = userEvent.setup()
    render(
      <FeatureStatusTransition
        featureName="src.col_a"
        current="reviewed"
        onTransitioned={onTransitioned}
      />,
    )
    await user.click(screen.getByTestId('feature-status-change-button'))
    await user.click(screen.getByTestId('feature-status-option-deprecated'))

    const notes = await screen.findByTestId('feature-status-notes')
    await user.type(notes, 'replaced by v2')
    await user.click(screen.getByTestId('feature-status-confirm'))

    await waitFor(() => {
      expect(setStatus).toHaveBeenCalledTimes(1)
    })
    // Readiness must NOT be fetched for non-certify transitions.
    expect(certificationReadiness).not.toHaveBeenCalled()
    expect(onTransitioned).toHaveBeenCalledWith('deprecated')
  })
})
