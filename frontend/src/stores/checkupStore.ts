import { create } from 'zustand'

interface Completeness {
  score: number
  level: string
  missing_fields: string[]
}

interface CheckupState {
  loading: boolean
  content: string | null
  error: string | null
  completeness: Completeness | null
  memberKey: string | null  // `${memberId}` to track which member's result
  setLoading: (v: boolean) => void
  setContent: (content: string, completeness: Completeness, memberKey: string) => void
  setError: (error: string, memberKey: string) => void
  reset: (memberKey: string) => void
}

export const useCheckupStore = create<CheckupState>((set) => ({
  loading: false,
  content: null,
  error: null,
  completeness: null,
  memberKey: null,
  setLoading: (v) => set({ loading: v }),
  setContent: (content, completeness, memberKey) =>
    set({ content, completeness, memberKey, loading: false, error: null }),
  setError: (error, memberKey) =>
    set({ error, memberKey, loading: false }),
  reset: (memberKey) => set({ loading: false, content: null, error: null, completeness: null, memberKey }),
}))
