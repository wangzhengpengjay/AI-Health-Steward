import { useState, useRef, useEffect } from 'react'
import { useMemberStore } from '@/stores/memberStore'
import { chatApi } from '@/lib/api'
import type { ChatMessage } from '@/types'
import ChatBubble from '@/components/ChatBubble'

export default function Chat() {
  const { currentMemberId, members } = useMemberStore()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const currentMember = members.find((m) => m.id === currentMemberId)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, streamingContent])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
    if (!validTypes.includes(file.type)) {
      setError('仅支持 JPG/PNG/WebP/PDF 格式')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      setError('文件大小不能超过 20MB')
      return
    }
    setAttachedFile(file)
    setError(null)
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

  const handleSend = async () => {
    if ((!input.trim() && !attachedFile) || isStreaming) return
    if (!currentMemberId) {
      setError('请先选择家庭成员')
      return
    }

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
    setMessages((prev) => [...prev, userMsg])
    const userInput = input.trim()
    const fileToSend = attachedFile
    setInput('')
    handleRemoveFile()
    setError(null)
    setIsStreaming(true)
    setStreamingContent('')

    try {
      let fullContent = ''
      for await (const chunk of chatApi.stream(Number(currentMemberId), userInput || '请帮我解读这份报告', fileToSend ?? undefined)) {
        fullContent += chunk
        setStreamingContent(fullContent)
      }

      const aiMsg: ChatMessage = {
        role: 'assistant',
        content: fullContent || '(空回复)',
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, aiMsg])
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'AI 服务暂时不可用'
      setError(errorMsg)
      const aiMsg: ChatMessage = {
        role: 'assistant',
        content: `抱歉，处理您的请求时出错了：${errorMsg}。请稍后重试。`,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, aiMsg])
    } finally {
      setIsStreaming(false)
      setStreamingContent('')
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
        {messages.length === 0 && !isStreaming && (
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
            placeholder={attachedFile ? "描述你的问题，或直接发送让 AI 解读..." : "输入您的健康问题... (Enter 发送, Shift+Enter 换行)"}
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
    </div>
  )
}
