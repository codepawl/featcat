import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import {
  ACTIVE_JOB_KEY,
  BatchProgressBanner,
  readActiveJob,
  writeActiveJob,
} from '../../components/BatchProgressBanner'

/**
 * Covers the F5-survival contract of the auto-doc batch progress UI
 * (drift bug #1 in docs/BACKLOG.md): mount with a stored job id, mock the
 * status endpoint to return running state, and assert the progress chip
 * renders with the polled values.
 */
describe('BatchProgressBanner — reload resume', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('round-trips an active job through localStorage', () => {
    writeActiveJob({ jobId: 'abc-123', total: 7 })
    expect(readActiveJob()).toEqual({ jobId: 'abc-123', total: 7 })
    writeActiveJob(null)
    expect(readActiveJob()).toBeNull()
  })

  it('ignores garbage in localStorage rather than crashing', () => {
    window.localStorage.setItem(ACTIVE_JOB_KEY, 'not json {')
    expect(readActiveJob()).toBeNull()
  })

  it('restores the progress banner from localStorage on mount and polls the status endpoint', async () => {
    // Pre-populate the storage key as if the previous tab started a batch
    // before the reload.
    window.localStorage.setItem(
      ACTIVE_JOB_KEY,
      JSON.stringify({ jobId: 'job-xyz', total: 7 }),
    )

    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          job_id: 'job-xyz',
          total: 7,
          completed: 3,
          failed: 0,
          status: 'running',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    const onComplete = vi.fn()
    // Parent has not yet rehydrated → pass job=null and let the banner
    // seed itself from localStorage.
    render(<BatchProgressBanner job={null} onComplete={onComplete} pollMs={20} />)

    const banner = await screen.findByTestId('batch-progress-banner')
    expect(banner).toHaveAttribute('role', 'status')
    await waitFor(() => {
      expect(banner).toHaveTextContent('Generating... (3/7)')
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/docs/generate-batch/job-xyz/status',
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    )
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('clears localStorage and fires onComplete when the backend reports done', async () => {
    window.localStorage.setItem(
      ACTIVE_JOB_KEY,
      JSON.stringify({ jobId: 'job-done', total: 4 }),
    )
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            job_id: 'job-done',
            total: 4,
            completed: 4,
            failed: 0,
            status: 'done',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    const onComplete = vi.fn()
    render(<BatchProgressBanner job={null} onComplete={onComplete} pollMs={20} />)

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
    expect(window.localStorage.getItem(ACTIVE_JOB_KEY)).toBeNull()
  })

  it('drops a stale job id on 404 (server restart) without polling forever', async () => {
    window.localStorage.setItem(
      ACTIVE_JOB_KEY,
      JSON.stringify({ jobId: 'job-stale', total: 2 }),
    )
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: 'Job not found' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    const onComplete = vi.fn()
    render(<BatchProgressBanner job={null} onComplete={onComplete} pollMs={20} />)

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
    expect(window.localStorage.getItem(ACTIVE_JOB_KEY)).toBeNull()
  })
})
