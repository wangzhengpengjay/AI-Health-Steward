import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage } from '@/types'

const RISK_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  S: { label: 'S级 禁止输出', color: 'text-red-600', bg: 'bg-red-50 border-red-300' },
  A: { label: 'A级 高风险', color: 'text-amber-600', bg: 'bg-amber-50 border-amber-300' },
  B: { label: 'B级 常规', color: 'text-green-600', bg: 'bg-green-50 border-green-300' },
}

const TOOL_LABELS: Record<string, string> = {
  query_metrics: '已查询健康指标',
  query_profile: '已查询诊断/用药记录',
  query_abnormal: '已查询异常指标',
  extract_and_save: '已记录健康数据',
}

interface ChatBubbleProps {
  message: ChatMessage
  isStreaming?: boolean
}

export default function ChatBubble({ message, isStreaming }: ChatBubbleProps) {
  const isUser = message.role === 'user'
  const risk = message.risk_level ? RISK_LABELS[message.risk_level] : null

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`max-w-[80%] rounded-card shadow-sm ${
          isUser
            ? 'bg-primary text-white px-4 py-3'
            : `bg-white border px-4 py-3 ${
                message.risk_level === 'S'
                  ? 'border-red-300'
                  : message.risk_level === 'A'
                    ? 'border-amber-300'
                    : 'border-slate-200'
              }`
        }`}
      >
        {/* High-risk alert banner */}
        {message.isHighRiskAlert && (
          <div className="mb-2 -mx-4 -mt-3 rounded-t-card bg-red-500 px-4 py-1.5 text-sm font-medium text-white">
            <span className="material-symbols-rounded text-sm align-middle mr-1">warning</span>
            建议立即就医
          </div>
        )}

        {/* Tool call badges */}
        {!isUser && message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {message.tool_calls.map((tc, i) => (
              <span
                key={i}
                className="inline-flex items-center rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary"
              >
                <span className="material-symbols-rounded text-xs mr-1">check_circle</span>
                {TOOL_LABELS[tc.name] || tc.name}
              </span>
            ))}
          </div>
        )}

        {/* Message content */}
        <div className={`text-sm leading-relaxed ${isUser ? 'text-white' : 'text-slate-800'}`}>
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm max-w-none prose-headings:my-1 prose-p:my-1 prose-li:my-0 prose-table:text-xs prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1 prose-th:bg-slate-50 prose-pre:bg-slate-50 prose-pre:text-xs">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
              {isStreaming && <span className="inline-block w-1.5 h-4 ml-0.5 bg-primary animate-pulse" />}
            </div>
          )}
        </div>

        {/* Risk label */}
        {!isUser && risk && message.risk_level !== 'B' && (
          <div className={`mt-2 inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${risk.bg} ${risk.color}`}>
            <span className="material-symbols-rounded text-xs mr-1">
              {message.risk_level === 'S' ? 'block' : 'warning'}
            </span>
            {risk.label}
          </div>
        )}

        {/* Disclaimer for AI messages */}
        {!isUser && !isStreaming && (
          <div className="mt-1.5 text-xs text-slate-400">
            本建议仅供健康参考，不替代医生诊断，请遵医嘱
          </div>
        )}

        {/* Timestamp */}
        <div className={`mt-1 text-xs ${isUser ? 'text-primary-disabled' : 'text-slate-400'}`}>
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  )
}
