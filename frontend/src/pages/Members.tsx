import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { membersApi } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import type { FamilyMember, FamilyMemberInput, Gender, Relationship, BloodType } from '@/types'

const GENDER_OPTIONS: { value: Gender; label: string }[] = [
  { value: 'male', label: '男' },
  { value: 'female', label: '女' },
  { value: 'other', label: '其他' },
]

const RELATIONSHIP_OPTIONS: { value: Relationship; label: string }[] = [
  { value: 'self', label: '本人' },
  { value: 'spouse', label: '配偶' },
  { value: 'parent', label: '父母' },
  { value: 'child', label: '子女' },
  { value: 'sibling', label: '兄弟姐妹' },
  { value: 'grandparent', label: '祖父母' },
  { value: 'other', label: '其他' },
]

const BLOOD_TYPE_OPTIONS: BloodType[] = ['A', 'B', 'AB', 'O', 'unknown']

export default function Members() {
  const queryClient = useQueryClient()
  const { upsertMember, removeMember, setMembers } = useMemberStore()
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<FamilyMember | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<FamilyMember | null>(null)

  const { data: members = [], isLoading } = useQuery<FamilyMember[]>({
    queryKey: ['members'],
    queryFn: membersApi.list,
  })

  // Sync fetched members to zustand store
  useEffect(() => {
    if (members.length > 0) setMembers(members)
  }, [members, setMembers])

  const createMutation = useMutation({
    mutationFn: (data: FamilyMemberInput) => membersApi.create(data),
    onSuccess: (member) => {
      queryClient.invalidateQueries({ queryKey: ['members'] })
      upsertMember(member)
      setModalOpen(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FamilyMemberInput> }) =>
      membersApi.update(id, data),
    onSuccess: (member) => {
      queryClient.invalidateQueries({ queryKey: ['members'] })
      upsertMember(member)
      setModalOpen(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => membersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['members'] })
      if (deleteTarget) removeMember(deleteTarget.id)
      setDeleteTarget(null)
    },
  })

  const handleSubmit = (data: FamilyMemberInput) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  const handleEdit = (member: FamilyMember) => {
    setEditing(member)
    setModalOpen(true)
  }

  const handleAdd = () => {
    setEditing(null)
    setModalOpen(true)
  }

  return (
    <div className="mx-auto max-w-5xl p-8">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-symbols-rounded text-3xl text-primary">group</span>
          <h1 className="text-2xl font-semibold text-slate-800">成员管理</h1>
        </div>
        <button
          onClick={handleAdd}
          className="flex items-center gap-1.5 rounded-field bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
        >
          <span className="material-symbols-rounded text-xl">person_add</span>
          添加成员
        </button>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-card border border-slate-200 bg-bg-primary">
        <table className="w-full">
          <thead>
            <tr className="border-b border-slate-200 bg-bg-tertiary text-left text-sm text-slate-600">
              <th className="px-4 py-3 font-medium">姓名</th>
              <th className="px-4 py-3 font-medium">性别</th>
              <th className="px-4 py-3 font-medium">出生日期</th>
              <th className="px-4 py-3 font-medium">关系</th>
              <th className="px-4 py-3 font-medium">血型</th>
              <th className="px-4 py-3 text-right font-medium">操作</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-400">
                  加载中...
                </td>
              </tr>
            ) : members.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-400">
                  暂无家庭成员，点击「添加成员」开始
                </td>
              </tr>
            ) : (
              members.map((m) => (
                <tr key={m.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 text-sm font-medium text-slate-800">{m.name}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{genderLabel(m.gender)}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{m.birth_date}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{relationshipLabel(m.relationship)}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">{m.blood_type ?? '-'}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleEdit(m)}
                      className="mr-2 rounded-field px-3 py-1 text-sm text-primary hover:bg-primary-light"
                    >
                      编辑
                    </button>
                    <button
                      onClick={() => setDeleteTarget(m)}
                      className="rounded-field px-3 py-1 text-sm text-semantic-error hover:bg-red-50"
                    >
                      删除
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Add/Edit modal */}
      {modalOpen && (
        <MemberFormModal
          editing={editing}
          onSubmit={handleSubmit}
          onClose={() => setModalOpen(false)}
          loading={createMutation.isPending || updateMutation.isPending}
          error={createMutation.error?.message ?? updateMutation.error?.message}
        />
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <ConfirmDialog
          title="删除家庭成员"
          message={`确定要删除「${deleteTarget.name}」吗？该操作将删除其所有健康画像数据，且不可恢复。建议先导出数据。`}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
          loading={deleteMutation.isPending}
        />
      )}
    </div>
  )
}

// ---- Member form modal ----

interface MemberFormModalProps {
  editing: FamilyMember | null
  onSubmit: (data: FamilyMemberInput) => void
  onClose: () => void
  loading: boolean
  error?: string
}

function MemberFormModal({ editing, onSubmit, onClose, loading, error }: MemberFormModalProps) {
  const [form, setForm] = useState<FamilyMemberInput>({
    name: editing?.name ?? '',
    gender: editing?.gender ?? 'male',
    birth_date: editing?.birth_date ?? '',
    relationship: editing?.relationship ?? 'self',
    blood_type: editing?.blood_type ?? 'unknown',
    phone: editing?.phone ?? '',
  })

  const handleChange = <K extends keyof FamilyMemberInput>(
    key: K,
    value: FamilyMemberInput[K],
  ) => setForm((f) => ({ ...f, [key]: value }))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-full max-w-md rounded-card bg-bg-primary p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-slate-800">
          {editing ? '编辑成员' : '添加成员'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field label="姓名" required>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => handleChange('name', e.target.value)}
              className="input-base"
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="性别" required>
              <select
                value={form.gender}
                onChange={(e) => handleChange('gender', e.target.value as Gender)}
                className="input-base"
              >
                {GENDER_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </Field>

            <Field label="关系" required>
              <select
                value={form.relationship}
                onChange={(e) => handleChange('relationship', e.target.value as Relationship)}
                className="input-base"
              >
                {RELATIONSHIP_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="出生日期" required>
            <input
              type="date"
              required
              value={form.birth_date}
              onChange={(e) => handleChange('birth_date', e.target.value)}
              className="input-base"
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="血型">
              <select
                value={form.blood_type ?? 'unknown'}
                onChange={(e) => handleChange('blood_type', e.target.value as BloodType)}
                className="input-base"
              >
                {BLOOD_TYPE_OPTIONS.map((b) => (
                  <option key={b} value={b}>{b === 'unknown' ? '未知' : b}</option>
                ))}
              </select>
            </Field>

            <Field label="电话">
              <input
                type="tel"
                value={form.phone ?? ''}
                onChange={(e) => handleChange('phone', e.target.value)}
                className="input-base"
              />
            </Field>
          </div>

          {error && (
            <p className="text-sm text-semantic-error">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-field border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-bg-tertiary"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-field bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
            >
              {loading ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---- Confirm dialog ----

interface ConfirmDialogProps {
  title: string
  message: string
  onConfirm: () => void
  onCancel: () => void
  loading: boolean
}

function ConfirmDialog({ title, message, onConfirm, onCancel, loading }: ConfirmDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="w-full max-w-sm rounded-card bg-bg-primary p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold text-slate-800">{title}</h2>
        <p className="mb-4 text-sm text-slate-600">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded-field border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-bg-tertiary"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="rounded-field bg-semantic-error px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {loading ? '删除中...' : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---- Form field wrapper ----

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-slate-700">
        {label}{required && <span className="text-semantic-error"> *</span>}
      </label>
      {children}
    </div>
  )
}

// ---- Label helpers ----

function genderLabel(g: Gender): string {
  return GENDER_OPTIONS.find((o) => o.value === g)?.label ?? g
}

function relationshipLabel(r: Relationship): string {
  return RELATIONSHIP_OPTIONS.find((o) => o.value === r)?.label ?? r
}
