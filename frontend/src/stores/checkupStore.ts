import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface Completeness {
  score: number
  level: string
  missing_fields: string[]
}

interface MemberResult {
  loading: boolean
  content: string | null
  error: string | null
  completeness: Completeness | null
}

interface CheckupState {
  results: Record<number, MemberResult>
  setLoading: (memberId: number, v: boolean) => void
  setContent: (memberId: number, content: string, completeness: Completeness) => void
  setError: (memberId: number, error: string) => void
  getResult: (memberId: number) => MemberResult
}

const EMPTY: MemberResult = { loading: false, content: null, error: null, completeness: null }

export const useCheckupStore = create<CheckupState>()(
  persist(
    (set, get) => ({
      results: {},
      setLoading: (memberId, v) =>
        set((s) => ({ results: { ...s.results, [memberId]: { ...get().getResult(memberId), loading: v } } })),
      setContent: (memberId, content, completeness) =>
        set((s) => ({ results: { ...s.results, [memberId]: { content, completeness, loading: false, error: null } } })),
      setError: (memberId, error) =>
        set((s) => ({ results: { ...s.results, [memberId]: { ...get().getResult(memberId), error, loading: false } } })),
      getResult: (memberId) => get().results[memberId] ?? EMPTY,
    }),
    { name: 'checkup-store' }
  )
)
