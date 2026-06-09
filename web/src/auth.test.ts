import { describe, expect, it } from 'vitest'
import { canDelete, canWrite } from './auth'

describe('auth helpers', () => {
  it('treats anonymous users as writable in public mode', () => {
    expect(canWrite(null)).toBe(true)
  })

  it('still keeps delete access restricted without a signed-in admin', () => {
    expect(canDelete(null)).toBe(false)
  })
})
