import { test as base } from '@playwright/test'
import { BACKEND_URL } from './constants'
import { createAiMockHelpers, mockAiDefault, type AiMockHelpers } from './mock-ai'
import { clearWriteState, ensureSeeded } from './seed'

export interface E2EFixtures {
  apiUrl: string
  mockAi: AiMockHelpers
}

interface WorkerFixtures {
  seededBackend: void
}

export const test = base.extend<E2EFixtures, WorkerFixtures>({
  seededBackend: [
    async ({}, use) => {
      await ensureSeeded()
      await use()
    },
    { scope: 'worker', auto: true },
  ],

  apiUrl: async ({}, use) => {
    await use(BACKEND_URL)
  },

  mockAi: async ({ page }, use) => {
    await mockAiDefault(page)
    const helpers = createAiMockHelpers(page)
    await use(helpers)
  },

  page: async ({ page }, use) => {
    await clearWriteState()
    await use(page)
  },
})

export { expect } from '@playwright/test'
