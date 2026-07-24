import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { checkupApi } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import { useCheckupStore } from '@/stores/checkupStore'
import CheckupSupplementModal from '@/components/CheckupSupplementModal'

const PROGRESS_STEPS = [
  { time: 0, text: '\u6b63\u5728\u805a\u5408\u5065\u5eb7\u753b\u50cf\u6570\u636e...' },
  { time: 3, text: '\u6b63\u5728\u6784\u5efa 1+X+Y \u63a8\u8350\u6307\u4ee4...' },
  { time: 6, text: '\u6b63\u5728\u8c03\u7528 AI \u6a21\u578b\u751f\u6210\u65b9\u6848...' },
  { time: 15, text: '\u6a21\u578b\u751f\u6210\u4e2d\uff0c\u65b9\u6848\u8f83\u590d\u6742\u8bf7\u8010\u5fc3\u7b49\u5f85...' },
  { time: 25, text: '\u5373\u5c06\u5b8c\u6210...' },
]

function stripCodeFence(text: string): string {
  const trimmed = text.trim()
  if (trimmed.startsWith('```') && trimmed.endsWith('```')) {
    const lines = trimmed.split('\n')
    return lines.slice(1, -1).join('\n')
  }
  return text
}

export default function CheckupRecommend() {
  const { currentMemberId, members } = useMemberStore()
  const member = members.find((m) => m.id === currentMemberId)
  const ck = useCheckupStore()

  const [showModal, setShowModal] = useState(false)
  const [progressText, setProgressText] = useState(PROGRESS_STEPS[0].text)

  const memberId = currentMemberId ?? 0
  const result = ck.getResult(memberId)

  useEffect(() => {
    if (!result.loading) {
      setProgressText(PROGRESS_STEPS[0].text)
      return
    }
    let elapsed = 0
    const timer = setInterval(() => {
      elapsed += 1
      const step = [...PROGRESS_STEPS].reverse().find((s) => elapsed >= s.time)
      if (step) setProgressText(step.text)
    }, 1000)
    return () => clearInterval(timer)
  }, [result.loading])

  useQuery({
    queryKey: ['checkup-completeness', currentMemberId],
    queryFn: async () => {
      const res = await checkupApi.profileCheck(Number(currentMemberId))
      return res
    },
    enabled: !!currentMemberId,
  })

  const handleGenerate = async (budgetTier: string) => {
    if (!currentMemberId) return
    setShowModal(false)
    ck.setLoading(currentMemberId, true)
    ck.setError(currentMemberId, '')
    ck.setLoading(currentMemberId, true)
    try {
      const res = await checkupApi.recommend(Number(currentMemberId), budgetTier)
      ck.setContent(currentMemberId, res.content, res.completeness)
    } catch (err) {
      ck.setError(currentMemberId, err instanceof Error ? err.message : '\u751f\u6210\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6a21\u578b\u914d\u7f6e\u540e\u91cd\u8bd5')
    }
  }

  if (!currentMemberId || !member) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-rounded text-5xl text-slate-300">person_add</span>
          <p className="mt-3 text-slate-500">{'\u8bf7\u5148\u9009\u62e9\u5bb6\u5ead\u6210\u5458'}</p>
        </div>
      </div>
    )
  }

  if (!result.content && !result.loading && !result.error) {
    return (
      <>
        <div className="flex h-full items-center justify-center">
          <div className="max-w-md text-center">
            <span className="material-symbols-rounded text-6xl text-slate-200">monitor_heart</span>
            <h2 className="mt-4 text-xl font-semibold text-slate-700">{'\u4e2a\u6027\u5316\u4f53\u68c0\u9879\u76ee\u63a8\u8350'}</h2>
            <p className="mt-2 text-sm text-slate-500">{'\u57fa\u4e8e\u5065\u5eb7\u753b\u50cf\u6570\u636e\uff0c\u6309\u7167 1+X+Y \u4e09\u5c42\u903b\u8f91\u751f\u6210\u5b9a\u5236\u5316\u4f53\u68c0\u65b9\u6848'}</p>
            <button onClick={() => setShowModal(true)} className="mt-6 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover">{'\u751f\u6210\u4f53\u68c0\u63a8\u8350\u65b9\u6848'}</button>
          </div>
        </div>
        {showModal && <CheckupSupplementModal onSubmit={handleGenerate} onClose={() => setShowModal(false)} />}
      </>
    )
  }

  if (result.loading) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-slate-800">{'\u4f53\u68c0\u63a8\u8350'}</h1>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{member.name}</span>
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <p className="mt-4 text-sm text-slate-600">{progressText}</p>
            <p className="mt-1 text-xs text-slate-400">{'\u751f\u6210\u8fc7\u7a0b\u4e2d\u53ef\u5207\u6362\u5176\u4ed6\u9875\u9762\uff0c\u56de\u6765\u540e\u7ee7\u7eed\u67e5\u770b'}</p>
          </div>
        </div>
      </div>
    )
  }

  if (result.error && !result.content) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="max-w-md text-center">
          <span className="material-symbols-rounded text-5xl text-red-300">error</span>
          <p className="mt-3 text-sm text-slate-600">{result.error}</p>
          <button onClick={() => setShowModal(true)} className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover">{'\u91cd\u8bd5'}</button>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-slate-800">{'\u4f53\u68c0\u63a8\u8350'}</h1>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{member.name}</span>
          </div>
          <button onClick={() => setShowModal(true)} className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50">
            <span className="material-symbols-rounded text-base">refresh</span>
            {'\u91cd\u65b0\u751f\u6210'}
          </button>
        </div>

        {result.completeness && (
          <div className="border-b border-slate-100 bg-slate-50 px-6 py-2.5">
            <span className="text-sm text-slate-600">{result.completeness.level} {'\u753b\u50cf\u5b8c\u6574\u5ea6'} {result.completeness.score}%</span>
            {result.completeness.missing_fields.length > 0 && (
              <span className="ml-2 text-xs text-slate-400">{'\u00b7 \u7f3a\u5931\uff1a'}{result.completeness.missing_fields.join('\u3001')}</span>
            )}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="prose prose-sm max-w-none prose-headings:my-2 prose-p:my-1.5 prose-li:my-0.5 prose-table:text-xs prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-th:bg-slate-50">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{stripCodeFence(result.content || '')}</ReactMarkdown>
          </div>
          <div className="mt-6 border-t border-slate-100 pt-3 text-xs text-slate-400">{'\u672c\u65b9\u6848\u7531 AI \u57fa\u4e8e\u5065\u5eb7\u753b\u50cf\u751f\u6210\uff0c\u4ec5\u4f9b\u53c2\u8003\uff0c\u4e0d\u66ff\u4ee3\u533b\u751f\u5efa\u8bae'}</div>
        </div>
      </div>
      {showModal && <CheckupSupplementModal onSubmit={handleGenerate} onClose={() => setShowModal(false)} />}
    </>
  )
}
