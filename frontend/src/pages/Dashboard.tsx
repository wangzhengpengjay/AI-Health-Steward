import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { metricsApi, profileApi } from '@/lib/api'
import { LabTabContent, ExamTimeline } from '@/components/MetricViews'
import { useMemberStore } from '@/stores/memberStore'
import type { MetricRecord } from '@/types'

const METRIC_LABELS: Record<string, { label: string; unit: string }> = {
  systolic_blood_pressure: { label: '收缩压', unit: 'mmHg' },
  diastolic_blood_pressure: { label: '舒张压', unit: 'mmHg' },
  fasting_glucose: { label: '空腹血糖', unit: 'mmol/L' },
  postmeal_glucose: { label: '餐后血糖', unit: 'mmol/L' },
  total_cholesterol: { label: '总胆固醇', unit: 'mmol/L' },
  triglycerides: { label: '甘油三酯', unit: 'mmol/L' },
  ldl_cholesterol: { label: 'LDL-C', unit: 'mmol/L' },
  hdl_cholesterol: { label: 'HDL-C', unit: 'mmol/L' },
  heart_rate: { label: '心率', unit: 'bpm' },
  weight: { label: '体重', unit: 'kg' },
}

const SEVERITY_LABELS: Record<string, string> = { mild: '轻度', moderate: '中度', severe: '重度' }
const STATUS_LABELS: Record<string, string> = { active: '现患', past: '既往', cured: '已愈' }

export default function Dashboard() {
  const { currentMemberId, members } = useMemberStore()
  const queryClient = useQueryClient()
  const member = members.find((m) => m.id === currentMemberId)
  const [addModal, setAddModal] = useState<null | 'diagnosis' | 'medication' | 'allergy' | 'lifestyle' | 'surgery' | 'vaccination'>(null)
  const [reportDetail, setReportDetail] = useState<{ name: string; type: 'lab' | 'exam'; records: Record<string, MetricRecord[]> } | null>(null)

  const { data: allMetrics = [] } = useQuery({
    queryKey: ['metrics-all', currentMemberId],
    queryFn: () => metricsApi.list(Number(currentMemberId)),
    enabled: !!currentMemberId,
  })

  const { data: profile } = useQuery({
    queryKey: ['profile', currentMemberId],
    queryFn: () => profileApi.get(Number(currentMemberId)),
    enabled: !!currentMemberId,
  })

  const deleteMutation = useMutation({
    mutationFn: ({ type, id }: { type: string; id: number }) => profileApi.deleteRecord(type, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profile', currentMemberId] }),
  })

  if (!currentMemberId || !member) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-rounded text-5xl text-slate-300">person_add</span>
          <p className="mt-3 text-slate-500">请先选择家庭成员</p>
        </div>
      </div>
    )
  }

  const latestByMetric: Record<string, MetricRecord> = {}
  for (const r of allMetrics) {
    if (r.metric_name.startsWith("lab:") || r.metric_name.startsWith("exam:")) continue
    if (!latestByMetric[r.metric_name] || new Date(r.measured_at) > new Date(latestByMetric[r.metric_name].measured_at)) {
      latestByMetric[r.metric_name] = r
    }
  }

  // Group lab/exam by report name / category
  const reportGroups: { name: string; type: 'lab' | 'exam'; records: Record<string, MetricRecord[]> }[] = []
  const groupMap: Record<string, { name: string; type: 'lab' | 'exam'; records: Record<string, MetricRecord[]> }> = {}
  for (const r of allMetrics) {
    if (r.metric_name.startsWith('lab:')) {
      const name = r.metric_name.split(':')[1] || '检验报告'
      if (!groupMap[name]) groupMap[name] = { name, type: 'lab', records: {} }
      if (!groupMap[name].records[r.metric_name]) groupMap[name].records[r.metric_name] = []
      groupMap[name].records[r.metric_name].push(r)
    } else if (r.metric_name.startsWith('exam:')) {
      const name = r.metric_name.split(':')[1] || '检查发现'
      if (!groupMap[name]) groupMap[name] = { name, type: 'exam', records: {} }
      if (!groupMap[name].records[r.metric_name]) groupMap[name].records[r.metric_name] = []
      groupMap[name].records[r.metric_name].push(r)
    }
  }
  reportGroups.push(...Object.values(groupMap))

  const abnormals = allMetrics.filter((r) => r.is_abnormal && !r.metric_name.startsWith('lab:') && !r.metric_name.startsWith('exam:'))
  const abnormalMetrics = [...new Set(abnormals.map((r) => r.metric_name))]

  const age = member.birth_date
    ? Math.floor((Date.now() - new Date(member.birth_date).getTime()) / 365.25 / 86400000)
    : null

 const diagnoses = profile?.diagnoses ?? []
 const medications = profile?.medications ?? []
 const allergies = profile?.allergies ?? []
  const lifestyles = profile?.lifestyles ?? []
  const surgeries = profile?.surgeries ?? []
  const vaccinations = profile?.vaccinations ?? []

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-bg-secondary">
      <div className="border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-primary">dashboard</span>
          <h1 className="text-lg font-medium text-slate-800">画像看板</h1>
          <span className="ml-2 rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary">{member.name}</span>
        </div>
      </div>

      <div className="space-y-4 p-6">
        {/* Basic info */}
        <div className="rounded-card border border-slate-200 bg-white p-5">
          <div className="mb-3 flex items-center gap-2">
            <span className="material-symbols-rounded text-slate-400">badge</span>
            <h2 className="text-sm font-medium text-slate-700">基础信息</h2>
          </div>
          <div className="grid grid-cols-3 gap-4 sm:grid-cols-5">
            <InfoItem label="姓名" value={member.name} />
            <InfoItem label="性别" value={member.gender === 'male' ? '男' : member.gender === 'female' ? '女' : '其他'} />
            <InfoItem label="年龄" value={age !== null ? `${age}岁` : '-'} />
            <InfoItem label="血型" value={member.blood_type ?? '-'} />
            <InfoItem label="关系" value={member.relationship ?? '-'} />
          </div>
        </div>

        {/* Metrics + Abnormal */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="rounded-card border border-slate-200 bg-white p-5 lg:col-span-2">
            <div className="mb-3 flex items-center gap-2">
              <span className="material-symbols-rounded text-slate-400">monitoring</span>
              <h2 className="text-sm font-medium text-slate-700">最新指标</h2>
            </div>
            {Object.keys(latestByMetric).length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-400">暂无指标数据</p>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {Object.entries(latestByMetric).map(([key, r]) => {
                  const meta = METRIC_LABELS[key] || { label: key, unit: r.unit || '' }
                  return (
                    <div key={key} className={`rounded-field border p-3 ${r.is_abnormal ? 'border-amber-200 bg-amber-50' : 'border-slate-100 bg-slate-50'}`}>
                      <p className="text-xs text-slate-500">{meta.label}</p>
                      <p className={`mt-1 text-lg font-semibold ${r.is_abnormal ? 'text-amber-600' : 'text-slate-800'}`}>
                        {r.value}
                        <span className="ml-1 text-xs text-slate-400">{meta.unit}</span>
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
            {/* Report group cards */}
            {reportGroups.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {reportGroups.map((g) => (
                  <button
                    key={g.name}
                    onClick={() => setReportDetail(g)}
                    className="flex items-center gap-2 rounded-field border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700 transition hover:border-primary hover:bg-primary-light/30"
                  >
                    <span className={`material-symbols-rounded text-lg ${g.type === 'lab' ? 'text-green-600' : 'text-amber-600'}`}>
                      {g.type === 'lab' ? 'science' : 'stethoscope'}
                    </span>
                    <span className="font-medium">{g.name}</span>
                    <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-xs text-slate-500">{Object.keys(g.records).length}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="rounded-card border border-slate-200 bg-white p-5">
            <div className="mb-3 flex items-center gap-2">
              <span className="material-symbols-rounded text-slate-400">warning</span>
              <h2 className="text-sm font-medium text-slate-700">异常项</h2>
            </div>
            {abnormalMetrics.length === 0 ? (
              <div className="flex flex-col items-center py-6 text-center">
                <span className="material-symbols-rounded text-3xl text-green-400">check_circle</span>
                <p className="mt-1 text-sm text-green-600">暂无异常</p>
              </div>
            ) : (
              <div className="space-y-2">
                {abnormalMetrics.map((key) => {
                  const meta = METRIC_LABELS[key] || { label: key, unit: '' }
                  const latest = latestByMetric[key]
                  return (
                    <div key={key} className="flex items-center justify-between rounded-field bg-amber-50 px-3 py-2">
                      <span className="text-sm text-slate-700">{meta.label}</span>
                      <span className="text-sm font-medium text-amber-600">{latest?.value} {meta.unit}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Diagnoses */}
        <SectionCard
          icon="medical_information"
          title="诊断记录"
          onAdd={() => setAddModal('diagnosis')}
        >
          {diagnoses.length === 0 ? <Empty text="暂无诊断记录" /> : diagnoses.map((d) => (
            <RecordRow
              key={d.id}
              title={d.disease_name}
              badges={[
                d.severity ? SEVERITY_LABELS[d.severity] ?? d.severity : null,
                STATUS_LABELS[d.status] ?? d.status,
                d.diagnosed_date ? d.diagnosed_date : null,
              ]}
              onDelete={() => deleteMutation.mutate({ type: 'diagnoses', id: d.id })}
            />
          ))}
        </SectionCard>

        {/* Medications */}
        <SectionCard
          icon="medication"
          title="用药记录"
          onAdd={() => setAddModal('medication')}
        >
          {medications.length === 0 ? <Empty text="暂无用药记录" /> : medications.map((m) => (
            <RecordRow
              key={m.id}
              title={m.drug_name}
              subtitle={m.generic_name}
              badges={[`${m.dosage} · ${m.frequency}`, m.start_date ?? null]}
              onDelete={() => deleteMutation.mutate({ type: 'medications', id: m.id })}
            />
          ))}
        </SectionCard>

        {/* Allergies */}
        <SectionCard
          icon="dangerous"
          title="过敏信息"
          onAdd={() => setAddModal('allergy')}
        >
          {allergies.length === 0 ? <Empty text="暂无过敏记录" /> : allergies.map((a) => (
            <RecordRow
              key={a.id}
              title={a.name}
              badges={[
                a.type === 'drug' ? '药物' : a.type === 'food' ? '食物' : '其他',
                SEVERITY_LABELS[a.severity] ?? a.severity,
              ]}
              onDelete={() => deleteMutation.mutate({ type: 'allergies', id: a.id })}
            />
         ))}
       </SectionCard>

        {/* Lifestyle (smoking/drinking) */}
        <SectionCard
          icon="smoke_free"
          title="个人史"
          onAdd={() => setAddModal('lifestyle')}
        >
          {lifestyles.length === 0 ? <Empty text="暂无个人史记录" /> : lifestyles.map((l) => (
            <RecordRow
              key={l.id}
              title={l.category === 'smoking' ? '吸烟' : l.category === 'drinking' ? '饮酒' : l.category === 'exercise' ? '运动' : l.category === 'sleep' ? '睡眠' : '饮食'}
              badges={[l.status, l.frequency ?? null, l.recorded_at ?? null]}
              onDelete={() => deleteMutation.mutate({ type: 'lifestyles', id: l.id })}
            />
          ))}
        </SectionCard>

        {/* Surgical history */}
        <SectionCard
          icon="healing"
          title="手术史"
          onAdd={() => setAddModal('surgery')}
        >
          {surgeries.length === 0 ? <Empty text="暂无手术记录" /> : surgeries.map((s) => (
            <RecordRow
              key={s.id}
              title={s.surgery_name}
              badges={[s.surgery_date ?? null, s.hospital ?? null]}
              onDelete={() => deleteMutation.mutate({ type: 'surgeries', id: s.id })}
            />
          ))}
        </SectionCard>

        {/* Vaccination history */}
        <SectionCard
          icon="vaccines"
          title="疫苗接种史"
          onAdd={() => setAddModal('vaccination')}
        >
          {vaccinations.length === 0 ? <Empty text="暂无疫苗接种记录" /> : vaccinations.map((v) => (
            <RecordRow
              key={v.id}
              title={v.vaccine_name}
              badges={[v.dose_no ?? null, v.vaccinated_date ?? null, v.facility ?? null]}
              onDelete={() => deleteMutation.mutate({ type: 'vaccinations', id: v.id })}
            />
          ))}
        </SectionCard>

        {/* Data summary */}
        <div className="grid grid-cols-3 gap-4">
          <SummaryCard label="指标记录" value={allMetrics.length} />
          <SummaryCard label="诊断/用药" value={diagnoses.length + medications.length} />
          <SummaryCard label="异常记录" value={abnormals.length} abnormal={abnormals.length > 0} />
        </div>
      </div>

      {reportDetail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setReportDetail(null)}>
          <div className="max-h-[85vh] w-[700px] overflow-y-auto rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className={`material-symbols-rounded text-lg ${reportDetail.type === 'lab' ? 'text-green-600' : 'text-amber-600'}`}>
                  {reportDetail.type === 'lab' ? 'science' : 'stethoscope'}
                </span>
                <h2 className="text-base font-medium text-slate-800">{reportDetail.name}</h2>
                <span className="text-xs text-slate-400">{reportDetail.type === 'lab' ? '检验' : '检查'}</span>
              </div>
              <button onClick={() => setReportDetail(null)} className="text-slate-400 hover:text-slate-600">
                <span className="material-symbols-rounded">close</span>
              </button>
            </div>
            {reportDetail.type === 'lab'
              ? <LabTabContent allRecords={reportDetail.records} tabLabel={reportDetail.name} />
              : <ExamTimeline allRecords={reportDetail.records} tabLabel={reportDetail.name} />}
          </div>
        </div>
      )}

      {addModal && (
        <AddProfileModal
          type={addModal}
          memberId={Number(currentMemberId)}
          onClose={() => setAddModal(null)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ['profile', currentMemberId] })
            setAddModal(null)
          }}
        />
      )}
    </div>
  )
}

function InfoItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-slate-700">{value}</p>
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <p className="py-4 text-center text-sm text-slate-400">{text}</p>
}

function SectionCard({ icon, title, onAdd, children }: { icon: string; title: string; onAdd: () => void; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-slate-400">{icon}</span>
          <h2 className="text-sm font-medium text-slate-700">{title}</h2>
        </div>
        <button onClick={onAdd} className="flex items-center gap-1 rounded-field border border-slate-200 px-2 py-1 text-xs text-slate-600 transition hover:border-primary hover:text-primary">
          <span className="material-symbols-rounded text-base">add</span>
          新增
        </button>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function RecordRow({ title, subtitle, badges, onDelete }: {
  title: string
  subtitle?: string
  badges: (string | null)[]
  onDelete: () => void
}) {
  return (
    <div className="flex items-center justify-between rounded-field bg-slate-50 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-700">{title}</span>
        {subtitle && <span className="text-xs text-slate-400">({subtitle})</span>}
        {badges.filter(Boolean).map((b, i) => (
          <span key={i} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{b}</span>
        ))}
      </div>
      <button onClick={onDelete} className="rounded p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-500" title="删除">
        <span className="material-symbols-rounded text-base">delete</span>
      </button>
    </div>
  )
}

function SummaryCard({ label, value, abnormal }: { label: string; value: number; abnormal?: boolean }) {
  return (
    <div className="rounded-card border border-slate-200 bg-white p-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${abnormal ? 'text-amber-600' : 'text-slate-800'}`}>{value}</p>
    </div>
  )
}

// ---- Add modal ----
function AddProfileModal({ type, memberId, onClose, onSuccess }: {
  type: 'diagnosis' | 'medication' | 'allergy' | 'lifestyle' | 'surgery' | 'vaccination'
  memberId: number
  onClose: () => void
  onSuccess: () => void
}) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      if (type === 'diagnosis') return profileApi.addDiagnosis(memberId, data as never)
      if (type === 'medication') return profileApi.addMedication(memberId, data as never)
      if (type === 'allergy') return profileApi.addAllergy(memberId, data as never)
      if (type === 'lifestyle') return profileApi.addLifestyle(memberId, data as never)
      if (type === 'surgery') return profileApi.addSurgery(memberId, data as never)
      return profileApi.addVaccination(memberId, data as never)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile', memberId] })
      onSuccess()
    },
  })

  const TITLE_MAP: Record<string, string> = { diagnosis: '诊断', medication: '用药', allergy: '过敏', lifestyle: '个人史', surgery: '手术', vaccination: '疫苗接种' }
  const title = TITLE_MAP[type] ?? type

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-96 rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">新增{title}记录</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            const fd = new FormData(e.currentTarget)
            const data: Record<string, unknown> = {}
            for (const [k, v] of fd.entries()) {
              if (v) data[k] = v
            }
            mutation.mutate(data)
          }}
          className="space-y-3"
        >
          {type === 'diagnosis' && (
            <>
              <Field label="疾病名称" name="disease_name" required />
              <div className="grid grid-cols-2 gap-3">
                <SelectField label="严重程度" name="severity" options={[['', '请选择'], ['mild', '轻度'], ['moderate', '中度'], ['severe', '重度']]} />
                <SelectField label="状态" name="status" options={[['active', '现患'], ['past', '既往'], ['cured', '已愈']]} />
              </div>
              <DateField label="诊断日期" name="diagnosed_date" />
            </>
          )}
          {type === 'medication' && (
            <>
              <Field label="药品名称" name="drug_name" required />
              <div className="grid grid-cols-2 gap-3">
                <Field label="剂量" name="dosage" required placeholder="如 5mg" />
                <Field label="频次" name="frequency" required placeholder="如 每日一次" />
              </div>
              <DateField label="开始日期" name="start_date" />
            </>
          )}
         {type === 'allergy' && (
           <>
             <SelectField label="类型" name="type" options={[['drug', '药物'], ['food', '食物'], ['other', '其他']]} />
             <Field label="过敏原" name="name" required />
             <SelectField label="严重程度" name="severity" options={[['mild', '轻度'], ['moderate', '中度'], ['severe', '重度']]} />
           </>
         )}
         {type === 'lifestyle' && (
            <LifestyleForm />
         )}
         {type === 'surgery' && (
            <>
              <Field label="手术名称" name="surgery_name" required />
              <DateField label="手术日期" name="surgery_date" />
              <Field label="医院" name="hospital" />
              <Field label="备注" name="notes" />
            </>
          )}
          {type === 'vaccination' && (
            <>
              <Field label="疫苗名称" name="vaccine_name" required placeholder="如 乙肝疫苗" />
              <Field label="剂次" name="dose_no" placeholder="如 第1剂、加强针" />
              <DateField label="接种日期" name="vaccinated_date" />
              <Field label="接种机构" name="facility" />
            </>
          )}
         {mutation.error && <p className="text-sm text-red-500">保存失败</p>}
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 rounded-field border border-slate-200 py-2 text-sm text-slate-600 hover:bg-slate-50">取消</button>
            <button type="submit" disabled={mutation.isPending} className="flex-1 rounded-field bg-primary py-2 text-sm text-white hover:bg-primary-hover disabled:opacity-50">
              {mutation.isPending ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Field({ label, name, required, placeholder }: { label: string; name: string; required?: boolean; placeholder?: string }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}{required && <span className="text-red-400"> *</span>}</label>
      <input name={name} required={required} placeholder={placeholder} className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none" />
    </div>
  )
}

function SelectField({ label, name, options }: { label: string; name: string; options: [string, string][] }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}</label>
      <select name={name} className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </div>
  )
}

function DateField({ label, name }: { label: string; name: string }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}</label>
      <input type="date" name={name} className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none" />
    </div>
  )
}

const LIFESTYLE_META: Record<string, { statusHint: string; freqHint: string }> = {
  smoking:   { statusHint: '如 吸烟中、已戒烟', freqHint: '如 每日10支' },
  drinking:  { statusHint: '如 偶尔饮酒、已戒酒', freqHint: '如 每周2次' },
  exercise:  { statusHint: '如 规律运动、偶尔运动', freqHint: '如 每周3次、每次30分钟' },
  sleep:     { statusHint: '如 正常、失眠', freqHint: '如 每日7小时' },
  diet:      { statusHint: '如 均衡饮食、低盐饮食', freqHint: '如 每日3餐' },
}

function LifestyleForm() {
  const [cat, setCat] = useState('smoking')
  const meta = LIFESTYLE_META[cat] ?? { statusHint: '', freqHint: '' }
  return (
    <>
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-500">类别</label>
        <select name="category" value={cat} onChange={(e) => setCat(e.target.value)} className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none">
          <option value="smoking">吸烟</option>
          <option value="drinking">饮酒</option>
          <option value="exercise">运动</option>
          <option value="sleep">睡眠</option>
          <option value="diet">饮食</option>
        </select>
      </div>
      <Field label="状态" name="status" required placeholder={meta.statusHint} />
      <Field label="频次" name="frequency" placeholder={meta.freqHint} />
      <DateField label="记录日期" name="recorded_at" />
    </>
  )
}
