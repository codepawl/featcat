import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import i18n from '../../i18n/config'
import { Chat } from '../Chat'
import { chatStore } from '../../stores/chatStore'

const mocks = vi.hoisted(() => ({
  health: vi.fn(),
  discover: vi.fn(),
  monitorCheck: vi.fn(),
  stats: vi.fn(),
}))

vi.mock('../../api', () => ({
  invalidateCache: vi.fn(),
  api: {
    health: mocks.health,
    ai: {
      discover: mocks.discover,
    },
    monitor: {
      check: mocks.monitorCheck,
    },
    stats: mocks.stats,
  },
}))

describe('Chat page file attachments', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    chatStore.clear()
    await i18n.changeLanguage('en')
    mocks.health.mockResolvedValue({ status: 'ok', llm: true, model: 'gpt-4' })
  })

  it('renders initial state with empty greeting and suggestions', async () => {
    render(<Chat />)
    expect(await screen.findByText('Hi — ask anything about your features')).toBeInTheDocument()
    expect(screen.getByText('Discover features')).toBeInTheDocument()
  })

  it('allows adding and removing file attachments', async () => {
    render(<Chat />)

    // Retrieve input field and paperclip button
    const paperclipBtn = screen.getByTitle('Add attachment')
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeInTheDocument()

    // Mock file input change event
    const file = new File(['CREATE TABLE users (id INT);'], 'schema.sql', { type: 'text/plain' })

    // Simulate selecting the file
    fireEvent.change(fileInput, { target: { files: [file] } })

    // Wait for file reader to load content and render preview chip
    await waitFor(() => {
      expect(screen.getByText('schema.sql')).toBeInTheDocument()
    })

    // Now click the remove attachment button
    const removeBtn = screen.getByTitle('Remove attachment')
    fireEvent.click(removeBtn)

    // Verify it is removed
    expect(screen.queryByText('schema.sql')).not.toBeInTheDocument()
  })

  it('submits query with attachments to the backend and renders message bubble', async () => {
    // Mock fetch for SSE response
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: {
        get: () => 'test-session-id',
      },
      body: {
        getReader: () => {
          const encoder = new TextEncoder()
          const chunks = [
            encoder.encode('data: {"type": "token", "content": "Hello! I saw your table."}\n\n'),
            encoder.encode('data: {"type": "done"}\n\n'),
          ]
          let index = 0
          return {
            read: async () => {
              if (index < chunks.length) {
                return { value: chunks[index++], done: false }
              }
              return { value: undefined, done: true }
            },
          }
        },
      },
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<Chat />)

    // Add file
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['id,name\n1,alice'], 'data.csv', { type: 'text/plain' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('data.csv')).toBeInTheDocument()
    })

    // Enter query text
    const textarea = screen.getByPlaceholderText('Ask about features...')
    fireEvent.change(textarea, { target: { value: 'Analyze this data' } })

    // Send the message
    const sendBtn = screen.getByLabelText('Send')
    fireEvent.click(sendBtn)

    // Verify fetch was called with correct payload
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled()
    })

    const fetchArgs = fetchMock.mock.calls[0]
    expect(fetchArgs[0]).toBe('/api/ai/chat')
    const requestOptions = fetchArgs[1] as RequestInit
    expect(requestOptions.method).toBe('POST')

    const body = JSON.parse(requestOptions.body as string)
    expect(body.query).toBe('Analyze this data')
    expect(body.attachments).toEqual([
      { filename: 'data.csv', content: 'id,name\n1,alice' }
    ])

    // Verify chat bubble shows attachment pill in message list
    await waitFor(() => {
      // Find within message list
      const messageList = screen.getByTestId('chat-messages')
      expect(messageList).toBeInTheDocument()
      expect(messageList).toHaveTextContent('data.csv')
      expect(messageList).toHaveTextContent('Analyze this data')
    })
  })
})
