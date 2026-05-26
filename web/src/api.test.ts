import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}

describe('api.online materialization schedule actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('updateMaterializationSchedule sends PATCH with enabled=true', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'sched-1', enabled: true }))
    vi.stubGlobal('fetch', fetchMock)

    await api.online.updateMaterializationSchedule('sched-1', { enabled: true })

    expect(fetchMock).toHaveBeenCalledWith('/api/online/materialization-schedules/sched-1', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
      body: JSON.stringify({ enabled: true }),
    })
  })

  it('updateMaterializationSchedule sends PATCH with enabled=false', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'sched-1', enabled: false }))
    vi.stubGlobal('fetch', fetchMock)

    await api.online.updateMaterializationSchedule('sched-1', { enabled: false })

    expect(fetchMock).toHaveBeenCalledWith('/api/online/materialization-schedules/sched-1', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
      body: JSON.stringify({ enabled: false }),
    })
  })

  it('runMaterializationSchedule sends POST to the run endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ schedule_id: 'sched/1', requested: 2, written: 2 }))
    vi.stubGlobal('fetch', fetchMock)

    await api.online.runMaterializationSchedule('sched/1', { runner_id: 'runner-1' })

    expect(fetchMock).toHaveBeenCalledWith('/api/online/materialization-schedules/sched%2F1/run', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({ runner_id: 'runner-1' }),
    })
  })
})
