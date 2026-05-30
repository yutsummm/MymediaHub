'use client'

import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { Group } from '@/lib/types'
import { api } from '@/lib/api'
import { useAuth } from './AuthContext'

const lsSafe = {
  get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v) } catch {} },
}

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

function restoreCache(): { groups: Group[]; currentGroup: Group | null } {
  const raw = lsSafe.get('mediahub_groups_cache')
  if (!raw) return { groups: [], currentGroup: null }
  try {
    const groups = JSON.parse(raw) as Group[]
    const sid = lsSafe.get('mediahub_current_group')
    const sidNum = sid ? parseInt(sid) : null
    const cur = sidNum ? groups.find(x => x.id === sidNum) || groups[0] || null : groups[0] || null
    return { groups, currentGroup: cur }
  } catch {
    return { groups: [], currentGroup: null }
  }
}

export function GroupProvider({ children }: { children: React.ReactNode }) {
  const { user, token } = useAuth()
  const [groups, setGroups] = useState<Group[]>([])
  const [currentGroup, setCurrentGroup] = useState<Group | null>(null)
  const [loading, setLoading] = useState(true)
  const [restored, setRestored] = useState(false)

  // Step 1: restore cached groups immediately after hydration
  useEffect(() => {
    const { groups: cg, currentGroup: cc } = restoreCache()
    if (cg.length > 0) {
      setGroups(cg)
      if (cc) setCurrentGroup(cc)
    }
    setRestored(true)
  }, [])

  const refreshGroups = useCallback(async () => {
    if (!token) return
    try {
      const data = await api.getGroups()
      setGroups(data)
      lsSafe.set('mediahub_groups_cache', JSON.stringify(data))
      const stored = lsSafe.get('mediahub_current_group')
      const storedGroupId = stored ? parseInt(stored) : data[0]?.id
      if (storedGroupId) {
        const group = data.find(g => g.id === storedGroupId) || data[0]
        if (group) {
          setCurrentGroup(group)
          lsSafe.set('mediahub_current_group', group.id.toString())
        }
      } else if (data.length > 0) {
        setCurrentGroup(data[0])
        lsSafe.set('mediahub_current_group', data[0].id.toString())
      }
    } catch (e) {
      console.error('Failed to load groups:', e)
    }
  }, [token])

  // Step 2: show cached data immediately, refresh from API in background
  useEffect(() => {
    if (!restored) return
    if (!token) {
      setLoading(false)
      return
    }
    // Refresh in background — don't block rendering
    refreshGroups()
    setLoading(false)
  }, [restored, token, refreshGroups])

  const switchGroup = (groupId: number) => {
    const group = groups.find(g => g.id === groupId)
    if (group) {
      setCurrentGroup(group)
      lsSafe.set('mediahub_current_group', groupId.toString())
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
