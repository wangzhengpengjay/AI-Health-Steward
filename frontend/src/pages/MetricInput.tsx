import { useState, useMemo } from 'react'
import ReportConfirmModal from '@/components/ReportConfirmModal'
import { ExamTimeline, LabTabContent, SOURCE_LABELS } from '@/components/MetricViews'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart,
} from 'recharts'
import { membersApi, metricsApi, ApiError } from '@/lib/api'
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
  mergeLines?: boolean
  groupInput?: boolean  // when true, all lines are entered together (e.g., blood pressure systolic+diastolic)
}

interface DynamicTab {
  type: 'lab' | 'exam'
  label: string
  unit: string
  color?: string
  lines: { key: string; label: string; refLower: number; refUpper: number; color: string; warningUpper: number; criticalUpper: number; isLowerAbnormal?: boolean; contextOptions?: string[]; contextLabel?: string }[]
  bmiConfig?: { refLower: number; refUpper: number; warningUpper: number; label: string }
  mergeLines?: boolean
  groupInput?: boolean
}

const METRIC_TABS: MetricTab[] = [
  {
    label: '血压', unit: 'mmHg', color: '#3363FF', groupInput: true,
    lines: [
      { key: 'systolic_blood_pressure', label: '收缩压', refLower: 90, refUpper: 120, color: '#3363FF', warningUpper: 139, criticalUpper: 180, contextLabel: '测量姿势', contextOptions: ['坐位', '卧位', '站立位'] },
      { key: 'diastolic_blood_pressure', label: '舒张压', refLower: 60, refUpper: 80, color: '#5580FF', warningUpper: 89, criticalUpper: 110, contextLabel: '测量姿势', contextOptions: ['坐位', '卧位', '站立位'] },
    ],
  },
  {
    label: '血糖', unit: 'mmol/L', color: '#0891B2', mergeLines: true,
    lines: [
      { key: 'fasting_glucose', label: '空腹血糖', refLower: 3.9, refUpper: 6.1, color: '#0891B2', warningUpper: 7.0, criticalUpper: 11.1 },
      { key: 'postmeal_glucose', label: '餐后2h血糖', refLower: 3.9, refUpper: 7.8, color: '#22D3EE', warningUpper: 11.1, criticalUpper: 16.7 },
      { key: 'random_glucose', label: '随机血糖', refLower: 3.9, refUpper: 11.1, color: '#06B6D4', warningUpper: 11.1, criticalUpper: 16.7 },
      { key: 'postmeal_1h_glucose', label: '餐后1h血糖', refLower: 3.9, refUpper: 8.9, color: '#14B8A6', warningUpper: 11.1, criticalUpper: 16.7 },
      { key: 'bedtime_glucose', label: '睡前血糖', refLower: 3.9, refUpper: 8.0, color: '#0EA5E9', warningUpper: 10.0, criticalUpper: 16.7 },
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

// Get local datetime string for <input type="datetime-local">
function localDatetimeStr(d: Date = new Date()): string {
  const off = d.getTimezoneOffset() * 60000
  return new Date(d.getTime() - off).toISOString().slice(0, 16)
}

export default function MetricInput() {
  const { currentMemberId, members } = useMemberStore()
  const [activeTab, setActiveTab] = useState(0)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showReportModal, setShowReportModal] = useState(false)
  const [addLineKey, setAddLineKey] = useState<string>('')
  const [editRecord, setEditRecord] = useState<{ groupTs?: string; lineKey?: string; record?: MetricRecord } | null>(null)
  const queryClient = useQueryClient()

  const currentMember = members.find((m) => m.id === currentMemberId)

  // Fetch all metrics for dynamic tabs
  const { data: allMemberMetrics = [] } = useQuery({
    queryKey: ['metrics', currentMemberId, 'all'],
    queryFn: () => metricsApi.list(Number(currentMemberId)),
    enabled: !!currentMemberId,
  })

  // Build dynamic tabs: lab:* grouped by report_name, exam:* grouped by category
  const dynamicTabs = useMemo(() => {
    const labReports: Record<string, string[]> = {}  // report_name -> test_names
    const examCategories: Record<string, string[]> = {}  // category -> items
    for (const r of allMemberMetrics) {
      if (r.metric_name.startsWith('lab:')) {
        const parts = r.metric_name.split(':')
        const reportName = parts[1] || '检验报告'
        const testName = parts[2] || '指标'
        if (!labReports[reportName]) labReports[reportName] = []
        if (!labReports[reportName].includes(testName)) labReports[reportName].push(testName)
      } else if (r.metric_name.startsWith('exam:')) {
        const parts = r.metric_name.split(':')
        const category = parts[1] || '检查发现'
        const item = parts[2] || '结果'
        if (!examCategories[category]) examCategories[category] = []
        if (!examCategories[category].includes(item)) examCategories[category].push(item)
      }
    }
    const tabs: DynamicTab[] = []
    for (const [reportName, testNames] of Object.entries(labReports)) {
      tabs.push({
        type: 'lab',
        label: reportName,
        unit: '',
        lines: testNames.map(tn => ({
          key: `lab:${reportName}:${tn}`,
          label: tn,
          refLower: 0, refUpper: 0, color: '#059669', warningUpper: 0, criticalUpper: 0,
        })),
      })
    }
    for (const [category, items] of Object.entries(examCategories)) {
      tabs.push({
        type: 'exam',
        label: category,
        unit: '',
        lines: items.map(item => ({
          key: `exam:${category}:${item}`,
          label: item,
          refLower: 0, refUpper: 0, color: '#E6A23C', warningUpper: 0, criticalUpper: 0,
        })),
      })
    }
    return tabs
  }, [allMemberMetrics])

  const allTabs = [...METRIC_TABS, ...dynamicTabs]
  const tab: MetricTab | DynamicTab = allTabs[activeTab] || METRIC_TABS[0]

  // Fetch all metric lines' data for this tab
  const { data: allRecords = {}, isLoading } = useQuery({
    queryKey: ['metrics', currentMemberId, activeTab],
    queryFn: async () => {
      const results: Record<string, MetricRecord[]> = {}
      // For dynamic tabs, filter from allMemberMetrics
      if ('type' in tab && (tab.type === 'lab' || tab.type === 'exam')) {
        for (const line of tab.lines) {
          results[line.key] = allMemberMetrics.filter(r => r.metric_name === line.key)
        }
      } else {
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
        // For weight/BMI tab, also fetch bmi records for the chart
        if (tab.bmiConfig) {
          try {
            results['bmi'] = await metricsApi.getByName(String(currentMemberId), 'bmi')
          } catch {
            results['bmi'] = []
          }
        }
      }
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

  const updateMutation = useMutation({
    mutationFn: (data: { id: number; value: number; measured_at: string; context?: string }) =>
      metricsApi.update(data.id, { value: data.value, measured_at: data.measured_at, context: data.context }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['metrics', currentMemberId] })
      setEditRecord(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => metricsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['metrics', currentMemberId] })
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
    if (tab.mergeLines) {
      // Merge all sub-lines into one series, pick first match at this timestamp
      for (const line of tab.lines) {
        const records = allRecords[line.key] || []
        const record = records.find((r) => r.measured_at === date)
        if (record) {
          point['value'] = record.value
          point['value_abnormal'] = record.is_abnormal
          point['type'] = line.label
          break
        }
      }
    } else {
      tab.lines.forEach((line) => {
        // For weight/BMI tab, use bmi records for the chart
        const chartKey = tab.bmiConfig ? "bmi" : line.key
        const records = allRecords[chartKey] || []
        const record = records.find((r) => r.measured_at === date)
        if (record) {
          point[line.key] = record.value
          point[`${line.key}_abnormal`] = record.is_abnormal
        }
      })
    }
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

  // Count records: for group tabs, count by unique timestamp (one group = one record)
  let totalRecords = 0
  let abnormalCount = 0
  if (tab.groupInput) {
    const timestamps = new Set<string>()
    tab.lines.forEach((line) => {
      (allRecords[line.key] || []).forEach((r) => timestamps.add(r.measured_at))
    })
    totalRecords = timestamps.size
    // Abnormal if any line in the group is abnormal
    abnormalCount = [...timestamps].filter((ts) =>
      tab.lines.some((line) => {
        const r = (allRecords[line.key] || []).find((rec) => rec.measured_at === ts)
        return r?.is_abnormal
      })
    ).length
  } else {
    Object.values(allRecords).forEach((records) => {
      totalRecords += records.length
      abnormalCount += records.filter((r) => r.is_abnormal).length
    })
  }

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
            onClick={() => setShowReportModal(true)}
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
        {allTabs.map((t, i) => (
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
        {/* Lab tab: per-test charts */}
        {'type' in tab && tab.type === 'lab' && <LabTabContent allRecords={allRecords} tabLabel={tab.label} />}

        {/* Summary cards (skip for exam/lab tabs) */}
        {'type' in tab && (tab.type === 'exam' || tab.type === 'lab') ? null : (
        <div className="mb-4 flex gap-4">
          {tab.groupInput ? (
            // Group display: e.g., blood pressure shows "125/80 mmHg"
            <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
              <p className="text-xs text-slate-500">{tab.label}</p>
              <p className="mt-1 text-2xl font-semibold text-slate-800">
                {tab.lines.map((line) => {
                  const records = allRecords[line.key] || []
                  return records[0]?.text_value ?? records[0]?.value ?? '--'
                }).join(' / ')}
                <span className="ml-1 text-sm text-slate-400">{tab.unit}</span>
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                {tab.lines.map((line) => {
                  const records = allRecords[line.key] || []
                  const latest = records[0]
                  if (!latest || !latest.is_abnormal) return null
                  return (
                    <span key={line.key} className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-600">
                      {line.label}{line.isLowerAbnormal ? '偏低' : '偏高'}
                    </span>
                  )
                })}
              </div>
            </div>
          ) : (
            // Individual display: one card per line
            tab.lines.slice(0, 3).map((line) => {
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
            })
          )}
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
        )}

        {/* Chart or Timeline (skip for lab) */}
        {'type' in tab && tab.type === 'lab' ? null : (
        <div className="rounded-card border border-slate-200 bg-white p-6">
          {'type' in tab && tab.type === 'exam' ? (
            <ExamTimeline allRecords={allRecords} tabLabel={tab.label} />
          ) : (
          <>
          <h3 className="mb-4 text-sm font-medium text-slate-700">{tab.bmiConfig ? 'BMI' : tab.label}趋势图</h3>
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
                    const unit = tab.bmiConfig ? 'kg/m²' : tab.unit
                    const label = tab.bmiConfig ? 'BMI' : String(name)
                    return [`${v} ${unit}`, label]
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
                {tab.mergeLines ? (
                  <Line
                    type="monotone"
                    dataKey="value"
                    name={tab.label}
                    stroke={tab.color}
                    strokeWidth={2}
                    connectNulls
                    dot={(props: { cx?: number; cy?: number; payload?: Record<string, unknown> }) => {
                      const { cx, cy, payload } = props
                      if (cx === undefined || cy === undefined) return <g key={`g-merge-${cx}`} />
                      const isAbnormal = payload?.['value_abnormal']
                      return (
                        <circle
                          key={`dot-merge-${cx}-${cy}`}
                          cx={cx}
                          cy={cy}
                          r={4}
                          fill={isAbnormal ? '#F56C6C' : tab.color}
                          stroke="#fff"
                          strokeWidth={1.5}
                        />
                      )
                    }}
                  />
                ) : (
                  tab.lines.map((line) => {
                  return (
                  <Line
                    key={line.key}
                    type="monotone"
                    dataKey={line.key}
                    name={tab.bmiConfig ? 'BMI' : line.label}
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
                  )
                })
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {/* Legend with reference ranges */}
          <div className="mt-3 flex flex-wrap gap-4">
            {tab.mergeLines ? (
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: tab.color }} />
                {tab.label}
                <span className="text-slate-400">({tab.lines.map(l => l.label).join('/')})</span>
              </div>
            ) : (
              tab.lines.map((line) => {
              const isBmi = !!tab.bmiConfig
              const label = isBmi ? 'BMI' : line.label
              const unit = isBmi ? 'kg/m²' : tab.unit
              const lo = isBmi ? tab.bmiConfig!.refLower : line.refLower
              const hi = isBmi ? tab.bmiConfig!.refUpper : line.refUpper
              return (
              <div key={line.key} className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: line.color }} />
                {label}
                {hi > 0 && !line.isLowerAbnormal && (
                  <span className="text-slate-400">({lo}-{hi} {unit})</span>
                )}
                {line.isLowerAbnormal && lo > 0 && (
                  <span className="text-slate-400">(≥{lo} {unit})</span>
                )}
              </div>
              )
            })
            )}
          </div>
          </>
          )}
        </div>
        )}

        {/* Recent records (skip for exam/lab tabs) */}
        {'type' in tab && (tab.type === 'exam' || tab.type === 'lab') ? null : totalRecords > 0 && (
          <div className="mt-4 rounded-card border border-slate-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-medium text-slate-700">最近记录</h3>
            <div className="space-y-2">
              {tab.groupInput ? (
                // Group records: merge by measured_at, show all lines together
                (() => {
                  // Collect all unique timestamps from all lines
                  const timestamps = new Set<string>()
                  tab.lines.forEach((line) => {
                    (allRecords[line.key] || []).forEach((r) => timestamps.add(r.measured_at))
                  })
                  return [...timestamps]
                    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())
                    .slice(0, 10)
                    .map((ts) => {
                      const parts = tab.lines.map((line) => {
                        const r = (allRecords[line.key] || []).find((rec) => rec.measured_at === ts)
                        return { line, record: r }
                      })
                      const firstRecord = parts.find((p) => p.record)?.record
                      return (
                        <div key={ts} className="flex items-center justify-between rounded-field bg-slate-50 px-3 py-2">
                          <div className="flex items-center gap-2">
                            {parts.map(({ line, record }) => (
                              <div key={line.key} className="flex items-center gap-1.5">
                                <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: line.color }} />
                                <span className="text-xs text-slate-500">{line.label}</span>
                                <span className="text-sm font-medium text-slate-700">
                                  {record ? (record.text_value || record.value) : '--'}
                                </span>
                                {record && record.is_abnormal && (
                                  <span className="rounded-full bg-amber-50 px-1.5 py-0.5 text-xs text-amber-600">
                                    {line.isLowerAbnormal ? '偏低' : '偏高'}
                                  </span>
                                )}
                              </div>
                            ))}
                          </div>
                          <div className="flex items-center gap-3">
                            <div className="flex items-center gap-2 text-xs text-slate-400">
                              {firstRecord && <span>{SOURCE_LABELS[firstRecord.source_type] || firstRecord.source_type}</span>}
                              <span>{new Date(ts).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            </div>
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => setEditRecord({ groupTs: ts })}
                                className="rounded p-1 text-slate-400 transition hover:bg-slate-200 hover:text-primary"
                                title="编辑"
                              >
                                <span className="material-symbols-rounded text-base">edit</span>
                              </button>
                              <button
                                onClick={() => {
                                  if (confirm('确认删除该组记录？')) {
                                    parts.forEach(({ record }) => {
                                      if (record) deleteMutation.mutate(record.id)
                                    })
                                  }
                                }}
                                className="rounded p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-500"
                                title="删除"
                              >
                                <span className="material-symbols-rounded text-base">delete</span>
                              </button>
                            </div>
                          </div>
                        </div>
                      )
                    })
                })()
              ) : (
                // Individual records
                tab.lines.flatMap((line) =>
                  (allRecords[line.key] || []).slice(0, 10).map((r) => (
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
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2 text-xs text-slate-400">
                          <span>{SOURCE_LABELS[r.source_type] || r.source_type}</span>
                          <span>{new Date(r.measured_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => setEditRecord({ lineKey: line.key, record: r })}
                            className="rounded p-1 text-slate-400 transition hover:bg-slate-200 hover:text-primary"
                            title="编辑"
                          >
                            <span className="material-symbols-rounded text-base">edit</span>
                          </button>
                          <button
                            onClick={() => {
                              if (confirm('确认删除该记录？')) deleteMutation.mutate(r.id)
                            }}
                            className="rounded p-1 text-slate-400 transition hover:bg-red-50 hover:text-red-500"
                            title="删除"
                          >
                            <span className="material-symbols-rounded text-base">delete</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ))
                )
              )}
            </div>
          </div>
        )}
      </div>

      {/* Add data modal */}
      {showAddModal && (
        <AddDataModal
          tab={tab as MetricTab}
          selectedLineKey={addLineKey}
          onSelectLine={setAddLineKey}
          onClose={() => setShowAddModal(false)}
          onSubmit={(entries, heightValue) => {
            // Submit all entries sequentially (group input may have multiple)
            entries.forEach((data) => addMutation.mutate(data))
            // Update member height if provided (weight tab)
            if (heightValue && currentMemberId) {
              membersApi.update(Number(currentMemberId), { height: heightValue })
                .then(() => queryClient.invalidateQueries({ queryKey: ['members'] }))
            }
          }}
          isLoading={addMutation.isPending}
          error={addMutation.error instanceof ApiError ? addMutation.error.message : null}
          memberHeight={currentMember?.height}
        />
      )}

      {/* Edit modal */}
      {editRecord && (
        <EditModal
          tab={tab as MetricTab}
          editData={editRecord}
          allRecords={allRecords}
          onClose={() => setEditRecord(null)}
          onSubmit={(entries) => {
            entries.forEach((e) => updateMutation.mutate(e))
          }}
          isLoading={updateMutation.isPending}
        />
      )}

     {/* Upload modal */}
     {showReportModal && (
       <ReportConfirmModal
         onClose={() => setShowReportModal(false)}
         
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
  onSubmit: (data: { metric_name: string; value: number; unit: string; measured_at: string; reference_lower?: number; reference_upper?: number; context?: string }[], heightValue?: number) => void
  isLoading: boolean
  error: string | null
  memberHeight?: number  // for BMI calculation
}

function AddDataModal({ tab, selectedLineKey, onSelectLine, onClose, onSubmit, isLoading, error, memberHeight }: AddDataModalProps) {
  const isGroup = !!tab.groupInput
  const isWeightTab = !!tab.bmiConfig
  const selectedLine = tab.lines.find((l) => l.key === selectedLineKey) || tab.lines[0]

  // For group input: one value per line
  const [groupValues, setGroupValues] = useState<Record<string, string>>({})
  // For single input
  const [value, setValue] = useState('')
  const [height, setHeight] = useState(memberHeight?.toString() || '')
  const [measuredAt, setMeasuredAt] = useState(localDatetimeStr())
  const [context, setContext] = useState('')

  // Real-time BMI calculation
  const weightNum = parseFloat(value)
  const heightNum = parseFloat(height)
  const bmi = (isWeightTab && !isNaN(weightNum) && !isNaN(heightNum) && heightNum > 0)
    ? Math.round((weightNum / Math.pow(heightNum / 100, 2)) * 10) / 10
    : null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const isoTime = measuredAt + ':00+08:00'
    if (isGroup) {
      // Submit all lines together with the same timestamp
      const entries = tab.lines
        .map((line) => {
          const v = parseFloat(groupValues[line.key] || '')
          if (isNaN(v)) return null
          return {
            metric_name: line.key,
            value: v,
            unit: tab.unit,
            measured_at: isoTime,
            reference_lower: line.refLower || undefined,
            reference_upper: line.refUpper || undefined,
            context: context || undefined,
          }
        })
        .filter((e): e is NonNullable<typeof e> => e !== null)
      if (entries.length === 0) return
      onSubmit(entries)
    } else {
      const numValue = parseFloat(value)
      if (isNaN(numValue)) return
      const entries: { metric_name: string; value: number; unit: string; measured_at: string; reference_lower?: number; reference_upper?: number; context?: string }[] = [{
        metric_name: selectedLine.key,
        value: numValue,
        unit: tab.unit,
        measured_at: isoTime,
        reference_lower: selectedLine.refLower || undefined,
        reference_upper: selectedLine.refUpper || undefined,
        context: context || undefined,
      }]
      // Auto-add BMI record for weight tab when height is available
      if (isWeightTab && bmi !== null) {
        entries.push({
          metric_name: 'bmi',
          value: bmi,
          unit: '',
          measured_at: isoTime,
          reference_lower: 18.5,
          reference_upper: 24.0,
          context: '自动计算',
        })
      }
      onSubmit(entries, isWeightTab ? heightNum : undefined)
    }
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
          {/* Group input: show all lines at once (e.g., systolic + diastolic) */}
          {isGroup ? (
            <div className="grid grid-cols-2 gap-3">
              {tab.lines.map((line) => (
                <div key={line.key}>
                  <label className="mb-1 block text-xs font-medium text-slate-500">
                    {line.label} ({tab.unit})
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={groupValues[line.key] || ''}
                    onChange={(e) => setGroupValues((prev) => ({ ...prev, [line.key]: e.target.value }))}
                    className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
                    placeholder={line.label}
                    autoFocus={line === tab.lines[0]}
                  />
                  {line.refUpper > 0 && (
                    <p className="mt-0.5 text-xs text-slate-400">参考: {line.refLower}-{line.refUpper}</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <>
              {/* Line selector if multiple (non-group) */}
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
            </>
          )}
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
              disabled={isLoading || (isGroup ? !Object.values(groupValues).some(v => v) : !value)}
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

// ---- Edit Modal ----
interface EditModalProps {
  tab: MetricTab
  editData: { groupTs?: string; lineKey?: string; record?: MetricRecord }
  allRecords: Record<string, MetricRecord[]>
  onClose: () => void
  onSubmit: (data: { id: number; value: number; measured_at: string; context?: string }[]) => void
  isLoading: boolean
}

function EditModal({ tab, editData, allRecords, onClose, onSubmit, isLoading }: EditModalProps) {
  const isGroup = !!editData.groupTs
  const ts = editData.groupTs

  // For group edit: collect all line records at this timestamp
  const groupRecords = isGroup
    ? tab.lines.map((line) => ({
        line,
        record: (allRecords[line.key] || []).find((r) => r.measured_at === ts),
      })).filter((p) => p.record)
    : [{ line: tab.lines.find((l) => l.key === editData.lineKey)!, record: editData.record! }]

  // Initialize state from existing records
  const [groupValues, setGroupValues] = useState<Record<string, string>>(() => {
    const vals: Record<string, string> = {}
    groupRecords.forEach(({ line, record }) => {
      if (record) vals[line.key] = record.value.toString()
    })
    return vals
  })
  const [measuredAt, setMeasuredAt] = useState(() => {
    const r = groupRecords[0]?.record
    return r ? new Date(r.measured_at).toISOString().slice(0, 16) : localDatetimeStr()
  })
  const [context, setContext] = useState(() => {
    const r = groupRecords[0]?.record
    return r?.context || ''
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const isoTime = measuredAt + ':00+08:00'
    const entries = groupRecords
      .map(({ line, record }) => {
        const v = parseFloat(groupValues[line.key] || '')
        if (isNaN(v) || !record) return null
        return { id: record.id, value: v, measured_at: isoTime, context: context || undefined }
      })
      .filter((e): e is NonNullable<typeof e> => e !== null)
    if (entries.length === 0) return
    onSubmit(entries)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-96 rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">编辑{tab.label}数据</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {isGroup ? (
            <div className="grid grid-cols-2 gap-3">
              {groupRecords.map(({ line }) => (
                <div key={line.key}>
                  <label className="mb-1 block text-xs font-medium text-slate-500">
                    {line.label} ({tab.unit})
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={groupValues[line.key] || ''}
                    onChange={(e) => setGroupValues((prev) => ({ ...prev, [line.key]: e.target.value }))}
                    className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
                    placeholder={line.label}
                  />
                  {line.refUpper > 0 && (
                    <p className="mt-0.5 text-xs text-slate-400">参考: {line.refLower}-{line.refUpper}</p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {groupRecords[0].line.label} ({tab.unit})
              </label>
              <input
                type="number"
                step="0.1"
                value={groupValues[groupRecords[0].line.key] || ''}
                onChange={(e) => setGroupValues((prev) => ({ ...prev, [groupRecords[0].line.key]: e.target.value }))}
                required
                autoFocus
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              />
              {groupRecords[0].line.refUpper > 0 && (
                <p className="mt-0.5 text-xs text-slate-400">参考: {groupRecords[0].line.refLower}-{groupRecords[0].line.refUpper}</p>
              )}
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
          {groupRecords[0]?.line.contextOptions ? (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">
                {groupRecords[0].line.contextLabel || '备注'} (可选)
              </label>
              <select
                value={context}
                onChange={(e) => setContext(e.target.value)}
                className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              >
                <option value="">请选择</option>
                {groupRecords[0].line.contextOptions.map((opt) => (
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
              />
            </div>
          )}
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
              disabled={isLoading}
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

// ---- Exam Timeline (for exam:* tabs) ----
