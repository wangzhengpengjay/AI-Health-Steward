import { create } from 'zustand'
import type { FamilyMember } from '@/types'

interface MemberState {
  members: FamilyMember[]
  currentMemberId: string | null
  setMembers: (members: FamilyMember[]) => void
  setCurrentMember: (id: string | null) => void
  upsertMember: (member: FamilyMember) => void
  removeMember: (id: string) => void
}

export const useMemberStore = create<MemberState>((set) => ({
  members: [],
  currentMemberId: null,

  setMembers: (members) =>
    set({ members, currentMemberId: members[0]?.id ?? null }),

  setCurrentMember: (id) => set({ currentMemberId: id }),

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
    set((state) => ({
      members: state.members.filter((m) => m.id !== id),
      currentMemberId:
        state.currentMemberId === id
          ? (state.members.find((m) => m.id !== id)?.id ?? null)
          : state.currentMemberId,
    })),
}))
