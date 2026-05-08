export type ToolState = 'input-streaming' | 'input-available' | 'output-available' | 'output-error'

export interface ToolCall {
  id: string
  name: string
  state: ToolState
  input?: any
  output?: any
  error?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'ai'
  content: string
  thinking?: string
  isDoneThinking?: boolean
  isStreaming?: boolean
  result?: any
  html?: string
  tools?: ToolCall[]
  timestamp: number
}

let messages: ChatMessage[] = [
  { id: 'welcome', role: 'ai', content: 'Welcome to featcat AI Chat! Ask anything about your features.', timestamp: Date.now() },
]
const listeners = new Set<() => void>()

function notify() {
  listeners.forEach((fn) => fn())
}

export const chatStore = {
  getMessages: () => messages,

  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    messages = [...messages, { ...msg, id: Math.random().toString(36).slice(2) + Date.now().toString(36), timestamp: Date.now() }]
    notify()
  },

  updateLastMessage: (update: Partial<ChatMessage>) => {
    if (messages.length === 0) return
    messages = [...messages.slice(0, -1), { ...messages[messages.length - 1], ...update }]
    notify()
  },

  appendToLastMessage: (field: 'content' | 'thinking', text: string) => {
    if (messages.length === 0) return
    const last = messages[messages.length - 1]
    messages = [...messages.slice(0, -1), { ...last, [field]: (last[field] || '') + text }]
    notify()
  },

  upsertToolCall: (id: string, patch: Partial<ToolCall> & { name?: string }) => {
    if (messages.length === 0) return
    const last = messages[messages.length - 1]
    const tools = last.tools ? [...last.tools] : []
    const idx = tools.findIndex((t) => t.id === id)
    if (idx >= 0) {
      tools[idx] = { ...tools[idx], ...patch }
    } else {
      tools.push({ id, name: patch.name || 'tool', state: 'input-available', ...patch })
    }
    messages = [...messages.slice(0, -1), { ...last, tools }]
    notify()
  },

  clear: () => {
    messages = [
      { id: 'welcome', role: 'ai', content: 'Welcome to featcat AI Chat! Ask anything about your features.', timestamp: Date.now() },
    ]
    notify()
  },

  subscribe: (fn: () => void) => {
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  },
}
