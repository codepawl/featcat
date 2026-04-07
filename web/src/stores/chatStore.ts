export interface ChatMessage {
  id: string
  role: 'user' | 'ai'
  content: string
  thinking?: string
  isDoneThinking?: boolean
  isStreaming?: boolean
  result?: any
  html?: string
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
    messages = [...messages, { ...msg, id: crypto.randomUUID(), timestamp: Date.now() }]
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
