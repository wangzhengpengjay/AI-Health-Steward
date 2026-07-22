import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart,
} from 'recharts'
import { metricsApi, chatApi, ApiError } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import type { MetricRecord, SourceType } from '@/types'

// ---- Metric tab config ----
interface MetricTab {
  key: string
  label: string
  unit: string
  refLower?: number
  refUpper?: number
  color: string
}

const METRIC_TABS: MetricTab[] = [
  { key: 'systolic_blood_pressure', label: '血压', unit: 'mmHg', refLower: 90, refUpper: 120, color: '#3363FF' },
  { key: 'fasting_glucose', label: '血糖', unit: 'mmol/L', refLower: 3.9, refUpper: 6.1, color: '#0891B2' },
  { key: 'total_cholesterol', label: '血脂', unit: 'mmol/L', refLower: 3.1, refUpper: 5.2, color: '#059669' },
  { key: 'heart_rate', label: '心率', unit: 'bpm', refLower: 60, refUpper: 100, color: '#E6A23C' },
  { key: 'weight', label: '体重', unit: 'kg', refLower: 0, refUpper: 0, color: '#F56C6C' },
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
  const queryClient = useQueryClient()

  const currentMember = members.find((m) => m.id === currentMemberId)
  const metric = METRIC_TABS[activeTab]

  const { data: records = [], isLoading } = useQuery<MetricRecord[]>({
    queryKey: ['metrics', currentMemberId, metric.key],
    queryFn: () => metricsApi.getByName(String(currentMemberId), metric.key),
    enabled: !!currentMemberId,
  })

  const addMutation = useMutation({
    mutationFn: (data: { metric_name: string; value: number; unit: string; measured_at: string; reference_lower?: number; reference_upper?: number; context?: string }) =>
      metricsApi.create(String(currentMemberId), { ...data, source_type: 'manual' as SourceType }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['metrics', currentMemberId, metric.key] })
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

  // Prepare chart data
  const chartData = [...records]
    .sort((a, b) => new Date(a.measured_at).getTime() - new Date(b.measured_at).getTime())
    .map((r) => ({
      time: new Date(r.measured_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }),
      value: r.value,
      isAbnormal: r.is_abnormal,
      source: r.source_type,
    }))

  const abnormalCount = records.filter((r) => r.is_abnormal).length

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
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 rounded-field bg-primary px-3 py-2 text-sm text-white transition hover:bg-primary-hover"
          >
            <span className="material-symbols-rounded text-lg">add</span>
            新增数据
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200 bg-white px-6">
        {METRIC_TABS.map((tab, i) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(i)}
            className={`relative px-4 py-2.5 text-sm font-medium transition ${
              activeTab === i
                ? 'text-primary'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.label}
            {activeTab === i && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-full bg-primary" />
            )}
          </button>
        ))}
      </div>

      {/* Chart area */}
      <div className="flex-1 overflow-y-auto bg-bg-secondary p-6">
        {/* Summary cards */}
        <div className="mb-4 flex gap-4">
          <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">最新值</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">
              {records.length > 0 ? records[0].value : '--'}
              <span className="ml-1 text-sm text-slate-400">{metric.unit}</span>
            </p>
          </div>
          <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">参考范围</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">
              {metric.refLower && metric.refUpper
                ? `${metric.refLower}-${metric.refUpper}`
                : '--'}
              <span className="ml-1 text-sm text-slate-400">{metric.unit}</span>
            </p>
          </div>
          <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">异常次数</p>
            <p className={`mt-1 text-2xl font-semibold ${abnormalCount > 0 ? 'text-amber-600' : 'text-green-600'}`}>
              {abnormalCount}
              <span className="ml-1 text-sm text-slate-400">/ {records.length}</span>
            </p>
          </div>
          <div className="flex-1 rounded-card border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">记录数</p>
            <p className="mt-1 text-2xl font-semibold text-slate-800">{records.length}</p>
          </div>
        </div>

        {/* Trend chart */}
        <div className="rounded-card border border-slate-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-medium text-slate-700">{metric.label}趋势图</h3>
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
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
                <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#94A3B8' }} />
                <YAxis tick={{ fontSize: 12, fill: '#94A3B8' }} />
                <Tooltip
                  contentStyle={{ borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12 }}
                  formatter={(v) => [`${v} ${metric.unit}`, metric.label]}
                  labelFormatter={(l) => `日期: ${l}`}
                />
                {metric.refLower !== undefined && metric.refUpper !== undefined && metric.refUpper > 0 && (
                  <>
                    <ReferenceLine y={metric.refUpper} stroke="#E6A23C" strokeDasharray="5 5" label={{ value: '上限', fontSize: 10, fill: '#E6A23C' }} />
                    <ReferenceLine y={metric.refLower} stroke="#67C23A" strokeDasharray="5 5" label={{ value: '下限', fontSize: 10, fill: '#67C23A' }} />
                  </>
                )}
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={metric.color}
                  strokeWidth={2}
                  dot={(props: { cx?: number; cy?: number; payload?: { isAbnormal?: boolean } }) => {
                    const { cx, cy, payload } = props
                    if (cx === undefined || cy === undefined) return <g key={Math.random()} />
                    return (
                      <circle
                        key={`dot-${cx}-${cy}`}
                        cx={cx}
                        cy={cy}
                        r={4}
                        fill={payload?.isAbnormal ? '#F56C6C' : metric.color}
                        stroke="#fff"
                        strokeWidth={1.5}
                      />
                    )
                  }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Recent records */}
        {records.length > 0 && (
          <div className="mt-4 rounded-card border border-slate-200 bg-white p-4">
            <h3 className="mb-3 text-sm font-medium text-slate-700">最近记录</h3>
            <div className="space-y-2">
              {records.slice(0, 10).map((r) => (
                <div key={r.id} className="flex items-center justify-between rounded-field bg-slate-50 px-3 py-2">
                  <div className="flex items-center gap-3">
                    <span className={`inline-block h-2 w-2 rounded-full ${r.is_abnormal ? 'bg-amber-500' : 'bg-green-500'}`} />
                    <span className="text-sm font-medium text-slate-700">{r.value} {r.unit}</span>
                    {r.is_abnormal && (
                      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-600">异常</span>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-400">
                    <span>{SOURCE_LABELS[r.source_type] || r.source_type}</span>
                    <span>{new Date(r.measured_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Add data modal */}
      {showAddModal && (
        <AddDataModal
          metric={metric}
          onClose={() => setShowAddModal(false)}
          onSubmit={(data) => addMutation.mutate(data)}
          isLoading={addMutation.isPending}
          error={addMutation.error instanceof ApiError ? addMutation.error.message : null}
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
  metric: MetricTab
  onClose: () => void
  onSubmit: (data: { metric_name: string; value: number; unit: string; measured_at: string; reference_lower?: number; reference_upper?: number; context?: string }) => void
  isLoading: boolean
  error: string | null
}

function AddDataModal({ metric, onClose, onSubmit, isLoading, error }: AddDataModalProps) {
  const [value, setValue] = useState('')
  const [measuredAt, setMeasuredAt] = useState(new Date().toISOString().slice(0, 16))
  const [context, setContext] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const numValue = parseFloat(value)
    if (isNaN(numValue)) return
    onSubmit({
      metric_name: metric.key,
      value: numValue,
      unit: metric.unit,
      measured_at: new Date(measuredAt).toISOString(),
      reference_lower: metric.refLower,
      reference_upper: metric.refUpper,
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-96 rounded-card bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-medium text-slate-800">新增{metric.label}数据</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">数值 ({metric.unit})</label>
            <input
              type="number"
              step="0.1"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              autoFocus
              className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              placeholder={`输入${metric.label}数值`}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">测量时间</label>
            <input
              type="datetime-local"
              value={measuredAt}
              onChange={(e) => setMeasuredAt(e.target.value)}
              className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">备注 (可选)</label>
            <input
              type="text"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              className="w-full rounded-field border border-slate-200 px-3 py-2 text-sm focus:border-primary focus:outline-none"
              placeholder="如：空腹、餐后、静息"
            />
          </div>
          {metric.refLower && metric.refUpper ? (
            <p className="text-xs text-slate-400">参考范围: {metric.refLower}-{metric.refUpper} {metric.unit}</p>
          ) : null}
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
            {/* File select */}
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

            {/* Message */}
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

        {/* Result */}
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
