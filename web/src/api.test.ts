import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, AUTH_TOKEN_STORAGE_KEY, clearAuthToken, getAuthToken, setAuthToken } from './api'

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response
}

describe('api.online materialization schedule actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    clearAuthToken()
  })

  it('updateMaterializationSchedule sends PATCH with enabled=true', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'sched-1', enabled: true }))
    vi.stubGlobal('fetch', fetchMock)

    await api.online.updateMaterializationSchedule('sched-1', { enabled: true })

    expect(fetchMock).toHaveBeenCalledWith('/api/online/materialization-schedules/sched-1', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
      body: JSON.stringify({ enabled: true }),
      credentials: 'include',
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
      credentials: 'include',
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
      credentials: 'include',
    })
  })

  it('attaches the stored bearer token to API requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      authenticated: true,
      required: true,
      user: {
        email: 'admin@example.com',
        role: 'admin',
        groups: [],
        auth_type: 'token',
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    setAuthToken('  test-token  ')
    expect(getAuthToken()).toBe('test-token')

    await api.auth.me()

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me', {
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer test-token',
      },
      credentials: 'include',
    })
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBe('test-token')
  })

  it('posts company access requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      id: 'req-1',
      email: 'alice@fpt.com',
      display_name: 'Alice',
      message: 'Need dashboard access',
      status: 'pending',
      created_at: '2026-06-09T00:00:00Z',
      updated_at: '2026-06-09T00:00:00Z',
    }))
    vi.stubGlobal('fetch', fetchMock)

    await api.auth.requestAccess({
      email: 'alice@fpt.com',
      display_name: 'Alice',
      message: 'Need dashboard access',
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/request-access', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({
        email: 'alice@fpt.com',
        display_name: 'Alice',
        message: 'Need dashboard access',
      }),
      credentials: 'include',
    })
  })
})
