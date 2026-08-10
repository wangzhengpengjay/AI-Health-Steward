import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { membersApi, metricsApi, profileApi } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'
import type { FamilyMember } from '@/types'

function relationshipLabel(rel?: string): string {
  const map: Record<string, string> = {
    self: '本人',
    spouse: '配偶',
    parent: '父母',
    child: '子女',
    sibling: '兄弟姐妹',
    grandparent: '祖父母',
    other: '其他',
    '': '成员',
  }
  return map[rel ?? ''] ?? rel ?? '成员'
}

function memberAge(m: FamilyMember): number | null {
  if (!m.birth_date) return null
  const b = new Date(m.birth_date)
  if (Number.isNaN(b.getTime())) return null
  const now = new Date()
  let age = now.getFullYear() - b.getFullYear()
  const mdiff = now.getMonth() - b.getMonth()
  if (mdiff < 0 || (mdiff === 0 && now.getDate() < b.getDate())) age--
  return age
}

function MemberCard({ member }: { member: FamilyMember }) {
  const navigate = useNavigate()
  const setCurrentMember = useMemberStore((s) => s.setCurrentMember)

  // 拉取该成员的指标与画像，聚合异常/危急/完整度
  const { data: metrics = [] } = useQuery({
    queryKey: ['metrics', member.id],
    queryFn: () => metricsApi.list(member.id),
    enabled: !!member.id,
  })
  const { data: profile } = useQuery({
    queryKey: ['profile', member.id],
    queryFn: () => profileApi.get(member.id),
    enabled: !!member.id,
  })

  const critical = metrics.filter(
    (r) => r.is_critical && !r.metric_name.startsWith('lab:') && !r.metric_name.startsWith('exam:'),
  )
  const abnormal = metrics.filter(
    (r) => r.is_abnormal && !r.is_critical && !r.metric_name.startsWith('lab:') && !r.metric_name.startsWith('exam:'),
  )
  const hasProfileData =
    !!profile &&
    (profile.diagnoses.length > 0 ||
      profile.medications.length > 0 ||
      profile.allergies.length > 0 ||
      profile.lifestyles.length > 0 ||
      profile.surgeries.length > 0 ||
      profile.vaccinations.length > 0)

  const open = () => {
    setCurrentMember(member.id)
    navigate('/dashboard')
  }

  const age = memberAge(member)

  return (
    <button
      onClick={open}
      className="group flex flex-col rounded-card border border-slate-200 bg-white p-5 text-left shadow-sm transition-shadow hover:shadow-md"
    >
      <div className="mb-3 flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary-light text-lg font-bold text-primary">
          {member.name.slice(0, 1)}
        </div>
        <div>
          <div className="text-base font-semibold text-slate-800">{member.name}</div>
          <div className="text-xs text-slate-500">
            {relationshipLabel(member.relationship)}
            {age !== null && ` · ${age} 岁`}
          </div>
        </div>
        <span className="ml-auto material-symbols-rounded text-slate-300 transition-colors group-hover:text-primary">
          chevron_right
        </span>
      </div>

      {/* 状态统计 */}
      <div className="grid grid-cols-3 gap-2">
        <div
          className={`rounded-field px-3 py-2 text-center ${
            critical.length > 0 ? 'bg-red-50 ring-1 ring-red-200' : 'bg-bg-tertiary'
          }`}
        >
          <div className={`text-xl font-bold ${critical.length > 0 ? 'text-red-600' : 'text-slate-500'}`}>
            {critical.length}
          </div>
          <div className="text-[11px] text-slate-500">危急值</div>
        </div>
        <div className="rounded-field bg-bg-tertiary px-3 py-2 text-center">
          <div className={`text-xl font-bold ${abnormal.length > 0 ? 'text-amber-600' : 'text-slate-500'}`}>
            {abnormal.length}
          </div>
          <div className="text-[11px] text-slate-500">异常项</div>
        </div>
        <div className="rounded-field bg-bg-tertiary px-3 py-2 text-center">
          <div className="text-xl font-bold text-slate-600">{metrics.length}</div>
          <div className="text-[11px] text-slate-500">数据记录</div>
        </div>
      </div>

      {/* 提醒文案 */}
      <div className="mt-3 min-h-[1.25rem] text-xs">
        {critical.length > 0 ? (
          <span className="font-medium text-red-600">⚠ 存在危急值，请尽快就医</span>
        ) : abnormal.length > 0 ? (
          <span className="text-amber-600">有 {abnormal.length} 项指标异常，建议关注</span>
        ) : !hasProfileData && metrics.length === 0 ? (
          <span className="text-slate-400">暂无数据，点击开始记录</span>
        ) : (
          <span className="text-emerald-600">状态平稳 ✓</span>
        )}
      </div>
    </button>
  )
}

export default function Home() {
  const navigate = useNavigate()
  const { data: members = [] } = useQuery({
    queryKey: ['members'],
    queryFn: membersApi.list,
  })

  return (
    <div className="space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-800">家庭健康速览</h1>
        <p className="mt-1 text-sm text-slate-500">
          全家健康状态一屏掌握，点击任一成员进入详细画像。
        </p>
      </header>

      {members.length === 0 ? (
        <div className="rounded-card border border-slate-200 bg-white p-10 text-center">
          <p className="text-slate-500">还没有成员，先去「成员管理」添加家庭成员吧。</p>
          <button
            onClick={() => navigate('/members')}
            className="mt-4 rounded-field bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-dark"
          >
            前往成员管理
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {members.map((m) => (
            <MemberCard key={m.id} member={m} />
          ))}
        </div>
      )}
    </div>
  )
}