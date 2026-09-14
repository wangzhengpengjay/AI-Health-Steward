import { create } from 'zustand'
import type { FamilyMember } from '@/types'

interface MemberState {
  members: FamilyMember[]
  currentMemberId: number | null
  setMembers: (members: FamilyMember[]) => void
  setCurrentMember: (id: number | null) => void
  upsertMember: (member: FamilyMember) => void
  removeMember: (id: number) => void
}

const STORAGE_KEY = 'dsh:currentMemberId'

/** Read the persisted member selection, tolerating disabled/blocked storage. */
function readPersistedMemberId(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  } catch {
    return null
  }
}

function persistMemberId(id: number | null): void {
  try {
    if (id === null) window.localStorage.removeItem(STORAGE_KEY)
    else window.localStorage.setItem(STORAGE_KEY, String(id))
  } catch {
    // Storage unavailable (private mode / disabled): selection stays in memory.
  }
}

export const useMemberStore = create<MemberState>((set) => ({
  members: [],
  currentMemberId: readPersistedMemberId(),

  // Keep the current selection whenever it is still present in the list.
  // Previously every refetch reset it to members[0], so the app silently
  // switched members under the user (e.g. after saving a metric invalidated
  // the members query) and always fell back to the first member on reload.
  setMembers: (members) =>
    set((state) => {
      const stillExists =
        state.currentMemberId !== null &&
        members.some((m) => m.id === state.currentMemberId)
      const nextId = stillExists ? state.currentMemberId : (members[0]?.id ?? null)
      persistMemberId(nextId)
      return { members, currentMemberId: nextId }
    }),

  setCurrentMember: (id) => {
    persistMemberId(id)
    set({ currentMemberId: id })
  },

  // Add or replace a member in the list (used after create/update)
  upsertMember: (member) =>
    set((state) => {
      const idx = state.members.findIndex((m) => m.id === member.id)
      const members =
        idx >= 0
          ? state.members.map((m) => (m.id === member.id ? member : m))
          : [...state.members, member]
      return { members }
    }),

  removeMember: (id) =>
    set((state) => {
      const nextId =
        state.currentMemberId === id
          ? (state.members.find((m) => m.id !== id)?.id ?? null)
          : state.currentMemberId
      persistMemberId(nextId)
      return {
        members: state.members.filter((m) => m.id !== id),
        currentMemberId: nextId,
      }
    }),
}))
