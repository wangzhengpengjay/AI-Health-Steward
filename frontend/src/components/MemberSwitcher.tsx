import { useMemberStore } from '@/stores/memberStore'

export default function MemberSwitcher() {
  const { members, currentMemberId, setCurrentMember } = useMemberStore()

  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-slate-500">
        当前成员
      </label>
      {members.length === 0 ? (
        <p className="text-sm text-slate-400">暂未添加成员</p>
      ) : (
        <select
          value={currentMemberId ?? ''}
          onChange={(e) => setCurrentMember(e.target.value || null)}
          className="w-full rounded-field border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        >
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}（{relationshipLabel(m.relationship)}）
            </option>
          ))}
        </select>
      )}
    </div>
  )
}

function relationshipLabel(rel: string): string {
  const map: Record<string, string> = {
    self: '本人',
    spouse: '配偶',
    parent: '父母',
    child: '子女',
    sibling: '兄弟姐妹',
    grandparent: '祖父母',
    other: '其他',
  }
  return map[rel] ?? rel
}
