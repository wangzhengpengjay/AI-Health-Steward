import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scalesApi, type ScaleDetail } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import MemberSwitcher from '@/components/MemberSwitcher'

const RISK_STYLE: Record<string, string> = {
  none: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  mild: 'bg-amber-50 text-amber-700 border-amber-200',
  moderate: 'bg-amber-50 text-amber-700 border-amber-200',
  moderately_severe: 'bg-orange-50 text-orange-700 border-orange-200',
  severe: 'bg-red-50 text-red-700 border-red-200',
  high: 'bg-red-50 text-red-700 border-red-200',
}

function ScaleCard({ detail, memberId }: { detail: ScaleDetail; memberId: number }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [open, setOpen] = useState(false)

  const submitMutation = useMutation({
    mutationFn: () => scalesApi.submit(memberId, detail.code, answers),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: ['scales', memberId] })
      queryClient.invalidateQueries({ queryKey: ['scale-results', memberId] })
      // 提交成功后跳转到完整结果页
      navigate(`/assess/result/${r.id}`)
    },
  })

  const answeredCount = Object.keys(answers).length
  const allAnswered = answeredCount >= detail.questions.length

  return (
    <div className="rounded-card border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-base font-medium text-slate-800">{detail.name}</h3>
          <p className="mt-1 text-sm text-slate-500">{detail.description}</p>
        </div>
        {detail.should_push && (
          <span className="rounded-full bg-primary-light px-2 py-0.5 text-xs font-medium text-primary">
            建议测评
          </span>
        )}
      </div>
      {detail.reason && !open && (
        <p className="mt-2 text-xs text-slate-400">{detail.reason}</p>
      )}
      {detail.last_result && !open && (
        <div className="mt-2 flex items-center gap-2 text-xs">
          <span className="text-slate-400">上次结果：</span>
          <span className="font-medium text-slate-600">{detail.last_result.total_score} 分</span>
          <span className={`rounded-full border px-2 py-0.5 ${RISK_STYLE[detail.last_result.risk_level] ?? 'bg-slate-50 text-slate-600'}`}>
            {detail.last_result.risk_label}
          </span>
          {detail.last_result.created_at && (
            <span className="text-slate-400">{new Date(detail.last_result.created_at).toLocaleDateString()}</span>
          )}
        </div>
      )}

      <button
        onClick={() => setOpen(!open)}
        className="mt-3 rounded-field border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
      >
        {open ? '收起' : '开始测评'}
      </button>

      {open && (
        <div className="mt-4 space-y-3">
          {detail.questions.map((q, qi) => (
            <div key={q.id} className="rounded-field bg-slate-50 p-3">
              <div className="text-sm font-medium text-slate-700">
                {qi + 1}. {q.text}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {q.options.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setAnswers((a) => ({ ...a, [q.id]: opt.value }))}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                      answers[q.id] === opt.value
                        ? 'border-primary bg-primary text-white'
                        : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          ))}

          <button
            onClick={() => submitMutation.mutate()}
            disabled={!allAnswered || submitMutation.isPending}
            className="w-full rounded-field bg-primary py-2.5 text-sm font-medium text-white hover:bg-primary-dark disabled:opacity-40"
          >
            {submitMutation.isPending
              ? '提交中…'
              : allAnswered
                ? '提交测评'
                : `请完成剩余 ${detail.questions.length - answeredCount} 题`}
          </button>

        </div>
      )}
    </div>
  )
}

function ResultHistory({ memberId }: { memberId: number }) {
  const navigate = useNavigate()
  const { data: results = [] } = useQuery({
    queryKey: ['scale-results', memberId],
    queryFn: () => scalesApi.results(memberId),
    enabled: !!memberId,
  })
  if (results.length === 0) return null
  return (
    <div className="rounded-card border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">测评历史</h3>
        <span className="text-xs text-slate-400">点击查看完整结果</span>
      </div>
      <div className="space-y-2">
        {results.map((r) => (
          <button
            key={r.id}
            onClick={() => navigate(`/assess/result/${r.id}`)}
            className="flex w-full items-center justify-between rounded-field bg-slate-50 px-3 py-2 text-sm transition-colors hover:bg-slate-100"
          >
            <div>
              <span className="font-medium text-slate-700">
                {r.scale_name ?? r.scale_code.toUpperCase()}
              </span>
              <span className="ml-2 text-slate-500">{new Date(r.created_at).toLocaleDateString()}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-800">{r.total_score} 分</span>
              <span className={`rounded-full border px-2 py-0.5 text-xs ${RISK_STYLE[r.risk_level] ?? 'bg-slate-50'}`}>
                {r.risk_label}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

export default function Assess() {
  const { currentMemberId, members } = useMemberStore()
  const member = members.find((m) => m.id === currentMemberId)

  const { data: scales = [] } = useQuery({
    queryKey: ['scales', currentMemberId],
    queryFn: () => scalesApi.list(Number(currentMemberId)),
    enabled: !!currentMemberId,
  })

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
          <span className="material-symbols-rounded text-primary">monitor_heart</span>
          <h1 className="text-lg font-medium text-slate-800">风险自测</h1>
          <span className="ml-2 rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary">
            {member.name}
          </span>
        </div>
      </div>

      <div className="space-y-4 p-6">
        <div className="w-48">
          <MemberSwitcher />
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {scales.map((meta) => (
            <ScaleDetailFetcher key={meta.code} code={meta.code} memberId={currentMemberId} />
          ))}
        </div>
        <ResultHistory memberId={currentMemberId} />
      </div>
    </div>
  )
}

function ScaleDetailFetcher({ code, memberId }: { code: string; memberId: number }) {
  const { data: detail } = useQuery({
    queryKey: ['scale-detail', memberId, code],
    queryFn: () => scalesApi.detail(memberId, code),
    enabled: !!memberId,
  })
  if (!detail) return null
  return <ScaleCard detail={detail} memberId={memberId} />
}
