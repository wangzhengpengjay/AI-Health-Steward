import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, feishuApi, membersApi, type ProviderConfig, type ProviderUpdatePayload, type FeishuChannel } from '@/lib/api'

interface EditState {
  multimodal_api_base: string
  multimodal_api_key: string
  multimodal_api_model: string
  text_api_base: string
  text_api_key: string
  text_api_model: string
  local_llm_base: string
  local_llm_model: string
  text_provider_priority: string
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<EditState | null>(null)
  const [showWipeConfirm, setShowWipeConfirm] = useState(false)
  const [wipeResult, setWipeResult] = useState<string | null>(null)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  const { data: providers, isLoading } = useQuery({
    queryKey: ['settings-providers'],
    queryFn: settingsApi.getProviders,
  })

  const { data: feishuChannels, refetch: refetchFeishu } = useQuery({
    queryKey: ['feishu-channels'],
    queryFn: feishuApi.listChannels,
  })

  const { data: members } = useQuery({
    queryKey: ['members'],
    queryFn: membersApi.list,
  })

  const [showChannelModal, setShowChannelModal] = useState(false)
  const [editingChannel, setEditingChannel] = useState<FeishuChannel | null>(null)

  const channelSaveMutation = useMutation({
    mutationFn: (data: { id?: number; name: string; app_id: string; app_secret: string; member_id: number | null; is_active: boolean }) => {
      const { id, ...payload } = data
      if (id) return feishuApi.updateChannel(id, payload)
      return feishuApi.createChannel(payload)
    },
    onSuccess: () => {
      setShowChannelModal(false)
      setEditingChannel(null)
      refetchFeishu()
    },
  })

  const channelDeleteMutation = useMutation({
    mutationFn: (id: number) => feishuApi.deleteChannel(id),
    onSuccess: () => refetchFeishu(),
  })

  const healthMutation = useMutation({
    mutationFn: settingsApi.checkHealth,
  })

  const exportMutation = useMutation({
    mutationFn: settingsApi.exportData,
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `health-data-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.json`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const wipeMutation = useMutation({
    mutationFn: settingsApi.wipeData,
    onSuccess: (data) => {
      setWipeResult(data.message)
      setShowWipeConfirm(false)
    },
  })

  const saveMutation = useMutation({
    mutationFn: (data: ProviderUpdatePayload) => settingsApi.updateProviders(data),
    onSuccess: (data) => {
      setSaveMsg(data.message)
      setEditing(false)
      setForm(null)
      queryClient.invalidateQueries({ queryKey: ['settings-providers'] })
      setTimeout(() => setSaveMsg(null), 3000)
    },
  })

  const startEdit = () => {
    if (!providers) return
    setForm({
      multimodal_api_base: providers.multimodal_api.base_url,
      multimodal_api_key: '',
      multimodal_api_model: providers.multimodal_api.model,
      text_api_base: providers.text_api.base_url,
      text_api_key: '',
      text_api_model: providers.text_api.model,
      local_llm_base: providers.local_llm.base_url,
      local_llm_model: providers.local_llm.model,
      text_provider_priority: providers.text_provider_priority,
    })
    setEditing(true)
    setSaveMsg(null)
  }

  const handleSave = () => {
    if (!form) return
    const payload: ProviderUpdatePayload = {}
    if (form.multimodal_api_base !== providers!.multimodal_api.base_url)
      payload.multimodal_api_base = form.multimodal_api_base
    if (form.multimodal_api_key)
      payload.multimodal_api_key = form.multimodal_api_key
    if (form.multimodal_api_model !== providers!.multimodal_api.model)
      payload.multimodal_api_model = form.multimodal_api_model
    if (form.text_api_base !== providers!.text_api.base_url)
      payload.text_api_base = form.text_api_base
    if (form.text_api_key)
      payload.text_api_key = form.text_api_key
    if (form.text_api_model !== providers!.text_api.model)
      payload.text_api_model = form.text_api_model
    if (form.local_llm_base !== providers!.local_llm.base_url)
      payload.local_llm_base = form.local_llm_base
    if (form.local_llm_model !== providers!.local_llm.model)
      payload.local_llm_model = form.local_llm_model
    if (form.text_provider_priority !== providers!.text_provider_priority)
      payload.text_provider_priority = form.text_provider_priority
    saveMutation.mutate(payload)
  }

  if (isLoading || !providers) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="material-symbols-rounded animate-spin text-3xl text-primary">
          progress_activity
        </span>
      </div>
    )
  }

  const health = healthMutation.data

  const inputCls = "w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
  const labelCls = "mb-1 block text-xs text-slate-400"

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="material-symbols-rounded text-2xl text-primary">settings</span>
          <h1 className="text-xl font-semibold text-slate-800">设置</h1>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button
                onClick={() => { setEditing(false); setForm(null) }}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saveMutation.isPending}
                className="rounded-lg bg-primary px-3 py-1.5 text-sm text-white transition hover:bg-primary-dark disabled:opacity-50"
              >
                {saveMutation.isPending ? '保存中...' : '保存'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => healthMutation.mutate()}
                disabled={healthMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg border border-primary px-3 py-1.5 text-sm text-primary transition hover:bg-primary/5 disabled:opacity-50"
              >
                <span className="material-symbols-rounded text-base">
                  {healthMutation.isPending ? 'progress_activity' : 'monitoring'}
                </span>
                {healthMutation.isPending ? '检测中' : '健康检测'}
              </button>
              <button
                onClick={startEdit}
                className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm text-white transition hover:bg-primary-dark"
              >
                <span className="material-symbols-rounded text-base">edit</span>
                编辑配置
              </button>
            </>
          )}
        </div>
      </div>

      {saveMsg && (
        <div className="flex items-center gap-2 rounded-lg bg-emerald-50 px-4 py-2.5 text-sm text-emerald-600">
          <span className="material-symbols-rounded text-base">check_circle</span>
          {saveMsg}
        </div>
      )}

      {/* Model Provider Config */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-slate-500">模型配置</h2>
        {editing && form ? (
          <div className="space-y-4">
            {/* Multimodal */}
            <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
              <div className="mb-3 flex items-center gap-2">
                <span className="material-symbols-rounded text-xl text-primary">visibility</span>
                <h3 className="font-medium text-slate-800">多模态模型</h3>
                <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-500">必选</span>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div>
                  <label className={labelCls}>接口地址</label>
                  <input className={inputCls} value={form.multimodal_api_base}
                    onChange={e => setForm({ ...form, multimodal_api_base: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>模型 ID</label>
                  <input className={inputCls} value={form.multimodal_api_model}
                    onChange={e => setForm({ ...form, multimodal_api_model: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>API Key（留空不修改）</label>
                  <input className={inputCls} type="password" placeholder={providers.multimodal_api.api_key}
                    value={form.multimodal_api_key}
                    onChange={e => setForm({ ...form, multimodal_api_key: e.target.value })} />
                </div>
              </div>
            </div>
            {/* Text API */}
            <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
              <div className="mb-3 flex items-center gap-2">
                <span className="material-symbols-rounded text-xl text-primary">chat</span>
                <h3 className="font-medium text-slate-800">文本模型 (API)</h3>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div>
                  <label className={labelCls}>接口地址</label>
                  <input className={inputCls} value={form.text_api_base}
                    onChange={e => setForm({ ...form, text_api_base: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>模型 ID</label>
                  <input className={inputCls} value={form.text_api_model}
                    onChange={e => setForm({ ...form, text_api_model: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>API Key（留空不修改）</label>
                  <input className={inputCls} type="password" placeholder={providers.text_api.api_key}
                    value={form.text_api_key}
                    onChange={e => setForm({ ...form, text_api_key: e.target.value })} />
                </div>
              </div>
            </div>
            {/* Local LLM */}
            <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
              <div className="mb-3 flex items-center gap-2">
                <span className="material-symbols-rounded text-xl text-primary">dns</span>
                <h3 className="font-medium text-slate-800">本地文本模型</h3>
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <label className={labelCls}>接口地址</label>
                  <input className={inputCls} value={form.local_llm_base}
                    onChange={e => setForm({ ...form, local_llm_base: e.target.value })} />
                </div>
                <div>
                  <label className={labelCls}>模型名称</label>
                  <input className={inputCls} value={form.local_llm_model}
                    onChange={e => setForm({ ...form, local_llm_model: e.target.value })} />
                </div>
              </div>
            </div>
            {/* Priority */}
            <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
              <h3 className="mb-3 font-medium text-slate-800">文本路由优先级</h3>
              <div className="flex gap-4">
                {[{ v: 'text_api', l: '云端 API 优先' }, { v: 'local_llm', l: '本地模型优先' }].map(opt => (
                  <label key={opt.v} className="flex items-center gap-2 cursor-pointer">
                    <input type="radio" name="priority" value={opt.v}
                      checked={form.text_provider_priority === opt.v}
                      onChange={e => setForm({ ...form, text_provider_priority: e.target.value })}
                      className="accent-primary" />
                    <span className="text-sm text-slate-700">{opt.l}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <ProviderCard title="多模态模型" icon="visibility" cfg={providers.multimodal_api}
                health={health?.multimodal_api} checking={healthMutation.isPending} required />
              <ProviderCard title="文本模型 (API)" icon="chat" cfg={providers.text_api}
                health={health?.text_api} checking={healthMutation.isPending} />
              <ProviderCard title="本地文本模型" icon="dns" cfg={providers.local_llm}
                health={health?.local_llm} checking={healthMutation.isPending} />
              <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
                <h3 className="mb-3 font-medium text-slate-800">文本路由优先级</h3>
                <p className="text-sm text-slate-500">
                  当前优先级：<code className="rounded bg-slate-100 px-1.5 py-0.5 text-primary">
                    {providers.text_provider_priority}
                  </code>
                </p>
                <p className="mt-2 text-xs text-slate-400">
                  text_api 优先使用云端文本 API；local_llm 优先使用本地模型。未配置时自动回退。
                </p>
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-400">
              点击"编辑配置"可在线修改模型配置，保存后即时写入 .env 并生效。
            </p>
          </>
        )}
      </section>

      {/* Feishu Bot */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-500">飞书机器人</h2>
          <button
            onClick={() => { setEditingChannel(null); setShowChannelModal(true) }}
            className="flex items-center gap-1.5 rounded-lg border border-primary px-3 py-1.5 text-sm text-primary transition hover:bg-primary/5"
          >
            <span className="material-symbols-rounded text-base">add</span>
            添加渠道
          </button>
        </div>

        {!feishuChannels || feishuChannels.length === 0 ? (
          <div className="rounded-card border border-dashed border-slate-300 bg-bg-primary p-8 text-center">
            <span className="material-symbols-rounded text-3xl text-slate-300">chat</span>
            <p className="mt-2 text-sm text-slate-400">
              暂无飞书渠道。添加渠道后，可通过飞书 Bot 接收报告和轻问答。
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {feishuChannels.map((ch) => (
              <div key={ch.id} className="rounded-card border border-slate-200 bg-bg-primary p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${ch.connected ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                    <span className="font-medium text-slate-800">{ch.name}</span>
                    {!ch.is_active && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-400">已停用</span>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => { setEditingChannel(ch); setShowChannelModal(true) }}
                      className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    >
                      <span className="material-symbols-rounded text-base">edit</span>
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`删除渠道"${ch.name}"？`)) channelDeleteMutation.mutate(ch.id)
                      }}
                      className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                    >
                      <span className="material-symbols-rounded text-base">delete</span>
                    </button>
                  </div>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <div><dt className="text-slate-400">App ID</dt><dd className="text-slate-700">{ch.app_id || '-'}</dd></div>
                  <div><dt className="text-slate-400">绑定成员</dt><dd className="text-slate-700">{ch.member_name || '默认本人'}</dd></div>
                </dl>
              </div>
            ))}
          </div>
        )}

        {showChannelModal && (
          <ChannelModal
            channel={editingChannel}
            members={members}
            onSave={(data) => channelSaveMutation.mutate(data)}
            onClose={() => { setShowChannelModal(false); setEditingChannel(null) }}
            saving={channelSaveMutation.isPending}
          />
        )}
      </section>

      {/* Data Management */}      {/* Data Management */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-slate-500">数据管理</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
            <div className="mb-2 flex items-center gap-2">
              <span className="material-symbols-rounded text-xl text-primary">download</span>
              <h3 className="font-medium text-slate-800">数据导出</h3>
            </div>
            <p className="mb-4 text-sm text-slate-500">
              导出全部家庭成员的健康数据为 JSON 文件。
            </p>
            <button
              onClick={() => exportMutation.mutate()}
              disabled={exportMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-primary px-3 py-1.5 text-sm text-primary transition hover:bg-primary/5 disabled:opacity-50"
            >
              <span className="material-symbols-rounded text-base">
                {exportMutation.isPending ? 'progress_activity' : 'file_download'}
              </span>
              导出数据
            </button>
          </div>
          <div className="rounded-card border border-red-200 bg-red-50/30 p-5">
            <div className="mb-2 flex items-center gap-2">
              <span className="material-symbols-rounded text-xl text-red-500">dangerous</span>
              <h3 className="font-medium text-slate-800">清除数据</h3>
            </div>
            <p className="mb-4 text-sm text-slate-500">
              删除所有健康数据，此操作不可恢复。建议先导出备份。
            </p>
            {!showWipeConfirm ? (
              <button
                onClick={() => setShowWipeConfirm(true)}
                className="flex items-center gap-1.5 rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-600 transition hover:bg-red-50"
              >
                <span className="material-symbols-rounded text-base">delete_forever</span>
                清除全部数据
              </button>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-medium text-red-600">确认清除所有数据？不可恢复！</p>
                <div className="flex gap-2">
                  <button
                    onClick={() => wipeMutation.mutate()}
                    disabled={wipeMutation.isPending}
                    className="rounded-lg bg-red-500 px-3 py-1.5 text-sm text-white transition hover:bg-red-600 disabled:opacity-50"
                  >
                    {wipeMutation.isPending ? '清除中...' : '确认清除'}
                  </button>
                  <button
                    onClick={() => setShowWipeConfirm(false)}
                    className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
                  >
                    取消
                  </button>
                </div>
              </div>
            )}
            {wipeResult && <p className="mt-2 text-sm text-emerald-600">{wipeResult}</p>}
          </div>
        </div>
      </section>

      {/* System Info */}
      <section>
        <h2 className="mb-3 text-sm font-medium text-slate-500">系统信息</h2>
        <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
          <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
            <div><dt className="text-slate-400">应用版本</dt><dd className="text-slate-700">v0.1.0</dd></div>
            <div><dt className="text-slate-400">部署模式</dt><dd className="text-slate-700">单实例 · 单家庭</dd></div>
            <div><dt className="text-slate-400">数据库</dt><dd className="text-slate-700">PostgreSQL 16</dd></div>
            <div><dt className="text-slate-400">向量扩展</dt><dd className="text-slate-700">pgvector</dd></div>
          </dl>
        </div>
      </section>
    </div>
  )
}

// ---- Provider Card (read-only display) ----

interface ProviderCardProps {
  title: string
  icon: string
  cfg: ProviderConfig
  health?: { status: string; latency_ms?: number; error?: string }
  checking: boolean
  required?: boolean
}

function ProviderCard({ title, icon, cfg, health, checking, required }: ProviderCardProps) {
  const statusColor = !cfg.is_configured
    ? 'bg-slate-100 text-slate-500'
    : health?.status === 'ok'
      ? 'bg-emerald-50 text-emerald-600'
      : health?.status === 'error'
        ? 'bg-red-50 text-red-600'
        : 'bg-amber-50 text-amber-600'

  const statusText = !cfg.is_configured
    ? '未配置'
    : checking
      ? '检测中...'
      : health?.status === 'ok'
        ? `正常${health.latency_ms ? ` · ${health.latency_ms}ms` : ''}`
        : health?.status === 'error'
          ? '异常'
          : '待检测'

  return (
    <div className="rounded-card border border-slate-200 bg-bg-primary p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="material-symbols-rounded text-xl text-primary">{icon}</span>
          <h3 className="font-medium text-slate-800">{title}</h3>
          {required && (
            <span className="rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-500">必选</span>
          )}
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor}`}>{statusText}</span>
      </div>
      <dl className="space-y-1.5 text-sm">
        <div className="flex justify-between gap-2">
          <dt className="text-slate-400">接口地址</dt>
          <dd className="truncate text-slate-700">{cfg.base_url || '-'}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-400">模型</dt>
          <dd className="text-slate-700">{cfg.model || '-'}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-slate-400">API Key</dt>
          <dd className="font-mono text-slate-700">{cfg.api_key || '-'}</dd>
        </div>
      </dl>
      {health?.error && <p className="mt-2 text-xs text-red-500">{health.error}</p>}
    </div>
  )
}


interface ChannelModalProps {
  channel: FeishuChannel | null
  members: unknown
  onSave: (data: { id?: number; name: string; app_id: string; app_secret: string; member_id: number | null; is_active: boolean }) => void
  onClose: () => void
  saving: boolean
}

function ChannelModal({ channel, members, onSave, onClose, saving }: ChannelModalProps) {
  const [name, setName] = useState(channel?.name || '')
  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [memberId, setMemberId] = useState<number | null>(channel?.member_id || null)
  const [isActive, setIsActive] = useState(channel?.is_active ?? true)

  const memberList = (Array.isArray(members) ? members : []) as { id: number; name: string }[]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <h3 className="mb-4 text-lg font-medium text-slate-800">
          {channel ? '编辑飞书渠道' : '添加飞书渠道'}
        </h3>
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-slate-500">渠道名称</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="如：爸爸的飞书"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-500">App ID</label>
            <input
              value={appId}
              onChange={e => setAppId(e.target.value)}
              placeholder={channel ? "留空不修改" : "cli_xxxxxxxx"}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-500">
              App Secret {channel && <span className="text-xs text-slate-400">（留空不修改）</span>}
            </label>
            <input
              type="password"
              value={appSecret}
              onChange={e => setAppSecret(e.target.value)}
              placeholder={channel ? '留空不修改' : '输入 App Secret'}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-500">绑定成员</label>
            <select
              value={memberId ?? 0}
              onChange={e => setMemberId(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-primary focus:outline-none"
            >
              <option value={0}>默认本人（第一个成员）</option>
              {memberList.map(m => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={isActive} onChange={e => setIsActive(e.target.checked)} />
            启用此渠道
          </label>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 transition hover:bg-slate-50"
          >
            取消
          </button>
          <button
            onClick={() => onSave({
              id: channel?.id,
              name,
              app_id: appId || (channel ? '__unchanged__' : ''),
              app_secret: appSecret || (channel ? '__unchanged__' : ''),
              member_id: memberId,
              is_active: isActive,
            })}
            disabled={saving || !name}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-white transition hover:bg-primary/90 disabled:opacity-50"
          >
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
