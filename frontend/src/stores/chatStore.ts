import { create } from 'zustand'
import type { ChatMessage } from '@/types'
import type { ReportRecord } from '@/lib/api'

interface MemberChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  streamingContent: string
  pendingReport: ReportRecord | null
  extractingReport: boolean
  error: string | null
  historyLoaded: boolean
}

const emptyMemberChat = (): MemberChatState => ({
  messages: [],
  isStreaming: false,
  streamingContent: '',
  pendingReport: null,
  extractingReport: false,
  error: null,
  historyLoaded: false,
})

interface ChatStoreState {
  members: Record<number, MemberChatState>
  setHistory: (memberId: number, messages: ChatMessage[]) => void
  appendMessage: (memberId: number, message: ChatMessage) => void
  setStreaming: (memberId: number, isStreaming: boolean) => void
  setStreamingContent: (memberId: number, content: string) => void
  setPendingReport: (memberId: number, report: ReportRecord | null) => void
  setExtractingReport: (memberId: number, extracting: boolean) => void
  setError: (memberId: number, error: string | null) => void
  clearAll: () => void
}

export const useChatStore = create<ChatStoreState>((set) => {
  const patch = (memberId: number, partial: Partial<MemberChatState>) =>
    set((state) => ({
      members: {
        ...state.members,
        [memberId]: { ...emptyMemberChat(), ...state.members[memberId], ...partial },
      },
    }))

  return {
    members: {},
    setHistory: (memberId, messages) => patch(memberId, { messages, historyLoaded: true }),
    appendMessage: (memberId, message) =>
      set((state) => ({
        members: {
          ...state.members,
          [memberId]: {
            ...emptyMemberChat(),
            ...state.members[memberId],
            messages: [...(state.members[memberId]?.messages ?? []), message],
          },
        },
      })),
    setStreaming: (memberId, isStreaming) => patch(memberId, { isStreaming }),
    setStreamingContent: (memberId, content) => patch(memberId, { streamingContent: content }),
    setPendingReport: (memberId, report) => patch(memberId, { pendingReport: report }),
    setExtractingReport: (memberId, extracting) => patch(memberId, { extractingReport: extracting }),
    setError: (memberId, error) => patch(memberId, { error }),
    clearAll: () => set({ members: {} }),
  }
})
