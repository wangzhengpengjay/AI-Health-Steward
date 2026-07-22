import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Sidebar from './Sidebar'
import { membersApi } from '@/lib/api'
import { useMemberStore } from '@/stores/memberStore'

export default function Layout() {
  const setMembers = useMemberStore((s) => s.setMembers)

  // Global member fetch — ensures sidebar has members on any page entry
  const { data: members = [] } = useQuery({
    queryKey: ['members'],
    queryFn: membersApi.list,
  })

  useEffect(() => {
    if (members.length > 0) setMembers(members)
  }, [members, setMembers])

  return (
    <div className="flex h-screen bg-bg-secondary">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
