import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reportsApi, type ReportRecord } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import ReportConfirmModal from '@/components/ReportConfirmModal'

const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  uploaded: { text: '已上传', color: 'bg-slate-100 text-slate-500' },
  extracting: { text: '解析中', color: 'bg-blue-50 text-blue-600' },
  pending: { text: '待确认', color: 'bg-amber-50 text-amber-600' },
  archived: { text: '已入档', color: 'bg-green-50 text-green-600' },
  rejected: { text: '已拒绝', color: 'bg-red-50 text-red-600' },
  cancelled: { text: '已取消', color: 'bg-slate-100 text-slate-400' },
}

const SOURCE_LABELS: Record<string, string> = {
  report_page: '报告管理',
  metric_input: '指标管理',
  chat: 'AI咨询',
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  if (!iso) return '--'
  const d = new Date(iso)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export default function Reports() {
  const { currentMemberId, members } = useMemberStore()
 const queryClient = useQueryClient()
 const [selectedReport, setSelectedReport] = useState<ReportRecord | null>(null)
  const [previewImage, setPreviewImage] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const currentMember = members.find((m) => m.id === currentMemberId)

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['reports', currentMemberId],
    queryFn: () => reportsApi.list(Number(currentMemberId)),
    enabled: !!currentMemberId,
  })

  const uploadMutation = useMutation({
    mutationFn: ({ memberId, file }: { memberId: number; file: File }) =>
      reportsApi.upload(memberId, file, 'report_page'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports', currentMemberId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: ({ memberId, reportId }: { memberId: number; reportId: number }) =>
      reportsApi.delete(memberId, reportId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reports', currentMemberId] })
    },
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f || !currentMemberId) return
    uploadMutation.mutate({ memberId: Number(currentMemberId), file: f })
  }

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

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-primary">description</span>
          <h1 className="text-lg font-medium text-slate-800">报告管理</h1>
          {currentMember && (
            <span className="ml-2 rounded-full bg-primary-light px-2 py-0.5 text-xs text-primary">
              {currentMember.name}
            </span>
          )}
        </div>
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="flex items-center gap-1.5 rounded-field bg-primary px-3 py-2 text-sm text-white transition hover:bg-primary-hover disabled:opacity-50"
        >
          <span className={`material-symbols-rounded text-lg ${uploadMutation.isPending ? 'animate-spin' : ''}`}>
            {uploadMutation.isPending ? 'progress_activity' : 'upload'}
          </span>
          {uploadMutation.isPending ? '解析中...' : '上传报告'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto bg-bg-secondary p-6">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <span className="material-symbols-rounded animate-spin text-3xl text-slate-300">progress_activity</span>
          </div>
        ) : reports.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center text-slate-400">
            <span className="material-symbols-rounded text-5xl">inbox</span>
            <p className="mt-3 text-sm">暂无报告记录，点击"上传报告"开始</p>
            <p className="mt-1 text-xs text-slate-400">支持体检报告、检验单、检查报告等图片/PDF</p>
          </div>
        ) : (
          <div className="space-y-3">
            {reports.map((r) => {
              const status = STATUS_LABELS[r.status] || { text: r.status, color: 'bg-slate-100 text-slate-500' }
              const isPending = r.status === 'pending'
              return (
                <div
                  key={r.id}
                  className="flex items-center gap-4 rounded-card border border-slate-200 bg-white p-4 transition hover:border-primary/30"
                >
                  {/* File thumbnail */}
                  {r.file_type === 'application/pdf' ? (
                    <div className="flex h-12 w-12 items-center justify-center rounded-field bg-slate-50">
                      <span className="material-symbols-rounded text-slate-400">picture_as_pdf</span>
                    </div>
                  ) : (
                    <img
                      src={`/api/v1/members/${currentMemberId}/reports/${r.id}/file`}
                      alt={r.file_name}
                      className="h-12 w-12 cursor-pointer rounded-field object-cover ring-1 ring-slate-200 transition hover:ring-primary"
                      onClick={() => setPreviewImage(`/api/v1/members/${currentMemberId}/reports/${r.id}/file`)}
                    />
                  )}

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-slate-800">{r.file_name}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs ${status.color}`}>{status.text}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-slate-400">
                      <span>{formatDate(r.report_date || r.created_at)}</span>
                      <span>{formatFileSize(r.file_size)}</span>
                      {r.report_type && <span className="truncate">{r.report_type}</span>}
                      <span>来源: {SOURCE_LABELS[r.source] || r.source}</span>
                    </div>
                    {r.status === 'archived' && (
                      <div className="mt-1 flex gap-3 text-xs text-slate-500">
                        {r.saved_metrics > 0 && <span>指标 {r.saved_metrics}</span>}
                        {r.saved_lab_tests > 0 && <span>检验 {r.saved_lab_tests}</span>}
                        {r.saved_exam_findings > 0 && <span>检查 {r.saved_exam_findings}</span>}
                        {r.saved_diagnoses > 0 && <span>诊断 {r.saved_diagnoses}</span>}
                        {r.saved_medications > 0 && <span>用药 {r.saved_medications}</span>}
                      </div>
                    )}
                    {r.summary && r.status === 'archived' && (
                      <p className="mt-1 text-xs text-slate-400 line-clamp-1">{r.summary}</p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {isPending && (
                      <button
                        onClick={() => setSelectedReport(r)}
                        className="flex items-center gap-1 rounded-field bg-primary px-3 py-1.5 text-xs text-white hover:bg-primary-hover"
                      >
                        <span className="material-symbols-rounded text-sm">check_circle</span>
                        确认入档
                      </button>
                    )}
                    {r.status === 'archived' && r.extraction && (
                      <button
                        onClick={() => setSelectedReport(r)}
                        className="flex items-center gap-1 rounded-field border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                      >
                        <span className="material-symbols-rounded text-sm">visibility</span>
                        查看详情
                      </button>
                    )}
                    <button
                      onClick={() => {
                        if (confirm('确认删除此报告记录？已入档的数据不会删除。')) {
                          deleteMutation.mutate({ memberId: Number(currentMemberId), reportId: r.id })
                        }
                      }}
                      className="flex items-center justify-center rounded-field p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500"
                      title="删除"
                    >
                      <span className="material-symbols-rounded text-base">delete</span>
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {uploadMutation.isError && (
          <div className="mt-4 rounded-field border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-600">
            上传失败: {uploadMutation.error instanceof Error ? uploadMutation.error.message : '未知错误'}
          </div>
        )}
      </div>

      {/* Confirm / View modal */}
      {selectedReport && (
        <ReportConfirmModal
          report={selectedReport}
          onClose={() => setSelectedReport(null)}
        />
      )}

      {/* Image preview modal */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8"
          onClick={() => setPreviewImage(null)}
        >
          <img
            src={previewImage}
            alt="报告原图"
            className="max-h-full max-w-full rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            className="absolute right-4 top-4 rounded-full bg-white/20 p-2 text-white hover:bg-white/30"
            onClick={() => setPreviewImage(null)}
          >
            <span className="material-symbols-rounded">close</span>
          </button>
        </div>
      )}
    </div>
  )
}
