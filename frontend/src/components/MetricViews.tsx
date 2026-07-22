import {
  Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, ComposedChart,
} from 'recharts'
import type { MetricRecord } from '@/types'

export const SOURCE_LABELS: Record<string, string> = {
  manual: '手动录入',
  report: '报告导入',
  chat_extract: '聊天抽取',
}

export function ExamTimeline({ allRecords, tabLabel }: { allRecords: Record<string, MetricRecord[]>; tabLabel: string }) {
  const allItems: { record: MetricRecord; lineKey: string; lineLabel: string }[] = []
  for (const [key, records] of Object.entries(allRecords)) {
    const parts = key.split(':')
    const desc = parts[2] || key
    for (const r of records) {
      allItems.push({ record: r, lineKey: key, lineLabel: desc })
    }
  }
  allItems.sort((a, b) => new Date(b.record.measured_at).getTime() - new Date(a.record.measured_at).getTime())

  if (allItems.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-slate-400">
        <span className="material-symbols-rounded text-4xl">timeline</span>
        <p className="mt-2 text-sm">暂无{tabLabel}检查记录</p>
      </div>
    )
  }

  return (
    <div>
      <h3 className="mb-4 text-sm font-medium text-slate-700">{tabLabel}检查时间线</h3>
      <div className="relative">
        <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-slate-200" />
        <div className="space-y-4">
          {allItems.map((item, idx) => {
            const r = item.record
            const date = new Date(r.measured_at).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
            const hasValue = r.value > 0 && !!r.unit
            return (
              <div key={idx} className="relative flex gap-4 pl-0">
                <div className="relative z-10 mt-1 h-6 w-6 flex-shrink-0 rounded-full bg-amber-100 flex items-center justify-center">
                  <span className="material-symbols-rounded text-amber-500 text-sm">circle</span>
                </div>
                <div className="flex-1 rounded-field border border-slate-100 bg-slate-50 p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">{date}</span>
                      <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">{SOURCE_LABELS[r.source_type] || r.source_type}</span>
                    </div>
                    {hasValue && <span className="text-sm font-semibold text-slate-700">{r.value} {r.unit}</span>}
                  </div>
                  <p className="mt-1 text-sm font-medium text-slate-800">{item.lineLabel}</p>
                  {r.context && <p className="mt-1 text-xs text-slate-500">{r.context}</p>}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export function LabTabContent({ allRecords, tabLabel }: { allRecords: Record<string, MetricRecord[]>; tabLabel: string }) {
  const tests = Object.entries(allRecords).filter(([, records]) => records.length > 0)

  if (tests.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center text-slate-400">
        <span className="material-symbols-rounded text-4xl">science</span>
        <p className="mt-2 text-sm">暂无{tabLabel}检验数据</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {tests.map(([key, records]) => {
        const testName = key.split(':')[2] || key
        const sorted = [...records].sort((a, b) => new Date(a.measured_at).getTime() - new Date(b.measured_at).getTime())
        const latest = sorted[sorted.length - 1]
        const hasRef = latest.reference_lower != null && latest.reference_upper != null

        return (
          <div key={key} className="rounded-card border border-slate-200 bg-white p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-600" />
                <h3 className="text-sm font-medium text-slate-700">{testName}</h3>
                {hasRef && <span className="text-xs text-slate-400">参考: {latest.reference_lower}-{latest.reference_upper} {latest.unit}</span>}
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-lg font-semibold ${latest.is_abnormal ? 'text-amber-600' : 'text-slate-800'}`}>
                  {latest.value}<span className="ml-1 text-xs text-slate-400">{latest.unit}</span>
                </span>
                {latest.is_abnormal && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-600">异常</span>}
              </div>
            </div>
            {sorted.length > 1 ? (
              <ResponsiveContainer width="100%" height={200}>
                <ComposedChart data={sorted.map(r => ({
                  time: new Date(r.measured_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }),
                  value: r.value,
                  abnormal: r.is_abnormal,
                }))} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F0F2F5" />
                  <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#94A3B8' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#94A3B8' }} />
                  <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #E2E8F0', fontSize: 12 }} />
                  {hasRef && latest.reference_upper && latest.reference_upper > 0 && (
                    <ReferenceLine y={latest.reference_upper} stroke="#059669" strokeDasharray="3 3" strokeOpacity={0.4} />
                  )}
                  {hasRef && latest.reference_lower && latest.reference_lower > 0 && (
                    <ReferenceLine y={latest.reference_lower} stroke="#059669" strokeDasharray="3 3" strokeOpacity={0.3} />
                  )}
                  <Line type="monotone" dataKey="value" name={testName} stroke="#059669" strokeWidth={2} connectNulls
                    dot={(props: { cx?: number; cy?: number; payload?: Record<string, unknown> }) => {
                      const { cx, cy, payload } = props
                      if (cx === undefined || cy === undefined) return <g />
                      return <circle cx={cx} cy={cy} r={4} fill={payload?.abnormal ? '#F56C6C' : '#059669'} stroke="#fff" strokeWidth={1.5} />
                    }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-6 text-center text-xs text-slate-400">仅1条记录，暂无趋势</p>
            )}
          </div>
        )
      })}
    </div>
  )
}
