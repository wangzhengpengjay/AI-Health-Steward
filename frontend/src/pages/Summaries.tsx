import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { summariesApi, type HealthSummary } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import MemberSwitcher from '@/components/MemberSwitcher'

const PERIODS: { key: string; label: string }[] = [
  { key: 'weekly', label: '周报' },
  { key: 'monthly', label: '月报' },
  { key: 'annual', label: '年报' },
]

function parseStats(s?: string | null): { trends: any[] } | null {
  if (!s) return null
  try {
    return JSON.parse(s)
  } catch {
    return null
  }
}

function Overview({ s }: { s: HealthSummary }) {
  const stats = parseStats(s.stats_json)
  const trends = stats?.trends ?? []
  return (
    <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
      <div className="rounded-field bg-slate-50 p-3">
        <div className="text-xs text-slate-500">周期范围</div>
        <div className="mt-1 text-sm font-medium text-slate-700">
          {s.period_start} ~ {s.period_end}
        </div>
      </div>
      <div className="rounded-field bg-slate-50 p-3">
        <div className="text-xs text-slate-500">跟踪指标</div>
        <div className="mt-1 text-sm font-medium text-slate-700">{trends.length} 项</div>
      </div>
      <div className="rounded-field bg-slate-50 p-3">
        <div className="text-xs text-slate-500">生成时间</div>
        <div className="mt-1 text-sm font-medium text-slate-700">
          {new Date(s.created_at).toLocaleDateString()}
        </div>
      </div>
    </div>
  )
}

function TrendTable({ s }: { s: HealthSummary }) {
  const stats = parseStats(s.stats_json)
  const trends = stats?.trends ?? []
  if (trends.length === 0) return null
  return (
    <div className="mb-4 overflow-hidden rounded-field border border-slate-200">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs text-slate-500">
          <tr>
            <th className="px-3 py-2">指标</th>
            <th className="px-3 py-2">期初 → 期末</th>
            <th className="px-3 py-2">变化</th>
            <th className="px-3 py-2">均值</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {trends.map((t) => (
            <tr key={t.metric}>
              <td className="px-3 py-2 font-medium text-slate-700">{t.label}</td>
              <td className="px-3 py-2 text-slate-600">
                {t.first} → {t.last} {t.unit}
              </td>
              <td className="px-3 py-2">
                {t.direction === 'up' ? (
                  <span className="text-red-600">↑ {Math.abs(t.delta ?? 0)}</span>
                ) : t.direction === 'down' ? (
                  <span className="text-emerald-600">↓ {Math.abs(t.delta ?? 0)}</span>
                ) : (
                  <span className="text-slate-400">→ 平稳</span>
                )}
                {t.abnormal_last && <span className="ml-1 text-xs text-amber-600">⚠</span>}
              </td>
              <td className="px-3 py-2 text-slate-500">{t.avg} {t.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Summaries() {
  const { currentMemberId, members } = useMemberStore()
  const queryClient = useQueryClient()
  const [period, setPeriod] = useState('monthly')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const member = members.find((m) => m.id === currentMemberId)

  const { data: summaries = [] } = useQuery({
    queryKey: ['summaries', currentMemberId, period],
    queryFn: () => summariesApi.list(Number(currentMemberId), period),
    enabled: !!currentMemberId,
  })

  const generateMutation = useMutation({
    mutationFn: () => summariesApi.generate(Number(currentMemberId), period),
    onSuccess: (s) => {
      queryClient.invalidateQueries({ queryKey: ['summaries', currentMemberId] })
      setSelectedId(s.id)
    },
  })

  const selected = summaries.find((s) => s.id === selectedId) ?? summaries[0]

  if (!currentMemberId || !member) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-slate-500">请先选择家庭成员</p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-bg-secondary">
      <div className="border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-primary">summarize</span>
          <h1 className="text-lg font-medium text-slate-800">健康小结</h1>
          <span className="ml-2 rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary">
            {member.name}
          </span>
        </div>
      </div>

      <div className="space-y-4 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="w-48">
            <MemberSwitcher />
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-field border border-slate-200 bg-white p-1">
              {PERIODS.map((p) => (
                <button
                  key={p.key}
                  onClick={() => setPeriod(p.key)}
                  className={`rounded-field px-3 py-1.5 text-sm transition-colors ${
                    period === p.key ? 'bg-primary text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="rounded-field bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-50"
            >
              {generateMutation.isPending ? '生成中…' : '生成本期小结'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* 历史列表 */}
          <div className="rounded-card border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-700">历史小结</h2>
            {summaries.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-400">暂无小结，点击"生成本期小结"</p>
            ) : (
              <div className="space-y-2">
                {summaries.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedId(s.id)}
                    className={`w-full rounded-field border px-3 py-2 text-left transition-colors ${
                      selected?.id === s.id
                        ? 'border-primary bg-primary-light/30'
                        : 'border-slate-100 hover:bg-slate-50'
                    }`}
                  >
                    <div className="text-sm font-medium text-slate-700">
                      {PERIODS.find((p) => p.key === s.period)?.label ?? s.period}
                    </div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {s.period_start} ~ {s.period_end}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 内容详情 */}
          <div className="rounded-card border border-slate-200 bg-white p-6 lg:col-span-2">
            {selected ? (
              <>
                <Overview s={selected} />
                <TrendTable s={selected} />
                <article className="prose prose-sm max-w-none text-slate-700">
                  <ReactMarkdown>{selected.content}</ReactMarkdown>
                </article>
              </>
            ) : (
              <div className="py-16 text-center text-slate-400">
                选择或生成一份小结以查看内容
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
