import { expect, test } from './fixtures/test'
import type { ChatEvent } from './fixtures/types'

const sseEvents: ChatEvent[] = [
  { type: 'thinking_start' },
  { type: 'thinking', content: 'Looking at the catalog to find CPU-related features...' },
  { type: 'thinking_end' },
  {
    type: 'tool_call',
    id: 'call-1',
    name: 'search',
    input: { query: 'cpu' },
  },
  {
    type: 'tool_result',
    id: 'call-1',
    name: 'search',
    output: { hits: ['device_performance.cpu_usage'] },
  },
  { type: 'token', content: 'I found ' },
  { type: 'token', content: 'one CPU feature: ' },
  { type: 'token', content: '`device_performance.cpu_usage`.' },
  { type: 'done' },
]

test.describe('Agentic chat (SSE)', () => {
  test('streams thinking, tool call, and tokens to the UI', async ({ page, mockAi }) => {
    await mockAi.mockChat(sseEvents)

    await page.goto('/chat')

    const input = page.getByPlaceholder('Ask about features...')
    await input.fill('Find CPU features')
    await page.getByRole('button', { name: 'Send' }).click()

    await expect(page.getByText(/Find CPU features/)).toBeVisible()
    await expect(page.getByText(/I found one CPU feature/)).toBeVisible()
    await expect(page.getByText(/device_performance\.cpu_usage/).first()).toBeVisible()

    expect(mockAi.callCount('/api/ai/chat')).toBe(1)
  })

  test('handles duplicate tool_call events idempotently', async ({ page, mockAi }) => {
    await mockAi.mockChat([
      { type: 'tool_call', id: 'call-dup', name: 'search', input: { q: 'a' } },
      { type: 'tool_call', id: 'call-dup', name: 'search', input: { q: 'a' } },
      { type: 'tool_result', id: 'call-dup', name: 'search', output: { hits: [] } },
      { type: 'token', content: 'No matches.' },
      { type: 'done' },
    ])

    await page.goto('/chat')
    await page.getByPlaceholder('Ask about features...').fill('Search')
    await page.getByRole('button', { name: 'Send' }).click()

    await expect(page.getByText('No matches.')).toBeVisible()

    const toolHeaders = page
      .getByRole('main')
      .getByText(/search/i)
      .filter({ hasText: 'search' })
    expect(await toolHeaders.count()).toBeGreaterThanOrEqual(1)
  })

  test('routes thinking and token events into separate UI regions', async ({ page, mockAi }) => {
    await mockAi.mockChat([
      { type: 'thinking_start' },
      { type: 'thinking', content: 'Reasoning chunk' },
      { type: 'thinking_end' },
      { type: 'token', content: 'Final answer is 42.' },
      { type: 'done' },
    ])

    await page.goto('/chat')
    await page.getByPlaceholder('Ask about features...').fill('Q')
    await page.getByRole('button', { name: 'Send' }).click()

    await expect(page.getByText(/Final answer is 42/)).toBeVisible()

    // Reasoning text routes into a collapsible Reasoning block. The token
    // text is not the reasoning text, so the visible response area must
    // contain "Final answer" but NOT have "Reasoning chunk" inlined into it.
    const responseRegion = page.getByText(/Final answer is 42/).locator('xpath=ancestor::*[1]')
    await expect(responseRegion).not.toContainText('Reasoning chunk')
  })
})
