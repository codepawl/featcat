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

  it('starting a new batch overwrites a stale job id from a prior run', async () => {
    // Simulate the user reloading after a partial run, then immediately
    // kicking off a fresh batch. The banner must follow the *new* job
    // (passed via the `job` prop), not keep polling the stale id that the
    // previous tab left in localStorage.
    window.localStorage.setItem(
      ACTIVE_JOB_KEY,
      JSON.stringify({ jobId: 'stale-1', total: 1 }),
    )

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      // Only the new job id should be polled. If the banner ever hits
      // /generate-batch/stale-1/status we fail the test by responding 500.
      if (url.includes('stale-1')) {
        return new Response('stale-id leaked into poll', { status: 500 })
      }
      return new Response(
        JSON.stringify({
          job_id: 'fresh-2',
          total: 5,
          completed: 2,
          failed: 0,
          status: 'running',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )
    })
    vi.stubGlobal('fetch', fetchMock)

    const onComplete = vi.fn()
    render(
      <BatchProgressBanner
        job={{ jobId: 'fresh-2', total: 5 }}
        onComplete={onComplete}
        pollMs={20}
      />,
    )

    const banner = await screen.findByTestId('batch-progress-banner')
    await waitFor(() => {
      expect(banner).toHaveTextContent('Generating... (2/5)')
    })

    // Persisted entry should now reflect the new job, not the stale one.
    const stored = window.localStorage.getItem(ACTIVE_JOB_KEY)
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored ?? 'null') as { jobId: string; total: number }
    expect(parsed.jobId).toBe('fresh-2')
    expect(parsed.total).toBe(5)

    // None of the polls hit the stale id.
    const calls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(calls.every((u) => !u.includes('stale-1'))).toBe(true)
  })
})
