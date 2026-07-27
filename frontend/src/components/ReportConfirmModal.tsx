import { useState, useRef, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi, type ReportRecord } from '@/lib/api'
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

interface Props {
  /** When provided: viewing/confirming an existing report record */
  report?: ReportRecord
  /** When provided without report: direct upload mode (from MetricInput) */
  uploadSource?: string
  onClose: () => void
}

export default function ReportConfirmModal({ report, uploadSource = 'metric_input', onClose }: Props) {
  const { currentMemberId, members } = useMemberStore()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // If report is provided, use its extraction; otherwise upload mode
  const [currentReport, setCurrentReport] = useState<ReportRecord | null>(report || null)
  const [error, setError] = useState<string | null>(null)

  // Selection state
  const extraction = currentReport?.extraction || null
  const [selectedMetrics, setSelectedMetrics] = useState<Set<number>>(new Set())
  const [selectedDiagnoses, setSelectedDiagnoses] = useState<Set<number>>(new Set())
  const [selectedMedications, setSelectedMedications] = useState<Set<number>>(new Set())
  const [selectedLabTests, setSelectedLabTests] = useState<Set<number>>(new Set())
  const [selectedExamFindings, setSelectedExamFindings] = useState<Set<number>>(new Set())

  // Initialize selections when extraction becomes available
  useEffect(() => {
    if (extraction) {
      setSelectedMetrics(new Set(extraction.metrics.map((_, i) => i)))
      setSelectedDiagnoses(new Set(extraction.diagnoses.map((_, i) => i)))
      setSelectedMedications(new Set(extraction.medications.map((_, i) => i)))
      setSelectedLabTests(new Set(extraction.lab_tests.map((_, i) => i)))
      setSelectedExamFindings(new Set(extraction.exam_findings.map((_, i) => i)))
    }
  }, [currentReport?.id])

  const uploadMutation = useMutation({
    mutationFn: ({ memberId, file }: { memberId: number; file: File }) =>
      reportsApi.upload(memberId, file, uploadSource),
    onSuccess: (data) => {
      setCurrentReport(data)
      setError(null)
    },
    onError: (err: Error) => setError(err.message),
  })

  const confirmMutation = useMutation({
    mutationFn: (memberId: number) => {
      if (!currentReport || !extraction) throw new Error('no extraction')
      return reportsApi.confirm(memberId, currentReport.id, {
        extraction,
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
      queryClient.invalidateQueries({ queryKey: ['reports'] })
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
    setError(null)
    uploadMutation.mutate({ memberId: Number(currentMemberId), file: f })
  }

  const toggle = (set: Set<number>, idx: number, setter: (s: Set<number>) => void) => {
    const next = new Set(set)
    if (next.has(idx)) next.delete(idx)
    else next.add(idx)
    setter(next)
  }

  const isArchived = currentReport?.status === 'archived'
  const matchedMember = extraction?.patient_name
    ? members.find((m) => m.name === extraction.patient_name)
    : null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="max-h-[85vh] w-[600px] overflow-y-auto rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">
            {isArchived ? '报告详情' : currentReport ? '确认入档' : '报告导入'}
          </h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>

        {/* Upload zone (only in direct upload mode without report) */}
        {!currentReport && (
          <>
            <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={handleFileSelect} className="hidden" />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="flex cursor-pointer flex-col items-center justify-center rounded-field border-2 border-dashed border-slate-200 py-12 transition hover:border-primary hover:bg-primary-light/30"
            >
              {uploadMutation.isPending ? (
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

        {/* Extraction results */}
        {currentReport && extraction && (
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

            {/* Archived stats */}
            {isArchived && (
              <div className="flex flex-wrap gap-2 text-xs">
                {currentReport.saved_metrics > 0 && <span className="rounded-full bg-green-50 px-2 py-0.5 text-green-600">指标 {currentReport.saved_metrics}</span>}
                {currentReport.saved_lab_tests > 0 && <span className="rounded-full bg-green-50 px-2 py-0.5 text-green-600">检验 {currentReport.saved_lab_tests}</span>}
                {currentReport.saved_exam_findings > 0 && <span className="rounded-full bg-green-50 px-2 py-0.5 text-green-600">检查 {currentReport.saved_exam_findings}</span>}
                {currentReport.saved_diagnoses > 0 && <span className="rounded-full bg-green-50 px-2 py-0.5 text-green-600">诊断 {currentReport.saved_diagnoses}</span>}
                {currentReport.saved_medications > 0 && <span className="rounded-full bg-green-50 px-2 py-0.5 text-green-600">用药 {currentReport.saved_medications}</span>}
              </div>
            )}

            {/* Metrics */}
            {extraction.metrics.length > 0 && (
              <Section title="指标数据" count={selectedMetrics.size} total={extraction.metrics.length} readonly={isArchived}>
                {extraction.metrics.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedMetrics.has(i)}
                    onToggle={() => !isArchived && toggle(selectedMetrics, i, setSelectedMetrics)}
                    label={METRIC_LABELS[m.metric_name] || m.label}
                    value={`${m.value} ${m.unit || ''}`}
                    badge={m.is_abnormal ? { text: '异常', color: 'amber' } : undefined}
                    sub={m.reference_lower != null && m.reference_upper != null ? `参考: ${m.reference_lower}-${m.reference_upper}` : undefined}
                    readonly={isArchived}
                  />
                ))}
              </Section>
            )}

            {/* Diagnoses */}
            {extraction.diagnoses.length > 0 && (
              <Section title="诊断记录" count={selectedDiagnoses.size} total={extraction.diagnoses.length} readonly={isArchived}>
                {extraction.diagnoses.map((d, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedDiagnoses.has(i)}
                    onToggle={() => !isArchived && toggle(selectedDiagnoses, i, setSelectedDiagnoses)}
                    label={d.disease_name}
                    badge={d.severity ? { text: d.severity, color: 'slate' } : undefined}
                    sub={d.diagnosed_date || undefined}
                    readonly={isArchived}
                  />
                ))}
              </Section>
            )}

            {/* Medications */}
            {extraction.medications.length > 0 && (
              <Section title="用药记录" count={selectedMedications.size} total={extraction.medications.length} readonly={isArchived}>
                {extraction.medications.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedMedications.has(i)}
                    onToggle={() => !isArchived && toggle(selectedMedications, i, setSelectedMedications)}
                    label={m.drug_name}
                    value={`${m.dosage} · ${m.frequency}`}
                    readonly={isArchived}
                  />
                ))}
              </Section>
            )}

            {/* Lab tests */}
            {extraction.lab_tests.length > 0 && (
              <Section title="检验指标" count={selectedLabTests.size} total={extraction.lab_tests.length} readonly={isArchived}>
                {extraction.lab_tests.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedLabTests.has(i)}
                    onToggle={() => !isArchived && toggle(selectedLabTests, i, setSelectedLabTests)}
                    label={m.test_name}
                    value={`${m.value} ${m.unit || ''}`}
                    sub={m.report_name}
                    badge={m.is_abnormal ? { text: '异常', color: 'amber' } : undefined}
                    readonly={isArchived}
                  />
                ))}
              </Section>
            )}

            {/* Exam findings */}
            {extraction.exam_findings.length > 0 && (
              <Section title="检查指标" count={selectedExamFindings.size} total={extraction.exam_findings.length} readonly={isArchived}>
                {extraction.exam_findings.map((m, i) => (
                  <CheckRow
                    key={i}
                    checked={selectedExamFindings.has(i)}
                    onToggle={() => !isArchived && toggle(selectedExamFindings, i, setSelectedExamFindings)}
                    label={m.finding_desc}
                    value={m.value_num != null ? `${m.value_num} ${m.unit || ''}` : undefined}
                    sub={m.conclusion || undefined}
                    badge={{ text: m.finding_category, color: 'amber' }}
                    readonly={isArchived}
                  />
                ))}
              </Section>
            )}

            {extraction.metrics.length === 0 && extraction.diagnoses.length === 0 && extraction.medications.length === 0 && extraction.lab_tests.length === 0 && extraction.exam_findings.length === 0 && (
              <p className="py-6 text-center text-sm text-slate-400">未从报告中提取到结构化数据</p>
            )}

            {error && <p className="text-sm text-red-500">{error}</p>}

            {/* Actions */}
            {!isArchived && (
              <div className="flex gap-3 pt-2">
                {!report && (
                  <button
                    onClick={() => { setCurrentReport(null); }}
                    className="flex-1 rounded-field border border-slate-200 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  >
                    重新上传
                  </button>
                )}
                <button
                  onClick={() => currentMemberId && confirmMutation.mutate(Number(currentMemberId))}
                  disabled={confirmMutation.isPending || (selectedMetrics.size + selectedDiagnoses.size + selectedMedications.size + selectedLabTests.size + selectedExamFindings.size === 0)}
                  className="flex-1 rounded-field bg-primary py-2 text-sm text-white hover:bg-primary-hover disabled:opacity-50"
                >
                  {confirmMutation.isPending ? '保存中...' : `确认入档 (${selectedMetrics.size + selectedDiagnoses.size + selectedMedications.size + selectedLabTests.size + selectedExamFindings.size})`}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Section({ title, count, total, readonly, children }: { title: string; count: number; total: number; readonly?: boolean; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="text-sm font-medium text-slate-700">{title}</h3>
        {!readonly && <span className="text-xs text-slate-400">({count}/{total} 已选)</span>}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  )
}

function CheckRow({ checked, onToggle, label, value, badge, sub, readonly }: {
  checked: boolean
  onToggle: () => void
  label: string
  value?: string
  badge?: { text: string; color: 'amber' | 'slate' }
  sub?: string
  readonly?: boolean
}) {
  return (
    <div
      onClick={readonly ? undefined : onToggle}
      className={`flex items-center gap-3 rounded-field border px-3 py-2 transition ${readonly ? 'cursor-default border-slate-100 bg-slate-50' : 'cursor-pointer'} ${checked && !readonly ? 'border-primary bg-primary-light/30' : 'border-slate-100 bg-slate-50'}`}
    >
      {!readonly && (
        <span className={`material-symbols-rounded text-lg ${checked ? 'text-primary' : 'text-slate-300'}`}>
          {checked ? 'check_box' : 'check_box_outline_blank'}
        </span>
      )}
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
