import { useState } from 'react'
import { checkupApi, membersApi, type SupplementPayload } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'

const BUDGET_OPTIONS = [
  { value: 'basic', label: '基础健康筛查型', price: '300-800元' },
  { value: 'core', label: '核心风险排查型', price: '800-2,500元' },
  { value: 'premium', label: '深度防癌与慢病管理型', price: '2,500元+' },
]

const CONTRAINDICATION_FIELDS: { key: string; label: string; femaleOnly?: boolean }[] = [
  { key: 'contrast_allergy', label: '是否对造影剂过敏？' },
  { key: 'has_pacemaker', label: '是否有心脏起搏器？' },
  { key: 'has_metal_implant', label: '是否有金属植入物？' },
  { key: 'on_anticoagulant', label: '是否在服用抗凝药（如阿司匹林、华法林）？' },
  { key: 'claustrophobia', label: '是否有幽闭恐惧症？' },
  { key: 'has_coagulopathy', label: '是否有凝血功能障碍？' },
  { key: 'has_heart_failure', label: '是否有心功能不全（NYHA III-IV级）？' },
  { key: 'is_pregnant', label: '是否怀孕？', femaleOnly: true },
  { key: 'is_preparing_pregnancy', label: '是否在备孕？', femaleOnly: true },
  { key: 'has_sexual_history', label: '是否有性生活史？', femaleOnly: true },
  { key: 'is_breastfeeding', label: '是否在哺乳期？', femaleOnly: true },
]

type TriState = 'yes' | 'no' | 'unknown'

interface Props {
  onSubmit: (budgetTier: string) => void
  onClose: () => void
}

export default function CheckupSupplementModal({ onSubmit, onClose }: Props) {
  const { currentMemberId, members, upsertMember } = useMemberStore()
  const member = members.find((m) => m.id === currentMemberId)
  const isFemale = member?.gender === 'female'

  const [budgetTier, setBudgetTier] = useState('core')
  const [region, setRegion] = useState(member?.region ?? '')
  const [occupation, setOccupation] = useState(member?.occupation ?? '')
  const [contraFields, setContraFields] = useState<Record<string, TriState>>(() => {
    const init: Record<string, TriState> = {}
    for (const f of CONTRAINDICATION_FIELDS) {
      const existing = (member as unknown as Record<string, string | undefined>)?.[f.key]
      init[f.key] = (existing as TriState) || 'unknown'
    }
    return init
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const visibleFields = CONTRAINDICATION_FIELDS.filter(
    (f) => !f.femaleOnly || isFemale
  )

  const handleSubmit = async () => {
    if (!currentMemberId) return
    setSubmitting(true)
    setError(null)
    try {
      const payload: SupplementPayload = {
        region: region || undefined,
        occupation: occupation || undefined,
      }
      for (const f of visibleFields) {
        const val = contraFields[f.key]
        if (val && val !== 'unknown') {
          (payload as Record<string, string>)[f.key] = val
        }
      }
      await checkupApi.supplement(currentMemberId, payload)
      // Refresh member data so next open has updated values
      const updated = await membersApi.get(currentMemberId)
      upsertMember(updated)
      onSubmit(budgetTier)
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-800">生成体检推荐方案</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <p className="mb-4 text-sm text-slate-500">
            补充以下信息以生成更精准、更安全的体检方案，已填写的信息将自动带出
          </p>

          {/* Budget */}
          <section className="mb-5">
            <h3 className="mb-2 text-sm font-medium text-slate-700">预算档位</h3>
            <div className="space-y-2">
              {BUDGET_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                    budgetTier === opt.value
                      ? 'border-primary bg-primary-light'
                      : 'border-slate-200 hover:border-slate-300'
                  }`}
                >
                  <input
                    type="radio"
                    name="budget"
                    value={opt.value}
                    checked={budgetTier === opt.value}
                    onChange={(e) => setBudgetTier(e.target.value)}
                    className="text-primary"
                  />
                  <div>
                    <span className="text-sm font-medium text-slate-800">{opt.label}</span>
                    <span className="ml-2 text-xs text-slate-400">{opt.price}</span>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* Basic info */}
          <section className="mb-5">
            <h3 className="mb-2 text-sm font-medium text-slate-700">基本信息</h3>
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-xs text-slate-500">居住地域</label>
                <input
                  type="text"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  placeholder="请输入省份或城市"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">职业</label>
                <input
                  type="text"
                  value={occupation}
                  onChange={(e) => setOccupation(e.target.value)}
                  placeholder="请输入职业"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>
          </section>

          {/* Contraindications */}
          <section className="mb-5">
            <h3 className="mb-2 text-sm font-medium text-slate-700">健康状态（用于安全排除）</h3>
            <div className="space-y-3">
              {visibleFields.map((f) => (
                <div key={f.key}>
                  <label className="mb-1.5 block text-sm text-slate-600">{f.label}</label>
                  <div className="flex gap-2">
                    {(['yes', 'no', 'unknown'] as TriState[]).map((opt) => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => setContraFields({ ...contraFields, [f.key]: opt })}
                        className={`rounded-lg border px-4 py-1.5 text-sm transition-colors ${
                          contraFields[f.key] === opt
                            ? opt === 'yes'
                              ? 'border-red-300 bg-red-50 text-red-600'
                              : opt === 'no'
                                ? 'border-green-300 bg-green-50 text-green-600'
                                : 'border-slate-300 bg-slate-50 text-slate-500'
                            : 'border-slate-200 text-slate-400 hover:border-slate-300'
                        }`}
                      >
                        {opt === 'yes' ? '是' : opt === 'no' ? '否' : '跳过'}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <p className="text-xs text-slate-400">
            跳过的项目将在方案中标注"未提供，请用户确认"
          </p>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 px-6 py-4">
          {error && <p className="mb-2 text-sm text-red-500">{error}</p>}
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full rounded-lg bg-primary py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:opacity-50"
          >
            {submitting ? '生成中...' : '生成方案'}
          </button>
        </div>
      </div>
    </div>
  )
}
