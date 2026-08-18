import { useState, useEffect, useRef } from 'react'
import {
  Line, XAxis, YAxis, ResponsiveContainer, ReferenceLine, ComposedChart,
} from 'recharts'
import { visitPrepApi, type VisitPrepResponse, type MetricTrend } from '@/lib/api'
import { metricLabel } from '@/lib/api'

const DEPARTMENTS = [
  '心内科', '内分泌科', '神经内科', '呼吸科', '消化科',
  '骨科', '眼科', '皮肤科', '泌尿科', '精神心理科',
  '耳鼻喉科', '口腔科', '妇科', '急诊科', '全科', '其他',
]

const AVAILABLE_METRICS = [
  'systolic_blood_pressure', 'diastolic_blood_pressure',
  'fasting_glucose', 'postmeal_glucose', 'random_glucose',
  'heart_rate', 'weight', 'bmi',
  'total_cholesterol', 'triglycerides', 'ldl_cholesterol', 'hdl_cholesterol',
]

interface VisitPrepPanelProps {
  memberId: number
  initialComplaint?: string
  onClose: () => void
}

export default function VisitPrepPanel({ memberId, initialComplaint = '', onClose }: VisitPrepPanelProps) {
  const [phase, setPhase] = useState<'form' | 'result'>('form')
  const [complaint, setComplaint] = useState(initialComplaint)
  const [department, setDepartment] = useState('')
  const [deptReason, setDeptReason] = useState('')
  const [selectedMetrics, setSelectedMetrics] = useState<Set<string>>(new Set())
  const [result, setResult] = useState<VisitPrepResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checkedQuestions, setCheckedQuestions] = useState<Set<number>>(new Set())
  const [checkedItems, setCheckedItems] = useState<Set<number>>(new Set())
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Auto-suggest department when complaint changes
  useEffect(() => {
    if (complaint.trim().length < 2) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await visitPrepApi.suggestDepartment(memberId, complaint.trim())
        if (res.department) {
          setDepartment(res.department)
          setDeptReason(res.reason)
        }
      } catch {
        // silently fail — user can manually select
      }
    }, 500)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [complaint, memberId])

  // Auto-select metrics based on department
  useEffect(() => {
    if (!department) return
    const autoSelect = new Set<string>()
    if (['心内科', '全科', '急诊科'].includes(department)) {
      autoSelect.add('systolic_blood_pressure')
      autoSelect.add('diastolic_blood_pressure')
      autoSelect.add('heart_rate')
    }
    if (['内分泌科', '全科'].includes(department)) {
      autoSelect.add('fasting_glucose')
      autoSelect.add('postmeal_glucose')
    }
    if (['心内科', '内分泌科'].includes(department)) {
      autoSelect.add('total_cholesterol')
      autoSelect.add('triglycerides')
      autoSelect.add('ldl_cholesterol')
    }
    setSelectedMetrics(autoSelect)
  }, [department])

  const toggleMetric = (name: string) => {
    setSelectedMetrics(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const toggleQuestion = (idx: number) => {
    setCheckedQuestions(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const toggleItem = (idx: number) => {
    setCheckedItems(prev => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const handleGenerate = async () => {
    if (!complaint.trim() || !department) return
    setLoading(true)
    setError(null)
    try {
      const res = await visitPrepApi.generate(memberId, {
        chief_complaint: complaint.trim(),
        department,
        selected_metrics: [...selectedMetrics],
      })
      setResult(res)
      setPhase('result')
    } catch (err) {
      setError(err instanceof Error ? err.message : '生成失败，请重试')
    } finally {
      setLoading(false)
    }
  }

  const handlePrint = () => {
    window.print()
  }

  const handleRegenerate = () => {
    setPhase('form')
    setResult(null)
    setCheckedQuestions(new Set())
    setCheckedItems(new Set())
  }

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={(e) => { e.stopPropagation() }}
      />
      {/* Panel */}
      <div className="fixed right-0 top-0 z-50 h-full w-[480px] max-w-[90vw] overflow-y-auto bg-white shadow-2xl print:static print:w-full print:shadow-none">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3 print:hidden">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-800">
            <span className="material-symbols-rounded text-primary">medical_information</span>
            就医指导
            {phase === 'result' && result && (
              <span className="text-sm font-normal text-slate-400">— {result.department}</span>
            )}
          </h2>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>

        {/* Form Phase */}
        {phase === 'form' && (
          <div className="px-5 py-4 print:hidden">
            {/* Complaint */}
            <label className="mb-1 block text-sm font-medium text-slate-700">
              就诊主诉 <span className="text-red-500">*</span>
            </label>
            <textarea
              value={complaint}
              onChange={(e) => setComplaint(e.target.value)}
              placeholder="描述本次就医的主要原因，如「最近头晕头痛」「血糖控制不好想调药」"
              rows={3}
              className="w-full resize-none rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-400">💡 可描述症状、目的，如"调药""复查"</p>

            {/* Department */}
            <label className="mb-1 mt-4 block text-sm font-medium text-slate-700">
              建议科室 <span className="text-red-500">*</span>
            </label>
            <select
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            >
              <option value="">请选择科室</option>
              {DEPARTMENTS.map(d => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            {deptReason && department && (
              <p className="mt-1 text-xs text-slate-400">💡 {deptReason}</p>
            )}

            {/* Metrics */}
            <label className="mb-2 mt-4 block text-sm font-medium text-slate-700">
              📊 相关指标趋势（可选）
            </label>
            <div className="grid grid-cols-3 gap-2">
              {AVAILABLE_METRICS.map(name => (
                <label
                  key={name}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-field border px-2.5 py-1.5 text-xs transition ${
                    selectedMetrics.has(name)
                      ? 'border-primary bg-primary-light text-primary'
                      : 'border-slate-200 text-slate-600 hover:border-slate-300'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedMetrics.has(name)}
                    onChange={() => toggleMetric(name)}
                    className="h-3 w-3 accent-primary"
                  />
                  {metricLabel(name)}
                </label>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-slate-400">已选指标的近3个月趋势将在报告中展示</p>

            {/* Error */}
            {error && (
              <div className="mt-4 rounded-field border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                {error}
              </div>
            )}

            {/* Generate Button */}
            <button
              onClick={handleGenerate}
              disabled={!complaint.trim() || !department || loading}
              className="mt-5 w-full rounded-field bg-primary py-2.5 text-sm font-medium text-white transition hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-primary-disabled"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="material-symbols-rounded animate-spin text-base">progress_activity</span>
                  正在生成...
                </span>
              ) : '生成就医指导'}
            </button>
          </div>
        )}

        {/* Result Phase */}
        {phase === 'result' && result && (
          <div id="visit-prep-print-area" className="px-5 py-4">
            {/* Complaint & Department */}
            <div className="mb-4 rounded-field bg-slate-50 px-4 py-3">
              <div className="flex items-center gap-2 text-sm">
                <span className="text-slate-400">就诊主诉：</span>
                <span className="font-medium text-slate-700">{result.chief_complaint}</span>
              </div>
              <div className="mt-1 flex items-center gap-2 text-sm">
                <span className="text-slate-400">就诊科室：</span>
                <span className="font-medium text-slate-700">{result.department}</span>
              </div>
            </div>

            {/* Questions */}
            {result.questions.length > 0 && (
              <section className="mb-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-800">
                  <span className="material-symbols-rounded text-primary text-base">help</span>
                  一、就诊问题清单
                </h3>
                <div className="space-y-1.5">
                  {result.questions.map((q, idx) => (
                    <label
                      key={idx}
                      className={`flex cursor-pointer items-start gap-2 rounded-field border px-3 py-2 text-sm transition ${
                        checkedQuestions.has(idx)
                          ? 'border-green-200 bg-green-50 text-slate-400 line-through'
                          : 'border-slate-100 text-slate-700'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checkedQuestions.has(idx)}
                        onChange={() => toggleQuestion(idx)}
                        className="mt-0.5 h-3.5 w-3.5 accent-primary"
                      />
                      <span>{idx + 1}. {q}</span>
                    </label>
                  ))}
                </div>
              </section>
            )}

            {/* Checklist */}
            {result.checklist.length > 0 && (
              <section className="mb-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-800">
                  <span className="material-symbols-rounded text-primary text-base">checklist</span>
                  二、就诊资料清单
                </h3>
                <div className="space-y-1.5">
                  {result.checklist.map((item, idx) => (
                    <label
                      key={idx}
                      className={`flex cursor-pointer items-center gap-2 rounded-field border px-3 py-2 text-sm transition ${
                        checkedItems.has(idx)
                          ? 'border-green-200 bg-green-50 text-slate-400 line-through'
                          : 'border-slate-100 text-slate-700'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checkedItems.has(idx)}
                        onChange={() => toggleItem(idx)}
                        className="h-3.5 w-3.5 accent-primary"
                      />
                      <span className="flex-1">{item.item}</span>
                      {item.count > 0 && (
                        <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">{item.count}条</span>
                      )}
                      {item.required && (
                        <span className="rounded-full bg-red-50 px-1.5 py-0.5 text-xs text-red-500">必带</span>
                      )}
                    </label>
                  ))}
                </div>
              </section>
            )}

            {/* Summary */}
            {result.summary && (
              <section className="mb-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-800">
                  <span className="material-symbols-rounded text-primary text-base">description</span>
                  三、病情摘要（给医生看）
                </h3>
                <div className="rounded-field border border-slate-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-700">
                  {result.summary}
                </div>
              </section>
            )}

            {/* Metrics Trend */}
            {result.metrics_trend.length > 0 && (
              <section className="mb-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-800">
                  <span className="material-symbols-rounded text-primary text-base">monitoring</span>
                  四、关键指标趋势
                </h3>
                <div className="space-y-3">
                  {result.metrics_trend.map(trend => (
                    <MiniTrendChart key={trend.metric_name} trend={trend} />
                  ))}
                </div>
              </section>
            )}

            {/* Actions */}
            <div className="mt-6 flex gap-2 print:hidden">
              <button
                onClick={handleRegenerate}
                className="flex items-center gap-1.5 rounded-field border border-slate-200 px-4 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
              >
                <span className="material-symbols-rounded text-base">refresh</span>
                重新生成
              </button>
              <button
                onClick={handlePrint}
                className="flex items-center gap-1.5 rounded-field bg-primary px-4 py-2 text-sm text-white transition hover:bg-primary-hover"
              >
                <span className="material-symbols-rounded text-base">print</span>
                打印 / 导出PDF
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  )
}

function MiniTrendChart({ trend }: { trend: MetricTrend }) {
  const data = trend.records.map(r => ({ date: r.date, value: r.value }))
  const trendIcon = { up: '↑', down: '↓', flat: '→' }[trend.trend]
  const trendColor = trend.is_abnormal ? '#EF4444' : '#10B981'

  return (
    <div className="rounded-field border border-slate-100 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">{trend.label}</span>
        <span className="text-xs font-medium" style={{ color: trendColor }}>
          {trend.latest_value} {trend.unit} {trendIcon}
        </span>
      </div>
      {data.length > 1 ? (
        <ResponsiveContainer width="100%" height={80}>
          <ComposedChart data={data}>
            <XAxis dataKey="date" hide />
            <YAxis hide domain={['auto', 'auto']} />
            {trend.reference_upper && (
              <ReferenceLine y={trend.reference_upper} stroke="#94A3B8" strokeDasharray="3 3" strokeOpacity={0.4} />
            )}
            {trend.reference_lower && (
              <ReferenceLine y={trend.reference_lower} stroke="#94A3B8" strokeDasharray="3 3" strokeOpacity={0.3} />
            )}
            <Line type="monotone" dataKey="value" stroke={trendColor} strokeWidth={2} dot={{ r: 2 }} />
          </ComposedChart>
        </ResponsiveContainer>
      ) : (
        <div className="flex h-[80px] items-center justify-center text-xs text-slate-400">
          仅1条记录，无趋势图
        </div>
      )}
      {trend.reference_upper && (
        <p className="mt-1 text-xs text-slate-400">
          参考范围: {trend.reference_lower ?? '—'} ~ {trend.reference_upper} {trend.unit}
        </p>
      )}
    </div>
  )
}
