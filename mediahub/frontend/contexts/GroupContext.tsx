'use client'

import { createContext, useContext, useState, useEffect } from 'react'
import type { Group } from '@/lib/types'
import { api } from '@/lib/api'
import { useAuth } from './AuthContext'

interface GroupCtx {
  groups: Group[]
  currentGroup: Group | null
  myRole: string | null
  loading: boolean
  switchGroup: (groupId: number) => void
  refreshGroups: () => Promise<void>
}

const GroupContext = createContext<GroupCtx>({
  groups: [],
  currentGroup: null,
  myRole: null,
  loading: true,
  switchGroup: () => {},
  refreshGroups: async () => {},
})

export function GroupProvider({ children }: { children: React.ReactNode }) {
  const { user, token } = useAuth()
  const [groups, setGroups] = useState<Group[]>([])
  const [currentGroup, setCurrentGroup] = useState<Group | null>(null)
  const [loading, setLoading] = useState(true)

  const refreshGroups = async () => {
    if (!user || !token) return
    try {
      const data = await api.getGroups()
      setGroups(data)
      const stored = localStorage.getItem('mediahub_current_group')
      const storedGroupId = stored ? parseInt(stored) : data[0]?.id
      if (storedGroupId) {
        const group = data.find(g => g.id === storedGroupId) || data[0]
        if (group) {
          setCurrentGroup(group)
          localStorage.setItem('mediahub_current_group', group.id.toString())
        }
      }
    } catch (e) {
      console.error('Failed to load groups:', e)
    }
  }

  useEffect(() => {
    if (user && token) {
      refreshGroups().finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [user, token])

  const switchGroup = (groupId: number) => {
    const group = groups.find(g => g.id === groupId)
    if (group) {
      setCurrentGroup(group)
      localStorage.setItem('mediahub_current_group', groupId.toString())
    }
  }

  return (
    <GroupContext.Provider
      value={{
        groups,
        currentGroup,
        myRole: currentGroup?.role || null,
        loading,
        switchGroup,
        refreshGroups,
      }}
    >
      {children}
    </GroupContext.Provider>
  )
}

export const useGroup = () => useContext(GroupContext)
