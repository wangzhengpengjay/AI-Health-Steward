import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart,
} from 'recharts'
import { metricsApi, chatApi, ApiError } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import type { MetricRecord, SourceType } from '@/types'

// ---- Metric line config ----
interface MetricLine {
  key: string
  label: string
  refLower: number
  refUpper: number
  color: string
  warningUpper: number
  criticalUpper: number
  isLowerAbnormal?: boolean
  contextOptions?: string[]  // predefined context choices for this metric
  contextLabel?: string  // label for the context field, default "备注"
}

interface MetricTab {
  label: string
  unit: string
  color: string
  lines: MetricLine[]
  bmiConfig?: { refLower: number; refUpper: number; warningUpper: number; label: string }
}

const METRIC_TABS: MetricTab[] = [
  {
    label: '血压', unit: 'mmHg', color: '#3363FF',
    lines: [
      { key: 'systolic_blood_pressure', label: '收缩压', refLower: 90, refUpper: 120, color: '#3363FF', warningUpper: 139, criticalUpper: 180, contextLabel: '测量姿势', contextOptions: ['坐位', '卧位', '站立位'] },
      { key: 'diastolic_blood_pressure', label: '舒张压', refLower: 60, refUpper: 80, color: '#5580FF', warningUpper: 89, criticalUpper: 110, contextLabel: '测量姿势', contextOptions: ['坐位', '卧位', '站立位'] },
    ],
  },
  {
    label: '血糖', unit: 'mmol/L', color: '#0891B2',
    lines: [
      { key: 'fasting_glucose', label: '空腹血糖', refLower: 3.9, refUpper: 6.1, color: '#0891B2', warningUpper: 7.0, criticalUpper: 11.1, contextLabel: '测量场景', contextOptions: ['空腹（8h以上未进食）', '餐前', '睡前'] },
      { key: 'postmeal_glucose', label: '餐后2h血糖', refLower: 3.9, refUpper: 7.8, color: '#22D3EE', warningUpper: 11.1, criticalUpper: 16.7, contextLabel: '餐后时间', contextOptions: ['餐后1h', '餐后2h', '餐后3h'] },
    ],
  },
  {
    label: '血脂', unit: 'mmol/L', color: '#059669',
    lines: [
      { key: 'total_cholesterol', label: '总胆固醇 TC', refLower: 0, refUpper: 5.2, color: '#059669', warningUpper: 6.2, criticalUpper: 0, contextLabel: '测量条件', contextOptions: ['空腹12h'] },
      { key: 'triglycerides', label: '甘油三酯 TG', refLower: 0, refUpper: 1.7, color: '#0891B2', warningUpper: 2.3, criticalUpper: 0, contextLabel: '测量条件', contextOptions: ['空腹12h'] },
      { key: 'ldl_cholesterol', label: '低密度脂蛋白 LDL-C', refLower: 0, refUpper: 3.4, color: '#E6A23C', warningUpper: 4.1, criticalUpper: 0, contextLabel: '测量条件', contextOptions: ['空腹12h'] },
      { key: 'hdl_cholesterol', label: '高密度脂蛋白 HDL-C', refLower: 1.0, refUpper: 0, color: '#3363FF', warningUpper: 0, criticalUpper: 0, isLowerAbnormal: true },
    ],
  },
  {
    label: '心率', unit: 'bpm', color: '#E6A23C',
    lines: [
      { key: 'heart_rate', label: '心率', refLower: 60, refUpper: 100, color: '#E6A23C', warningUpper: 0, criticalUpper: 0, contextLabel: '测量状态', contextOptions: ['静息', '运动后', '睡眠中'] },
    ],
  },
  {
    label: '体重/BMI', unit: 'kg', color: '#F56C6C',
    lines: [
      { key: 'weight', label: '体重', refLower: 0, refUpper: 0, color: '#F56C6C', warningUpper: 0, criticalUpper: 0 },
    ],
    bmiConfig: { refLower: 18.5, refUpper: 24.0, warningUpper: 28.0, label: 'BMI' },
  },
]

const SOURCE_LABELS: Record<string, string> = {
  manual: '手动录入',
  report: '报告导入',
  chat_extract: '聊天抽取',
}

export default function MetricInput() {
  const { currentMemberId, members } = useMemberStore()
  const [activeTab, setActiveTab] = useState(0)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [addLineKey, setAddLineKey] = useState<string>('')
  const queryClient = useQueryClient()

  const currentMember = members.find((m) => m.id === currentMemberId)
  const tab = METRIC_TABS[activeTab]

  // Fetch all metric lines' data for this tab
  const { data: allRecords = {}, isLoading } = useQuery({
    queryKey: ['metrics', currentMemberId, activeTab],
    queryFn: async () => {
      const results: Record<string, MetricRecord[]> = {}
      await Promise.all(
        tab.lines.map(async (line) => {
          try {
            const records = await metricsApi.getByName(String(currentMemberId), line.key)
            results[line.key] = records
          } catch {
            results[line.key] = []
          }
        })
      )
      return results
    },
    enabled: !!currentMemberId,
  })

  const addMutation = useMutation({
    mutationFn: (data: { metric_name: string; value: number; unit: string; measured_at: string; reference_lower?: number; reference_upper?: number; context?: string }) =>
      metricsApi.create(String(currentMemberId), { ...data, source_type: 'manual' as SourceType }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['metrics', currentMemberId] })
      setShowAddModal(false)
    },
  })

  if (!currentMemberId) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-rounded text-5xl text-slate-300">person_add</span>
          <p className="mt-3 text-slate-500">请先选择家庭成员</p>
        </div>
      </div>
    )
  }

  // Build chart data: merge all lines by date
  const allDates = new Set<string>()
  Object.values(allRecords).forEach((records) => {
    records.forEach((r) => allDates.add(r.measured_at))
  })
  const sortedDates = [...allDates].sort((a, b) => new Date(a).getTime() - new Date(b).getTime())

  const chartData = sortedDates.map((date) => {
    const point: Record<string, string | number | boolean> = {
      time: new Date(date).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }),
    }
    tab.lines.forEach((line) => {
      const records = allRecords[line.key] || []
      const record = records.find((r) => r.measured_at === date)
      if (record) {
        point[line.key] = record.value
        point[`${line.key}_abnormal`] = record.is_abnormal
      }
    })
    return point
  })

  // Compute BMI if weight tab
  let bmiValue: number | null = null
  if (tab.bmiConfig && currentMember) {
    const weightRecords = allRecords['weight'] || []
    if (weightRecords.length > 0 && currentMember.height) {
      const latestWeight = weightRecords[0].value
      const heightM = currentMember.height / 100
      bmiValue = Math.round((latestWeight / (heightM * heightM)) * 10) / 10
    }
  }

  // Count abnormals
  let totalRecords = 0
  let abnormalCount = 0
  Object.values(allRecords).forEach((records) => {
    totalRecords += records.length
    abnormalCount += records.filter((r) => r.is_abnormal).length
  })

  const handleAddClick = () => {
    setAddLineKey(tab.lines[0].key)
    setShowAddModal(true)
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-primary">monitoring</span>
          <h1 className="text-lg font-medium text-slate-800">健康指标</h1>
          {currentMember && (
            <span className="ml-2 rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary">
              {currentMember.name}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowUploadModal(true)}
            className="flex items-center gap-1.5 rounded-field border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:border-primary hover:text-primary"
          >
            <span className="material-symbols-rounded text-lg">attach_file</span>
            上传报告
          </button>
          <button
            onClick={handleAddClick}
            className="flex items-center gap-1.5 rounded-field bg-primary px-3 py-2 text-sm text-white transition hover:bg-primary-hover"
          >
            <span className="material-symbols-rounded text-lg">add</span>
            新增数据
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200 bg-white px-6">
        {METRIC_TABS.map((t, i) => (
          <button
            key={i}
            onClick={() => setActiveTab(i)}
            className={`relative px-4 py-2.5 text-sm font-medium transition ${
              activeTab === i ? 'text-primary' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {t.label}
            {activeTab === i && <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-primary" />}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto bg-bg-secondary p-6">
        {/* Summary cards */}
        <div className="mb-4 flex gap-4">
          {tab.lines.slice(0, 3).map((line) => {
            const records = allRecords[line.key] || []
            const latest = records[0]
            return (
              <div key={line.key} className="flex-1 rounded-card border border-slate-200 bg-white p-4">
                <p className="text-xs text-slate-500">{line.label}</p>
                <p className="mt-1 text-2xl font-semibold text-slate-800">
                  {latest ? latest.value : '--'}
                  <span className="ml-1 text-sm text-slate-400">{tab.unit}</span>
                </p>
                {latest && latest.is_abnormal && (
                  <span className="mt-1 inline-block rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-600">
                    {line.isLowerAbnormal ? '偏低' : '偏高'}
                  </span>
                )}
              </div>
            )
          })}
          {tab.bmiConfig && (
            <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
              <p className="text-xs text-slate-500">{tab.bmiConfig.label}</p>
              <p className="mt-1 text-2xl font-semibold text-slate-800">
                {bmiValue ?? '--'}
                <span className="ml-1 text-sm text-slate-400">kg/m²</span>
              </p>
              {bmiValue !== null && (
                <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs ${
                  bmiValue < tab.bmiConfig.refLower
                    ? 'bg-blue-50 text-blue-600'
                    : bmiValue >= tab.bmiConfig.warningUpper
                      ? 'bg-red-50 text-red-600'
                      : bmiValue >= tab.bmiConfig.refUpper
                        ? 'bg-amber-50 text-amber-600'
                        : 'bg-green-50 text-green-600'
                }`}>
                  {bmiValue < tab.bmiConfig.refLower ? '偏瘦' : bmiValue >= tab.bmiConfig.warningUpper ? '肥胖' : bmiValue >= tab.bmiConfig.refUpper ? '超重' : '正常'}
                </span>
              )}
            </div>
          )}
          <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">异常 / 总记录</p>
            <p className={`mt-1 text-2xl font-semibold ${abnormalCount > 0 ? 'text-amber-600' : 'text-green-600'}`}>
              {abnormalCount}
              <span className="ml-1 text-sm text-slate-400">/ {totalRecords}</span>
            </p>
          </div>
        </div>

        {/* Chart */}
        <div className="rounded-card border border-slate-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-medium text-slate-700">{tab.label}趋势图</h3>
          {isLoading ? (
            <div className="flex h-64 items-center justify-center">
              <span className="material-symbols-rounded animate-spin text-slate-300">progress_activity</span>
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center text-slate-400">
              <span className="material-symbols-rounded text-4xl">show_chart</span>
              <p className="mt-2 text-sm">暂无数据，点击"新增数据"或"上传报告"开始记录</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
                <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#94A3B8' }} />
                <YAxis tick={{ fontSize: 12, fill: '#94A3B8' }} />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12 }}
                  formatter={((v: unknown, name: unknown) => {
                    return [`${v} ${tab.unit}`, String(name)]
                  }) as never}
                />
                {/* Reference lines for each metric line */}
                {tab.lines.map((line) => (
                  <g key={`ref-${line.key}`}>
                    {line.refUpper > 0 && (
                      <ReferenceLine y={line.refUpper} stroke={line.color} strokeDasharray="3 3" strokeOpacity={0.4} />
                    )}
                    {line.refLower > 0 && !line.isLowerAbnormal && (
                      <ReferenceLine y={line.refLower} stroke="#67C23A" strokeDasharray="3 3" strokeOpacity={0.3} />
                    )}
                    {line.isLowerAbnormal && line.refLower > 0 && (
                      <ReferenceLine y={line.refLower} stroke="#F56C6C" strokeDasharray="3 3" strokeOpacity={0.4} label={{ value: `${line.label}下限`, fontSize: 9, fill: '#F56C6C' }} />
                    )}
                  </g>
                ))}
                {/* Lines */}
                {tab.lines.map((line) => (
                  <Line
                    key={line.key}
                    type="monotone"
                    dataKey={line.key}
                    name={line.label}
                    stroke={line.color}
                    strokeWidth={2}
                    connectNulls
                    dot={(props: { cx?: number; cy?: number; payload?: Record<string, unknown> }) => {
                      const { cx, cy, payload } = props
                      if (cx === undefined || cy === undefined) return <g key={`g-${line.key}-${cx}`} />
                      const isAbnormal = payload?.[`${line.key}_abnormal`]
                      return (
                        <circle
                          key={`dot-${line.key}-${cx}-${cy}`}
                          cx={cx}
                          cy={cy}
                          r={4}
                          fill={isAbnormal ? '#F56C6C' : line.color}
                          stroke="#fff"
                          strokeWidth={1.5}
                        />
                      )
                    }}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {/* Legend with reference ranges */}
          <div className="mt-3 flex flex-wrap gap-4">
            {tab.lines.map((line) => (
              <div key={line.key} className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: line.color }} />
                {line.label}
                {line.refUpper > 0 && !line.isLowerAbnormal && (
                  <span className="text-slate-400">({line.refLower}-{line.refUpper} {tab.unit})</span>
                )}
                {line.isLowerAbnormal && line.refLower > 0 && (
                  <span className="text-slate-400">(≥{line.refLower} {tab.unit})</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Recent records */}
        {totalRecords > 0 && (
          <div className="mt-4 rounded-card border border-slate-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-medium text-slate-700">最近记录</h3>
            <div className="space-y-2">
              {tab.lines.flatMap((line) =>
                (allRecords[line.key] || []).slice(0, 5).map((r) => (
                  <div key={`${line.key}-${r.id}`} className="flex items-center justify-between rounded-field bg-slate-50 px-3 py-2">
                    <div className="flex items-center gap-3">
                      <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: line.color }} />
                      <span className="text-xs text-slate-500">{line.label}</span>
                      <span className="text-sm font-medium text-slate-700">{r.value} {tab.unit}</span>
                      {r.is_abnormal && (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-600">
                          {line.isLowerAbnormal ? '偏低' : '偏高'}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      <span>{SOURCE_LABELS[r.source_type] || r.source_type}</span>
                      <span>{new Date(r.measured_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Add data modal */}
      {showAddModal && (
        <AddDataModal
          tab={tab}
          selectedLineKey={addLineKey}
          onSelectLine={setAddLineKey}
          onClose={() => setShowAddModal(false)}
          onSubmit={(data) => addMutation.mutate(data)}
          isLoading={addMutation.isPending}
          error={addMutation.error instanceof ApiError ? addMutation.error.message : null}
          memberHeight={currentMember?.height}
        />
      )}

      {/* Upload modal */}
      {showUploadModal && (
        <UploadModal
          memberId={Number(currentMemberId)}
          onClose={() => setShowUploadModal(false)}
        />
      )}
    </div>
  )
}

// ---- Add Data Modal ----
interface AddDataModalProps {
  tab: MetricTab
  selectedLineKey: string
  onSelectLine: (key: string) => void
  onClose: () => void
  onSubmit: (data: { metric_name: string; value: number; unit: string; measured_at: string; reference_lower?: number; reference_upper?: number; context?: string }) => void
  isLoading: boolean
  error: string | null
  memberHeight?: number  // for BMI calculation
}

function AddDataModal({ tab, selectedLineKey, onSelectLine, onClose, onSubmit, isLoading, error, memberHeight }: AddDataModalProps) {
  const [value, setValue] = useState('')
  const [height, setHeight] = useState(memberHeight?.toString() || '')
  const [measuredAt, setMeasuredAt] = useState(new Date().toISOString().slice(0, 16))
  const [context, setContext] = useState('')
  const selectedLine = tab.lines.find((l) => l.key === selectedLineKey) || tab.lines[0]
  const isWeightTab = !!tab.bmiConfig

  // Real-time BMI calculation
  const weightNum = parseFloat(value)
  const heightNum = parseFloat(height)
  const bmi = (isWeightTab && !isNaN(weightNum) && !isNaN(heightNum) && heightNum > 0)
    ? Math.round((weightNum / Math.pow(heightNum / 100, 2)) * 10) / 10
    : null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const numValue = parseFloat(value)
    if (isNaN(numValue)) return
    onSubmit({
      metric_name: selectedLine.key,
      value: numValue,
      unit: tab.unit,
      measured_at: new Date(measuredAt).toISOString(),
      reference_lower: selectedLine.refLower || undefined,
      reference_upper: selectedLine.refUpper || undefined,
      context: context || undefined,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-96 rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">新增{tab.label}数据</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Line selector if multiple */}
          {tab.lines.length > 1 && (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">指标项</label>
              <select
                value={selectedLineKey}
                onChange={(e) => onSelectLine(e.target.value)}
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              >
                {tab.lines.map((line) => (
                  <option key={line.key} value={line.key}>{line.label}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">
              {selectedLine.label} ({tab.unit})
            </label>
            <input
              type="number"
              step="0.1"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              autoFocus
              className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              placeholder={`输入${selectedLine.label}数值`}
            />
          </div>
          {/* Height input for weight/BMI tab */}
          {isWeightTab && (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">身高 (cm)</label>
              <input
                type="number"
                step="0.1"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="输入身高"
              />
            </div>
          )}
          {/* Real-time BMI display */}
          {isWeightTab && bmi !== null && tab.bmiConfig && (
            <div className="rounded-field bg-slate-50 px-3 py-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">计算 BMI</span>
                <span className="text-sm font-semibold text-slate-700">
                  {bmi} kg/m²
                  <span className={`ml-2 rounded-full px-2 py-0.5 text-xs ${
                    bmi < tab.bmiConfig.refLower
                      ? 'bg-blue-50 text-blue-600'
                      : bmi >= tab.bmiConfig.warningUpper
                        ? 'bg-red-50 text-red-600'
                        : bmi >= tab.bmiConfig.refUpper
                          ? 'bg-amber-50 text-amber-600'
                          : 'bg-green-50 text-green-600'
                  }`}>
                    {bmi < tab.bmiConfig.refLower ? '偏瘦' : bmi >= tab.bmiConfig.warningUpper ? '肥胖' : bmi >= tab.bmiConfig.refUpper ? '超重' : '正常'}
                  </span>
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                正常: {tab.bmiConfig.refLower}-{tab.bmiConfig.refUpper} | 超重: {tab.bmiConfig.refUpper}-{tab.bmiConfig.warningUpper} | 肥胖: ≥{tab.bmiConfig.warningUpper}
              </p>
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">测量时间</label>
            <input
              type="datetime-local"
              value={measuredAt}
              onChange={(e) => setMeasuredAt(e.target.value)}
              className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </div>
          {/* Context: dropdown if predefined options, free text otherwise */}
          {selectedLine.contextOptions ? (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {selectedLine.contextLabel || '备注'} (可选)
              </label>
              <select
                value={context}
                onChange={(e) => setContext(e.target.value)}
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              >
                <option value="">请选择</option>
                {selectedLine.contextOptions.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">备注 (可选)</label>
              <input
                type="text"
                value={context}
                onChange={(e) => setContext(e.target.value)}
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="输入备注信息"
              />
            </div>
          )}
          {/* Reference range hint */}
          {selectedLine.refUpper > 0 && !selectedLine.isLowerAbnormal && (
            <p className="text-xs text-slate-400">参考范围: {selectedLine.refLower}-{selectedLine.refUpper} {tab.unit}</p>
          )}
          {selectedLine.isLowerAbnormal && selectedLine.refLower > 0 && (
            <p className="text-xs text-slate-400">正常范围: ≥{selectedLine.refLower} {tab.unit}（偏低为异常）</p>
          )}
          {error && <p className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-field border border-slate-200 py-2 text-sm text-slate-600 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={isLoading || !value}
              className="flex-1 rounded-field bg-primary py-2 text-sm text-white hover:bg-primary-hover disabled:opacity-50"
            >
              {isLoading ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ---- Upload Modal ----
interface UploadModalProps {
  memberId: number
  onClose: () => void
}

function UploadModal({ memberId, onClose }: UploadModalProps) {
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [message, setMessage] = useState('请帮我解读这份报告并提取指标数据')
  const [result, setResult] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
    if (!validTypes.includes(f.type)) {
      setError('仅支持 JPG/PNG/WebP/PDF')
      return
    }
    setFile(f)
    setError(null)
    if (f.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(f))
    } else {
      setPreviewUrl(null)
    }
  }

  const handleSubmit = async () => {
    if (!file) return
    setIsLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await chatApi.send(memberId, message, file)
      setResult(res.reply)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 服务暂时不可用')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="max-h-[85vh] w-[480px] overflow-y-auto rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">上传报告</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>

        {!result && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              onChange={handleFileSelect}
              className="hidden"
            />
            <div
              onClick={() => fileInputRef.current?.click()}
              className="mb-4 flex cursor-pointer flex-col items-center justify-center rounded-field border-2 border-dashed border-slate-200 py-8 transition hover:border-primary hover:bg-primary-light/30"
            >
              {previewUrl ? (
                <img src={previewUrl} alt="预览" className="max-h-32 rounded-field object-contain" />
              ) : file ? (
                <div className="flex items-center gap-2 text-slate-600">
                  <span className="material-symbols-rounded">description</span>
                  <span className="text-sm">{file.name}</span>
                </div>
              ) : (
                <>
                  <span className="material-symbols-rounded text-3xl text-slate-300">cloud_upload</span>
                  <p className="mt-2 text-sm text-slate-500">点击选择图片或 PDF</p>
                  <p className="mt-1 text-xs text-slate-400">支持 JPG/PNG/WebP/PDF，最大 20MB</p>
                </>
              )}
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium text-slate-500">解读要求 (可选)</label>
              <input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              />
            </div>

            {error && <p className="mb-3 text-sm text-red-500">{error}</p>}

            <button
              onClick={handleSubmit}
              disabled={!file || isLoading}
              className="w-full rounded-field bg-primary py-2.5 text-sm text-white hover:bg-primary-hover disabled:opacity-50"
            >
              {isLoading ? 'AI 解读中...' : '上传并解读'}
            </button>
          </>
        )}

        {result && (
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm text-green-600">
              <span className="material-symbols-rounded">check_circle</span>
              AI 解读完成
            </div>
            <div className="prose prose-sm max-w-none rounded-field bg-slate-50 p-4">
              <div className="whitespace-pre-wrap text-sm text-slate-700">{result}</div>
            </div>
            <button
              onClick={onClose}
              className="mt-4 w-full rounded-field bg-primary py-2 text-sm text-white hover:bg-primary-hover"
            >
              完成
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
