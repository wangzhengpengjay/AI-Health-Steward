import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { membersApi, metricsApi, ApiError } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import type { MetricName, SourceType } from '@/types'
import type { FamilyMember } from '@/types'

const METRIC_OPTIONS: { value: MetricName; label: string; unit: string }[] = [
  { value: 'blood_pressure_systolic', label: '收缩压', unit: 'mmHg' },
  { value: 'blood_pressure_diastolic', label: '舒张压', unit: 'mmHg' },
  { value: 'heart_rate', label: '心率', unit: 'bpm' },
  { value: 'blood_glucose', label: '血糖', unit: 'mmol/L' },
  { value: 'weight', label: '体重', unit: 'kg' },
  { value: 'height', label: '身高', unit: 'cm' },
  { value: 'bmi', label: 'BMI', unit: '' },
  { value: 'temperature', label: '体温', unit: '℃' },
  { value: 'spo2', label: '血氧饱和度', unit: '%' },
  { value: 'steps', label: '步数', unit: '步' },
]

const SOURCE_OPTIONS: { value: SourceType; label: string }[] = [
  { value: 'manual', label: '手动录入' },
  { value: 'report', label: '报告导入' },
  { value: 'chat_extract', label: '聊天抽取' },
]

interface MetricFormState {
  metric_name: MetricName
  value: string
  unit: string
  recorded_at: string
  source_type: SourceType
  note: string
}

const nowISO = () => {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

export default function MetricInput() {
  const queryClient = useQueryClient()
  const { members, currentMemberId, setCurrentMember, setMembers } = useMemberStore()
  const [success, setSuccess] = useState(false)

  const { data: fetchedMembers } = useQuery<FamilyMember[]>({
    queryKey: ['members'],
    queryFn: membersApi.list,
    enabled: members.length === 0,
  })

  // Sync fetched members to zustand store
  useEffect(() => {
    if (fetchedMembers && fetchedMembers.length > 0) setMembers(fetchedMembers)
  }, [fetchedMembers, setMembers])

  const selectedMember = members.find((m) => m.id === currentMemberId) ?? null

  const [form, setForm] = useState<MetricFormState>({
    metric_name: 'blood_pressure_systolic',
    value: '',
    unit: 'mmHg',
    recorded_at: nowISO(),
    source_type: 'manual',
    note: '',
  })

  const createMutation = useMutation({
    mutationFn: (vars: { memberId: string; data: MetricFormState }) =>
      metricsApi.create(vars.memberId, {
        metric_name: vars.data.metric_name,
        value: parseFloat(vars.data.value),
        unit: vars.data.unit,
        recorded_at: new Date(vars.data.recorded_at).toISOString(),
        source_type: vars.data.source_type,
        note: vars.data.note || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['metrics'] })
      setSuccess(true)
      // Reset value for next entry, keep the same metric type
      setForm((f) => ({ ...f, value: '', note: '' }))
      setTimeout(() => setSuccess(false), 3000)
    },
  })

  const handleMetricChange = (metricName: MetricName) => {
    const opt = METRIC_OPTIONS.find((o) => o.value === metricName)
    setForm((f) => ({ ...f, metric_name: metricName, unit: opt?.unit ?? '' }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedMember) return
    createMutation.mutate({ memberId: selectedMember.id, data: form })
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <span className="material-symbols-rounded text-3xl text-primary">edit_note</span>
        <h1 className="text-2xl font-semibold text-slate-800">手动录入</h1>
      </div>

      {/* Member selector */}
      <div className="mb-6 rounded-card border border-slate-200 bg-bg-primary p-4">
        <label className="mb-1.5 block text-sm font-medium text-slate-700">
          录入对象 <span className="text-semantic-error">*</span>
        </label>
        {members.length === 0 ? (
          <p className="text-sm text-slate-400">请先在「成员管理」中添加家庭成员</p>
        ) : (
          <select
            value={currentMemberId ?? ''}
            onChange={(e) => setCurrentMember(e.target.value)}
            className="input-base"
          >
            <option value="" disabled>请选择成员</option>
            {members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}（{relationshipLabel(m.relationship)}）
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4 rounded-card border border-slate-200 bg-bg-primary p-6">
        <div className="grid grid-cols-2 gap-4">
          <Field label="指标类型" required>
            <select
              value={form.metric_name}
              onChange={(e) => handleMetricChange(e.target.value as MetricName)}
              className="input-base"
            >
              {METRIC_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>

          <Field label="数值" required>
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="0.01"
                required
                value={form.value}
                onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
                className="input-base"
                placeholder="例如 130"
              />
              <span className="whitespace-nowrap text-sm text-slate-500">{form.unit}</span>
            </div>
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="测量时间" required>
            <input
              type="datetime-local"
              required
              value={form.recorded_at}
              onChange={(e) => setForm((f) => ({ ...f, recorded_at: e.target.value }))}
              className="input-base"
            />
          </Field>

          <Field label="数据来源">
            <select
              value={form.source_type}
              onChange={(e) => setForm((f) => ({ ...f, source_type: e.target.value as SourceType }))}
              className="input-base"
            >
              {SOURCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="备注">
          <textarea
            value={form.note}
            onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
            className="input-base min-h-[80px] resize-y"
            placeholder="可选：测量条件、身体状态等"
          />
        </Field>

        {/* Error / success messages */}
        {createMutation.isError && (
          <p className="text-sm text-semantic-error">
            录入失败：{(createMutation.error as ApiError)?.message ?? '未知错误'}
          </p>
        )}
        {success && (
          <p className="flex items-center gap-1 text-sm text-semantic-success">
            <span className="material-symbols-rounded text-lg">check_circle</span>
            录入成功，可继续录入下一条
          </p>
        )}

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={!selectedMember || createMutation.isPending}
            className="flex items-center gap-1.5 rounded-field bg-primary px-6 py-2 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-50"
          >
            <span className="material-symbols-rounded text-xl">save</span>
            {createMutation.isPending ? '保存中...' : '保存记录'}
          </button>
        </div>
      </form>
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

function relationshipLabel(r: string): string {
  const map: Record<string, string> = {
    self: '本人',
    spouse: '配偶',
    parent: '父母',
    child: '子女',
    sibling: '兄弟姐妹',
    grandparent: '祖父母',
    other: '其他',
  }
  return map[r] ?? r
}
