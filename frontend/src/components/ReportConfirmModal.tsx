import { useState, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi, type ExtractionResult,  } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'

const METRIC_LABELS: Record<string, string> = {
  systolic_blood_pressure: '收缩压',
  diastolic_blood_pressure: '舒张压',
  fasting_glucose: '空腹血糖',
  postmeal_glucose: '餐后血糖',
  total_cholesterol: '总胆固醇',
  triglycerides: '甘油三酯',
  ldl_cholesterol: 'LDL-C',
  hdl_cholesterol: 'HDL-C',
  heart_rate: '心率',
  weight: '体重',
}

export default function ReportConfirmModal({ onClose }: { onClose: () => void }) {
  const { currentMemberId, members } = useMemberStore()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedMetrics, setSelectedMetrics] = useState<Set<number>>(new Set())
  const [selectedDiagnoses, setSelectedDiagnoses] = useState<Set<number>>(new Set())
  const [selectedMedications, setSelectedMedications] = useState<Set<number>>(new Set())
  const [selectedLabTests, setSelectedLabTests] = useState<Set<number>>(new Set())
  const [selectedExamFindings, setSelectedExamFindings] = useState<Set<number>>(new Set())

  const extractMutation = useMutation({
    mutationFn: ({ memberId, f }: { memberId: number; f: File }) => reportsApi.extract(memberId, f),
    onSuccess: (data) => {
      setExtraction(data)
      // Default: select all
      setSelectedMetrics(new Set(data.metrics.map((_, i) => i)))
      setSelectedDiagnoses(new Set(data.diagnoses.map((_, i) => i)))
      setSelectedMedications(new Set(data.medications.map((_, i) => i)))
      setSelectedLabTests(new Set(data.lab_tests.map((_, i) => i)))
      setSelectedExamFindings(new Set(data.exam_findings.map((_, i) => i)))
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const confirmMutation = useMutation({
    mutationFn: (memberId: number) => {
      if (!extraction) throw new Error('no extraction')
      return reportsApi.confirm(memberId, {
        extraction,
        file_name: file?.name,
        keep_metric_indices: [...selectedMetrics],
        keep_diagnosis_indices: [...selectedDiagnoses],
        keep_medication_indices: [...selectedMedications],
        keep_lab_test_indices: [...selectedLabTests],
        keep_exam_finding_indices: [...selectedExamFindings],
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['metrics'] })
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['metrics-all'] })
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f || !currentMemberId) return
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
    if (!validTypes.includes(f.type)) {
      setError('仅支持 JPG/PNG/WebP/PDF')
      return
    }
    setFile(f)
    setError(null)
    extractMutation.mutate({ memberId: currentMemberId, f })
  }

  const toggle = (set: Set<number>, idx: number, setter: (s: Set<number>) => void) => {
    const next = new Set(set)
    if (next.has(idx)) next.delete(idx)
    else next.add(idx)
    setter(next)
  }

  // Detect matched member
  const matchedMember = extraction?.patient_name
    ? members.find((m) => m.name === extraction.patient_name)
    : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="max-h-[85vh] w-[600px] overflow-y-auto rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">报告导入</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>

        {!extraction && (
          <>
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={handleFileSelect} className="hidden" />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer flex-col items-center justify-center rounded-field border-2 border-dashed border-slate-200 py-12 transition hover:border-primary hover:bg-primary-light/30"
            >
              {extractMutation.isPending ? (
                <>
                  <span className="material-symbols-rounded animate-spin text-3xl text-primary">progress_activity</span>
                  <p className="mt-2 text-sm text-primary">AI 解析中...</p>
                </>
              ) : (
                <>
                  <span className="material-symbols-rounded text-3xl text-slate-300">cloud_upload</span>
                  <p className="mt-2 text-sm text-slate-500">点击上传报告图片或 PDF</p>
                  <p className="mt-1 text-xs text-slate-400">支持 JPG/PNG/WebP/PDF，最大 20MB</p>
                </>
              )}
            </div>
            {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
          </>
        )}

        {extraction && (
          <div className="space-y-4">
            {/* Report meta */}
            {(extraction.report_type || extraction.report_date || extraction.summary) && (
              <div className="rounded-field bg-slate-50 p-3">
                {extraction.report_type && <p className="text-sm font-medium text-slate-700">{extraction.report_type}</p>}
                {extraction.report_date && <p className="text-xs text-slate-400">日期: {extraction.report_date}</p>}
                {extraction.summary && <p className="mt-1 text-sm text-slate-600">{extraction.summary}</p>}
              </div>
            )}

            {/* Name attribution */}
            {extraction.patient_name && (
              <div className="flex items-center gap-2 rounded-field border border-blue-100 bg-blue-50 px-3 py-2">
                <span className="material-symbols-rounded text-blue-500 text-lg">person_search</span>
                <span className="text-sm text-slate-600">
                  识别到姓名: <span className="font-medium text-slate-800">{extraction.patient_name}</span>
                  {matchedMember ? (
                    <span className="ml-2 text-green-600">✓ 匹配到家庭成员「{matchedMember.name}」</span>
                  ) : (
                    <span className="ml-2 text-amber-600">未匹配到家庭成员，将归入当前成员</span>
                  )}
                </span>
              </div>
            )}

            {/* Metrics */}
            {extraction.metrics.length > 0 && (
              <Section title="指标数据" count={selectedMetrics.size} total={extraction.metrics.length}>
                {extraction.metrics.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedMetrics.has(i)}
                    onToggle={() => toggle(selectedMetrics, i, setSelectedMetrics)}
                    label={METRIC_LABELS[m.metric_name] || m.label}
                    value={`${m.value} ${m.unit || ''}`}
                    badge={m.is_abnormal ? { text: '异常', color: 'amber' } : undefined}
                    sub={m.reference_lower != null && m.reference_upper != null ? `参考: ${m.reference_lower}-${m.reference_upper}` : undefined}
                  />
                ))}
              </Section>
            )}

            {/* Diagnoses */}
            {extraction.diagnoses.length > 0 && (
              <Section title="诊断记录" count={selectedDiagnoses.size} total={extraction.diagnoses.length}>
                {extraction.diagnoses.map((d, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedDiagnoses.has(i)}
                    onToggle={() => toggle(selectedDiagnoses, i, setSelectedDiagnoses)}
                    label={d.disease_name}
                    badge={d.severity ? { text: d.severity, color: 'slate' } : undefined}
                    sub={d.diagnosed_date || undefined}
                  />
                ))}
              </Section>
            )}

            {/* Medications */}
            {extraction.medications.length > 0 && (
              <Section title="用药记录" count={selectedMedications.size} total={extraction.medications.length}>
                {extraction.medications.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedMedications.has(i)}
                    onToggle={() => toggle(selectedMedications, i, setSelectedMedications)}
                    label={m.drug_name}
                    value={`${m.dosage} · ${m.frequency}`}
                  />
                ))}
              </Section>
            )}

            {/* Lab tests */}
            {extraction.lab_tests.length > 0 && (
              <Section title="检验指标" count={selectedLabTests.size} total={extraction.lab_tests.length}>
                {extraction.lab_tests.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedLabTests.has(i)}
                    onToggle={() => toggle(selectedLabTests, i, setSelectedLabTests)}
                    label={m.test_name}
                    value={`${m.value} ${m.unit || ''}`}
                    sub={m.report_name}
                    badge={m.is_abnormal ? { text: '异常', color: 'amber' } : undefined}
                  />
                ))}
              </Section>
            )}

            {/* Exam findings */}
            {extraction.exam_findings.length > 0 && (
              <Section title="检查指标" count={selectedExamFindings.size} total={extraction.exam_findings.length}>
                {extraction.exam_findings.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedExamFindings.has(i)}
                    onToggle={() => toggle(selectedExamFindings, i, setSelectedExamFindings)}
                    label={m.finding_desc}
                    value={m.value_num != null ? `${m.value_num} ${m.unit || ''}` : undefined}
                    sub={m.conclusion || undefined}
                    badge={{ text: m.finding_category, color: 'amber' }}
                  />
                ))}
              </Section>
            )}

            {extraction.metrics.length === 0 && extraction.diagnoses.length === 0 && extraction.medications.length === 0 && extraction.lab_tests.length === 0 && extraction.exam_findings.length === 0 && (
              <p className="py-6 text-center text-sm text-slate-400">未从报告中提取到结构化数据</p>
            )}

            {error && <p className="text-sm text-red-500">{error}</p>}

            <div className="flex gap-3 pt-2">
              <button
                onClick={() => { setExtraction(null); setFile(null) }}
                className="flex-1 rounded-field border border-slate-200 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                重新上传
              </button>
              <button
                onClick={() => currentMemberId && confirmMutation.mutate(currentMemberId)}
                disabled={confirmMutation.isPending || (selectedMetrics.size + selectedDiagnoses.size + selectedMedications.size + selectedLabTests.size + selectedExamFindings.size === 0)}
                className="flex-1 rounded-field bg-primary py-2 text-sm text-white hover:bg-primary-hover disabled:opacity-50"
              >
                {confirmMutation.isPending ? '保存中...' : `确认入档 (${selectedMetrics.size + selectedDiagnoses.size + selectedMedications.size + selectedLabTests.size + selectedExamFindings.size})`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Section({ title, count, total, children }: { title: string; count: number; total: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-slate-700">{title}</h3>
        <span className="text-xs text-slate-400">({count}/{total} 已选)</span>
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function CheckRow({ checked, onToggle, label, value, badge, sub }: {
  checked: boolean
  onToggle: () => void
  label: string
  value?: string
  badge?: { text: string; color: 'amber' | 'slate' }
  sub?: string
}) {
  return (
    <div
      onClick={onToggle}
      className={`flex cursor-pointer items-center gap-3 rounded-field border px-3 py-2 transition ${checked ? 'border-primary bg-primary-light/30' : 'border-slate-100 bg-slate-50'}`}
    >
      <span className={`material-symbols-rounded text-lg ${checked ? 'text-primary' : 'text-slate-300'}`}>
        {checked ? 'check_box' : 'check_box_outline_blank'}
      </span>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-700">{label}</span>
          {value && <span className="text-sm text-slate-600">{value}</span>}
          {badge && (
            <span className={`rounded-full px-2 py-0.5 text-xs ${badge.color === 'amber' ? 'bg-amber-50 text-amber-600' : 'bg-slate-100 text-slate-500'}`}>
              {badge.text}
            </span>
          )}
        </div>
        {sub && <p className="text-xs text-slate-400">{sub}</p>}
      </div>
    </div>
  )
}
