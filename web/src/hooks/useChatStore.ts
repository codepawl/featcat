import { useSyncExternalStore } from 'react'
import { chatStore } from '../stores/chatStore'

export function useChatStore() {
  const messages = useSyncExternalStore(chatStore.subscribe, chatStore.getMessages)
  return { messages, ...chatStore }
}
