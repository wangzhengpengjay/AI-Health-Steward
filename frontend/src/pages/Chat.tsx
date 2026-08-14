import { useState, useRef, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useMemberStore } from '@/stores/memberStore'
import { useChatStore } from '@/stores/chatStore'
import { chatApi, type ReportRecord } from '@/lib/api'
import type { ChatMessage } from '@/types'
import ChatBubble from '@/components/ChatBubble'
import ReportConfirmModal from '@/components/ReportConfirmModal'

export default function Chat() {
  const { currentMemberId, members } = useMemberStore()
  const memberId = currentMemberId ? Number(currentMemberId) : null
  const memberChat = useChatStore((s) => (memberId != null ? s.members[memberId] : undefined))
  const {
    setHistory,
    appendMessage,
    setStreaming,
    setStreamingContent,
    setPendingReport,
    setExtractingReport,
    setError,
  } = useChatStore()
  const messages = memberChat?.messages ?? []
  const isStreaming = memberChat?.isStreaming ?? false
  const streamingContent = memberChat?.streamingContent ?? ''
  const error = memberChat?.error ?? null
  const pendingReport = memberChat?.pendingReport ?? null
  const extractingReport = memberChat?.extractingReport ?? false
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const location = useLocation()
  const [input, setInput] = useState('')
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [showReportModal, setShowReportModal] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const currentMember = members.find((m) => m.id === currentMemberId)

  // Load persisted chat history when entering the page or switching members.
  useEffect(() => {
    if (!currentMemberId) return
    const id = Number(currentMemberId)
    if (useChatStore.getState().members[id]?.historyLoaded) return
    let cancelled = false
    setIsLoadingHistory(true)
    chatApi
      .getHistory(id)
      .then(({ messages }) => {
        if (cancelled) return
        const restored: ChatMessage[] = messages.map((h) => ({
          role: h.role as 'user' | 'assistant',
          content: h.content,
          timestamp: h.created_at || new Date().toISOString(),
        }))
        setHistory(id, restored)
      })
      .catch(() => {
        if (!cancelled) setHistory(id, [])
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentMemberId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, streamingContent])

  // Prefill input when navigating from AssessResult with scale context
  useEffect(() => {
    const state = location.state as { initialInput?: string } | null
    if (state?.initialInput) {
      setInput(state.initialInput)
      // Clear the state so it doesn't re-trigger on re-renders
      window.history.replaceState({}, '')
    }
  }, [location.state])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
    if (!validTypes.includes(file.type)) {
      if (memberId != null) setError(memberId, '仅支持 JPG/PNG/WebP/PDF 格式')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      if (memberId != null) setError(memberId, '文件大小不能超过 20MB')
      return
    }
    setAttachedFile(file)
    if (memberId != null) setError(memberId, null)
    if (file.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(file))
    } else {
      setPreviewUrl(null)
    }
  }

  const handleRemoveFile = () => {
    setAttachedFile(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    for (const item of items) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (!file) return
        const validTypes = ['image/jpeg', 'image/png', 'image/webp']
        if (!validTypes.includes(file.type)) {
          if (memberId != null) setError(memberId, '粘贴的图片格式不支持，仅支持 JPG/PNG/WebP')
          return
        }
        if (file.size > 20 * 1024 * 1024) {
          if (memberId != null) setError(memberId, '粘贴的图片超过 20MB 限制')
          return
        }
        setAttachedFile(file)
        if (memberId != null) setError(memberId, null)
        setPreviewUrl(URL.createObjectURL(file))
        break
      }
    }
  }

  const handleSend = async () => {
    if ((!input.trim() && !attachedFile) || isStreaming) return
    if (!currentMemberId) {
      if (memberId != null) setError(memberId, '请先选择家庭成员')
      return
    }
    const id = Number(currentMemberId)

    const userContent = input.trim() || (attachedFile ? '请帮我解读这份报告' : '')
    const userMsg: ChatMessage = {
      role: 'user',
      content: userContent,
      timestamp: new Date().toISOString(),
    }
    if (attachedFile && previewUrl) {
      userMsg.content = `${userContent}\n[图片: ${attachedFile.name}]`
    } else if (attachedFile) {
      userMsg.content = `${userContent}\n[文件: ${attachedFile.name}]`
    }
    appendMessage(id, userMsg)
    const userInput = input.trim()
    const fileToSend = attachedFile
    setInput('')
    handleRemoveFile()
    setError(id, null)
    setStreaming(id, true)
    setStreamingContent(id, '')
    if (fileToSend) setExtractingReport(id, true)

    try {
      let fullContent = ''
      for await (const chunk of chatApi.stream(id, userInput || '请帮我解读这份报告', fileToSend ?? undefined)) {
        if (chunk.type === 'delta') {
          fullContent += chunk.data
          setStreamingContent(id, fullContent)
        } else if (chunk.type === 'report') {
          try {
            const report = JSON.parse(chunk.data) as ReportRecord
            if (report.status === 'pending') {
              setPendingReport(id, report)
              setExtractingReport(id, false)
            }
          } catch (e) {
            console.error('Failed to parse report event:', e)
          }
        } else if (chunk.type === 'error') {
          throw new Error(chunk.data)
        }
      }

      const aiMsg: ChatMessage = {
        role: 'assistant',
        content: fullContent || '(空回复)',
        timestamp: new Date().toISOString(),
      }
      appendMessage(id, aiMsg)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'AI 服务暂时不可用'
      setError(id, errorMsg)
      const aiMsg: ChatMessage = {
        role: 'assistant',
        content: `抱歉，处理您的请求时出错了：${errorMsg}。请稍后重试。`,
        timestamp: new Date().toISOString(),
      }
      appendMessage(id, aiMsg)
    } finally {
      setStreaming(id, false)
      setStreamingContent(id, '')
      setExtractingReport(id, false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!currentMemberId) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-rounded text-5xl text-slate-300">person_add</span>
          <p className="mt-3 text-slate-500">请先在侧边栏选择家庭成员</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-primary">forum</span>
          <h1 className="text-lg font-medium text-slate-800">AI 健康咨询</h1>
          {currentMember && (
            <span className="ml-2 rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary">
              {currentMember.name}
            </span>
          )}
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto bg-bg-secondary px-6 py-4">
        {isLoadingHistory && (
          <div className="flex h-full items-center justify-center">
            <div className="flex items-center gap-2 text-slate-400">
              <span className="material-symbols-rounded animate-spin">progress_activity</span>
              <span className="text-sm">正在加载历史对话...</span>
            </div>
          </div>
        )}
        {messages.length === 0 && !isLoadingHistory && !isStreaming && (
          <div className="flex h-full items-center justify-center">
            <div className="max-w-md text-center">
              <span className="material-symbols-rounded text-5xl text-slate-300">chat_bubble_outline</span>
              <p className="mt-3 text-slate-500">开始和 AI 聊聊健康吧。你可以问：</p>
              <div className="mt-3 space-y-2 text-sm text-slate-400">
                <p>"我最近的血压怎么样？"</p>
                <p>"血糖 6.5 正常吗？"</p>
                <p>"我哪些指标不正常？"</p>
                <p>"我今天测了血压 130/85"</p>
                <p className="text-primary">也支持上传报告图片/PDF，AI 直接解读</p>
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatBubble key={i} message={msg} />
        ))}

        {isStreaming && (
          <ChatBubble
            message={{
              role: 'assistant',
              content: streamingContent || 'AI 思考中...',
              timestamp: new Date().toISOString(),
            }}
            isStreaming
          />
        )}

        {error && (
          <div className="mb-4 rounded-field border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-600">
            {error}
          </div>
        )}
      </div>

      {/* File preview */}
      {attachedFile && (
        <div className="flex items-center gap-3 border-t border-slate-200 bg-slate-50 px-6 py-2">
          {previewUrl ? (
            <img src={previewUrl} alt="预览" className="h-12 w-12 rounded-field object-cover" />
          ) : (
            <div className="flex h-12 w-12 items-center justify-center rounded-field bg-primary-light">
              <span className="material-symbols-rounded text-primary">description</span>
            </div>
          )}
          <span className="flex-1 truncate text-sm text-slate-600">{attachedFile.name}</span>
          <button
            onClick={handleRemoveFile}
            className="flex h-7 w-7 items-center justify-center rounded-full text-slate-400 hover:bg-slate-200 hover:text-slate-600"
          >
            <span className="material-symbols-rounded text-lg">close</span>
          </button>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-slate-200 bg-white px-6 py-4">
        {/* Report extraction card */}
        {extractingReport && (
          <div className="mb-3 flex items-center gap-2 rounded-field border border-blue-200 bg-blue-50 px-4 py-2">
            <span className="material-symbols-rounded animate-spin text-blue-500">progress_activity</span>
            <span className="text-sm text-blue-600">正在提取报告结构化数据...</span>
          </div>
        )}
        {pendingReport && (
          <div className="mb-3 flex items-center gap-3 rounded-field border border-green-200 bg-green-50 px-4 py-2.5">
            <span className="material-symbols-rounded text-green-600">check_circle</span>
            <div className="flex-1">
              <p className="text-sm font-medium text-slate-700">报告已解析完成</p>
              <p className="text-xs text-slate-500">
                {pendingReport.report_type || '健康报告'} · {pendingReport.extraction?.metrics.length || 0} 项指标 · {pendingReport.extraction?.lab_tests.length || 0} 项检验 · {pendingReport.extraction?.exam_findings.length || 0} 项检查
              </p>
            </div>
            <button
              onClick={() => setShowReportModal(true)}
              className="rounded-field bg-primary px-3 py-1.5 text-xs text-white hover:bg-primary-hover"
            >
              确认入档
            </button>
            <button
              onClick={() => { if (memberId != null) setPendingReport(memberId, null) }}
              className="rounded-field p-1 text-slate-400 hover:text-slate-600"
            >
              <span className="material-symbols-rounded text-base">close</span>
            </button>
          </div>
        )}
        <div className="flex items-end gap-3">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf"
            onChange={handleFileSelect}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isStreaming}
            className="flex h-11 w-11 items-center justify-center rounded-field border border-slate-200 text-slate-500 transition hover:bg-slate-50 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
            title="上传图片或PDF"
          >
            <span className="material-symbols-rounded">attach_file</span>
          </button>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={attachedFile ? "描述你的问题，或直接发送让 AI 解读..." : "输入健康问题，也可粘贴图片... (Enter 发送)"}
            rows={1}
            disabled={isStreaming}
            className="flex-1 resize-none rounded-field border border-slate-200 px-4 py-2.5 text-sm focus:border-primary focus:outline-none disabled:bg-slate-50"
            style={{ minHeight: '44px', maxHeight: '120px' }}
          />
          <button
            onClick={handleSend}
            disabled={(!input.trim() && !attachedFile) || isStreaming}
            className="flex h-11 w-11 items-center justify-center rounded-field bg-primary text-white transition hover:bg-primary-hover disabled:bg-primary-disabled disabled:cursor-not-allowed"
          >
            <span className="material-symbols-rounded">{isStreaming ? 'hourglass_empty' : 'send'}</span>
          </button>
        </div>
      </div>

      {/* Report confirm modal */}
      {showReportModal && pendingReport && (
        <ReportConfirmModal
          report={pendingReport}
          uploadSource="chat"
          onClose={() => { setShowReportModal(false); if (memberId != null) setPendingReport(memberId, null) }}
        />
      )}
    </div>
  )
}
