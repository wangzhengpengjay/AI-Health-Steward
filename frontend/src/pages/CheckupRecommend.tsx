import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { checkupApi } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import { useCheckupStore } from '@/stores/checkupStore'
import CheckupSupplementModal from '@/components/CheckupSupplementModal'

const PROGRESS_STEPS = [
  { time: 0, text: '正在聚合健康画像数据...' },
  { time: 3, text: '正在构建 1+X+Y 推荐指令...' },
  { time: 6, text: '正在调用 AI 模型生成方案...' },
  { time: 15, text: '模型生成中，方案较复杂请耐心等待...' },
  { time: 25, text: '即将完成...' },
]

export default function CheckupRecommend() {
  const { currentMemberId, members } = useMemberStore()
  const member = members.find((m) => m.id === currentMemberId)
  const ck = useCheckupStore()

  const [showModal, setShowModal] = useState(false)
  const [progressText, setProgressText] = useState(PROGRESS_STEPS[0].text)

  const memberKey = currentMemberId ? String(currentMemberId) : null

  // Reset store when switching member
  useEffect(() => {
    if (memberKey && ck.memberKey && ck.memberKey !== memberKey) {
      ck.reset(memberKey)
    }
  }, [memberKey])

  // Progress text timer during loading
  useEffect(() => {
    if (!ck.loading) {
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
  }, [ck.loading])

  // Fetch completeness on mount / member switch
  useQuery({
    queryKey: ['checkup-completeness', currentMemberId],
    queryFn: async () => {
      const res = await checkupApi.profileCheck(Number(currentMemberId))
      if (!ck.loading && !ck.content) {
        ck.setLoading(false)
      }
      return res
    },
    enabled: !!currentMemberId,
  })

  const handleGenerate = async (budgetTier: string) => {
    if (!currentMemberId) return
    setShowModal(false)
    ck.setLoading(true)
    ck.setError('', String(currentMemberId))  // clear error, keep memberKey
    ck.setLoading(true)
    try {
      const res = await checkupApi.recommend(Number(currentMemberId), budgetTier)
      ck.setContent(res.content, res.completeness, String(currentMemberId))
    } catch (err) {
      ck.setError(
        err instanceof Error ? err.message : '生成失败，请检查模型配置后重试',
        String(currentMemberId)
      )
    }
  }

  if (!currentMemberId || !member) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-rounded text-5xl text-slate-300">person_add</span>
          <p className="mt-3 text-slate-500">请先选择家庭成员</p>
        </div>
      </div>
    )
  }

  // Empty state — no content yet and not loading
  if (!ck.content && !ck.loading && !ck.error) {
    return (
      <>
        <div className="flex h-full items-center justify-center">
          <div className="max-w-md text-center">
            <span className="material-symbols-rounded text-6xl text-slate-200">monitor_heart</span>
            <h2 className="mt-4 text-xl font-semibold text-slate-700">个性化体检项目推荐</h2>
            <p className="mt-2 text-sm text-slate-500">
              基于健康画像数据，按照 1+X+Y 三层逻辑生成定制化体检方案
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="mt-6 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
            >
              生成体检推荐方案
            </button>
          </div>
        </div>
        {showModal && (
          <CheckupSupplementModal
            onSubmit={handleGenerate}
            onClose={() => setShowModal(false)}
          />
        )}
      </>
    )
  }

  // Loading state — persists across page switches via Zustand
  if (ck.loading) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-slate-800">体检推荐</h1>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {member.name}
            </span>
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <p className="mt-4 text-sm text-slate-600">{progressText}</p>
            <p className="mt-1 text-xs text-slate-400">生成过程中可切换其他页面，回来后继续查看</p>
          </div>
        </div>
      </div>
    )
  }

  // Error state
  if (ck.error && !ck.content) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="max-w-md text-center">
          <span className="material-symbols-rounded text-5xl text-red-300">error</span>
          <p className="mt-3 text-sm text-slate-600">{ck.error}</p>
          <button
            onClick={() => setShowModal(true)}
            className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-hover"
          >
            重试
          </button>
        </div>
      </div>
    )
  }

  // Result state
  return (
    <>
      <div className="flex h-full flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-slate-800">体检推荐</h1>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {member.name}
            </span>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50"
          >
            <span className="material-symbols-rounded text-base">refresh</span>
            重新生成
          </button>
        </div>

        {/* Completeness bar */}
        {ck.completeness && (
          <div className="border-b border-slate-100 bg-slate-50 px-6 py-2.5">
            <span className="text-sm text-slate-600">
              {ck.completeness.level} 画像完整度 {ck.completeness.score}%
            </span>
            {ck.completeness.missing_fields.length > 0 && (
              <span className="ml-2 text-xs text-slate-400">
                · 缺失：{ck.completeness.missing_fields.join('、')}
              </span>
            )}
          </div>
        )}

        {/* Markdown content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="prose prose-sm max-w-none prose-headings:my-2 prose-p:my-1.5 prose-li:my-0.5 prose-table:text-xs prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-th:bg-slate-50">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {ck.content || ''}
            </ReactMarkdown>
          </div>

          {/* Disclaimer */}
          <div className="mt-6 border-t border-slate-100 pt-3 text-xs text-slate-400">
            本方案由 AI 基于健康画像生成，仅供参考，不替代医生建议
          </div>
        </div>
      </div>

      {showModal && (
        <CheckupSupplementModal
          onSubmit={handleGenerate}
          onClose={() => setShowModal(false)}
        />
      )}
    </>
  )
}
