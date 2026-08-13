import { useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { scalesApi, type ScaleResult } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'

const RISK_STYLE: Record<string, string> = {
  none: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  mild: 'bg-amber-50 text-amber-700 border-amber-200',
  moderate: 'bg-amber-50 text-amber-700 border-amber-200',
  moderately_severe: 'bg-orange-50 text-orange-700 border-orange-200',
  severe: 'bg-red-50 text-red-700 border-red-200',
  high: 'bg-red-50 text-red-700 border-red-200',
}
const RISK_BAR: Record<string, string> = {
  none: 'bg-emerald-500',
  low: 'bg-emerald-500',
  mild: 'bg-amber-400',
  moderate: 'bg-amber-500',
  moderately_severe: 'bg-orange-500',
  severe: 'bg-red-600',
  high: 'bg-red-600',
}

function parseAnswers(raw?: string | null): Record<string, number> {
  if (!raw) return {}
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

// 风险分级条：将总分映射到 0..100 区间并标出所在阈值段
function RiskBar({
  score,
  thresholds,
  level,
}: {
  score: number
  thresholds?: { min: number; max: number; level: string; label: string }[]
  level: string
}) {
  if (!thresholds || thresholds.length === 0) return null
  const maxScore = Math.max(...thresholds.map((t) => t.max))
  const minScore = Math.min(...thresholds.map((t) => t.min))
  const range = Math.max(1, maxScore - minScore)
  const pct = Math.max(2, Math.min(98, ((score - minScore) / range) * 100))

  return (
    <div className="mt-4">
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        {/* 分段色块 */}
        {thresholds.map((t) => {
          const left = ((t.min - minScore) / range) * 100
          const width = Math.max(0, ((t.max - t.min) / range) * 100)
          return (
            <div
              key={t.level}
              className={`absolute inset-y-0 ${RISK_BAR[t.level] ?? 'bg-slate-300'} opacity-70`}
              style={{ left: `${left}%`, width: `${width}%` }}
            />
          )
        })}
        {/* 得分指针 */}
        <div
          className="absolute top-1/2 h-4 w-1 -translate-y-1/2 rounded bg-slate-900 shadow"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-slate-400">
        <span>{minScore} 分</span>
        <span className="font-medium text-slate-600">{level}</span>
        <span>{maxScore} 分</span>
      </div>
    </div>
  )
}

function QuestionReview({
  answers,
  detail,
  name,
}: {
  answers: Record<string, number>
  detail: { questions: { id: string; text: string; options: { value: number; label: string }[] }[] }
  name: string
}) {
  const rows = detail.questions.map((q, i) => {
    const val = answers[q.id]
    const opt = q.options.find((o) => o.value === val)
    return { idx: i + 1, text: q.text, val: val ?? 0, label: opt?.label ?? '未作答' }
  })
  // 主要关注点：得分最高的题项（不含未作答）
  const maxVal = Math.max(0, ...rows.filter((r) => r.label !== '未作答').map((r) => r.val))
  const focus = rows.filter((r) => r.val === maxVal && r.val > 0)

  return (
    <div className="rounded-card border border-slate-200 bg-white p-5">
      <h3 className="mb-1 text-sm font-medium text-slate-700">逐题回顾</h3>
      <p className="mb-3 text-xs text-slate-400">以下为 {name} 的作答明细</p>
      {focus.length > 0 && (
        <div className="mb-3 rounded-field bg-orange-50 px-3 py-2 text-sm text-orange-700">
          <span className="font-medium">主要关注点：</span>
          第 {focus.map((f) => f.idx).join('、')} 题得分较高，建议重点留意。
        </div>
      )}
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.idx} className="flex items-start justify-between rounded-field bg-slate-50 px-3 py-2">
            <div className="pr-3 text-sm text-slate-700">
              <span className="font-medium text-slate-500">{r.idx}.</span> {r.text}
            </div>
            <div className="shrink-0 text-right">
              <div className={`text-sm font-medium ${r.val > 0 ? 'text-slate-800' : 'text-slate-300'}`}>
                {r.label}
              </div>
              <div className={`text-xs ${r.val > 0 ? 'text-primary' : 'text-slate-300'}`}>{r.val} 分</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function HistoryTrend({ memberId, code, currentId }: { memberId: number; code: string; currentId: number }) {
  const { data: results = [] } = useQuery({
    queryKey: ['scale-results', memberId],
    queryFn: () => scalesApi.results(memberId),
    enabled: !!memberId,
  })
  const history = results.filter((r) => r.scale_code === code)
  if (history.length <= 1) return null
  const items = [...history].reverse() // 旧→新
  return (
    <div className="rounded-card border border-slate-200 bg-white p-5">
      <h3 className="mb-3 text-sm font-medium text-slate-700">历史得分变化</h3>
      <div className="space-y-2">
        {items.map((r) => (
          <div
            key={r.id}
            className={`flex items-center justify-between rounded-field px-3 py-2 text-sm ${
              r.id === currentId ? 'border border-primary bg-primary-light/20' : 'bg-slate-50'
            }`}
          >
            <span className="text-slate-500">{new Date(r.created_at).toLocaleDateString()}</span>
            <span className="flex items-center gap-2">
              <span className="font-semibold text-slate-800">{r.total_score} 分</span>
              <span className={`rounded-full border px-2 py-0.5 text-xs ${RISK_STYLE[r.risk_level] ?? 'bg-slate-50'}`}>
                {r.risk_label}
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function AssessResult() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { currentMemberId } = useMemberStore()

  const { data: results = [] } = useQuery({
    queryKey: ['scale-results', currentMemberId],
    queryFn: () => scalesApi.results(Number(currentMemberId)),
    enabled: !!currentMemberId,
  })

  const result: ScaleResult | undefined = results.find((r) => String(r.id) === String(id))

  const { data: detail } = useQuery({
    queryKey: ['scale-detail', currentMemberId, result?.scale_code],
    queryFn: () => scalesApi.detail(Number(currentMemberId), result!.scale_code),
    enabled: !!currentMemberId && !!result?.scale_code,
  })

  const answers = useMemo(() => parseAnswers(result?.answers), [result?.answers])

  if (!currentMemberId) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-slate-500">请先选择家庭成员</p>
      </div>
    )
  }
  if (!result) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-slate-500">未找到该测评结果</p>
          <button
            onClick={() => navigate('/assess')}
            className="mt-3 rounded-field bg-primary px-4 py-2 text-sm text-white hover:bg-primary-dark"
          >
            返回自测
          </button>
        </div>
      </div>
    )
  }

  const isHigh = ['high', 'severe', 'moderately_severe'].includes(result.risk_level)
  const levelLabel = detail?.thresholds?.find((t) => t.level === result.risk_level)?.label ?? result.risk_label

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-bg-secondary">
      <div className="border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate('/assess')} className="text-slate-400 hover:text-slate-600">
            <span className="material-symbols-rounded">arrow_back</span>
          </button>
          <span className="material-symbols-rounded text-primary">fact_check</span>
          <h1 className="text-lg font-medium text-slate-800">测评结果</h1>
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl space-y-4 p-6">
        {/* 得分总览 */}
        <div className={`rounded-card border p-6 ${RISK_STYLE[result.risk_level] ?? 'bg-slate-50'}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs text-slate-500">{result.scale_name ?? result.scale_code.toUpperCase()}</div>
              <div className="text-sm text-slate-400">{new Date(result.created_at).toLocaleDateString()}</div>
            </div>
            <div className="flex items-center gap-3">
              <div>
                <div className="text-3xl font-semibold text-slate-800">{result.total_score}</div>
                <div className="text-xs text-slate-500">总分</div>
              </div>
              <span className="rounded-full border bg-white/60 px-3 py-1 text-sm font-medium">
                {result.risk_label}
              </span>
            </div>
          </div>
          <RiskBar score={result.total_score} thresholds={detail?.thresholds} level={levelLabel ?? ''} />
          {result.advice && (
            <p className="mt-4 rounded-field bg-white/60 px-3 py-2 text-sm text-slate-700">{result.advice}</p>
          )}
          {isHigh && (
            <div className="mt-3 rounded-field bg-red-50 px-3 py-2 text-sm text-red-700">
              该结果为较高风险，建议尽快咨询医生做进一步评估。
            </div>
          )}
        </div>

        {/* 逐题回顾 */}
        {detail && <QuestionReview answers={answers} detail={detail} name={result.scale_name ?? ''} />}

        {/* 免责声明 */}
        {detail?.caveat && (
          <p className="rounded-card border border-slate-200 bg-white px-4 py-3 text-xs text-slate-400">
            {detail.caveat}
          </p>
        )}

        {/* 历史趋势 */}
        <HistoryTrend memberId={currentMemberId} code={result.scale_code} currentId={result.id} />

        {/* CTA */}
        <div className="flex gap-3 pt-1">
          <button
            onClick={() => navigate('/assess')}
            className="flex-1 rounded-field bg-primary py-2.5 text-sm font-medium text-white hover:bg-primary-dark"
          >
            返回自测
          </button>
          <button
            onClick={() => {
              const scaleName = result.scale_name ?? result.scale_code.toUpperCase()
              const prefilled = `我刚完成了「${scaleName}」测评，总分 ${result.total_score} 分，结果为「${result.risk_label}」。${result.advice ? '建议：' + result.advice : ''}请帮我进一步解读和建议。`
              navigate('/chat', { state: { initialInput: prefilled } })
            }}
            className="flex-1 rounded-field border border-slate-300 bg-white py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            咨询 AI 健康管家
          </button>
        </div>
      </div>
    </div>
  )
}
