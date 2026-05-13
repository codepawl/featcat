import type { Page, Route } from '@playwright/test'
import type { ChatEvent } from './types'

export interface AiMockHelpers {
  mockChat: (events: ChatEvent[]) => Promise<void>
  mockSuggestFeatures: (specs: string[]) => Promise<void>
  mockGenerateDocsBatch: (jobId: string) => Promise<void>
  mockBatchStatus: (jobId: string, payload: BatchStatusPayload) => Promise<void>
  callCount: (urlPattern: string) => number
}

export interface BatchStatusPayload {
  status: 'pending' | 'running' | 'success' | 'partial' | 'error'
  total: number
  processed: number
  succeeded: number
  failed: number
  results?: Array<{ feature_name: string; status: string }>
}

const callTracker = new WeakMap<Page, Map<string, number>>()

function bumpCount(page: Page, key: string): void {
  let map = callTracker.get(page)
  if (!map) {
    map = new Map()
    callTracker.set(page, map)
  }
  map.set(key, (map.get(key) ?? 0) + 1)
}

function buildSseFrame(events: ChatEvent[]): string {
  const frames = events.map((event) => `event: message\ndata: ${JSON.stringify(event)}\n\n`)
  return frames.join('')
}

export async function mockAiDefault(page: Page): Promise<void> {
  await page.route('**/api/ai/**', async (route: Route) => {
    bumpCount(page, '/api/ai')
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'AI mocked: route not overridden in this test' }),
    })
  })
  await page.route('**/api/docs/generate**', async (route: Route) => {
    bumpCount(page, '/api/docs/generate')
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'AI mocked: route not overridden in this test' }),
    })
  })
}

export function createAiMockHelpers(page: Page): AiMockHelpers {
  return {
    async mockChat(events: ChatEvent[]) {
      await page.route('**/api/ai/chat', async (route: Route) => {
        bumpCount(page, '/api/ai/chat')
        await route.fulfill({
          status: 200,
          headers: {
            'content-type': 'text/event-stream',
            'cache-control': 'no-cache',
            'x-session-id': 'e2e-mock-session',
          },
          body: buildSseFrame(events),
        })
      })
    },

    async mockSuggestFeatures(specs: string[]) {
      await page.route('**/api/ai/discover', async (route: Route) => {
        bumpCount(page, '/api/ai/discover')
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            existing: specs.map((spec) => ({ name: spec, score: 0.9 })),
            suggestions: [],
            interpretation: 'Mocked suggestion',
          }),
        })
      })
    },

    async mockGenerateDocsBatch(jobId: string) {
      await page.route('**/api/docs/generate-batch', async (route: Route) => {
        bumpCount(page, '/api/docs/generate-batch')
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ job_id: jobId, status: 'pending' }),
        })
      })
    },

    async mockBatchStatus(jobId: string, payload: BatchStatusPayload) {
      await page.route(`**/api/docs/generate-batch/${jobId}/status`, async (route: Route) => {
        bumpCount(page, `/api/docs/generate-batch/${jobId}/status`)
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(payload),
        })
      })
    },

    callCount(urlPattern: string): number {
      return callTracker.get(page)?.get(urlPattern) ?? 0
    },
  }
}
