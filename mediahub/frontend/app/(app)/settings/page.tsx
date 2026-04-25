'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import type { User } from '@/lib/types'

const ROLES = [
  { v: 'admin',    l: 'Администратор', d: 'Полный доступ' },
  { v: 'editor',   l: 'Редактор',      d: 'Создание и редактирование' },
  { v: 'observer', l: 'Наблюдатель',   d: 'Только чтение' },
]
const RC: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', observer: 'r-observer' }

export default function SettingsPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const [users, setUsers] = useState<User[]>([])

  useEffect(() => { api.getUsers().then(setUsers).catch(console.error) }, [])

  async function changeRole(id: number, role: string) {
    try {
      const updated = await api.updateUserRole(id, role)
      setUsers(p => p.map(u => u.id === id ? { ...u, role: updated.role } : u))
      showToast('Роль обновлена', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  return (
    <div className="content">
      <div className="card">
        <div className="card-header">
          <span className="card-title">👥 Управление пользователями</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Пользователь</th><th>Email</th><th>Роль</th>
              {user?.role === 'admin' && <th>Изменить роль</th>}
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--blue)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13, flexShrink: 0 }}>
                      {u.avatar || u.name[0]}
                    </div>
                    <span style={{ fontWeight: 600 }}>{u.name}</span>
                  </div>
                </td>
                <td style={{ color: 'var(--gray-500)', fontSize: 13 }}>{u.email}</td>
                <td><span className={`user-role-lbl ${RC[u.role]}`}>{ROLES.find(r => r.v === u.role)?.l ?? u.role}</span></td>
                {user?.role === 'admin' && (
                  <td>
                    <select value={u.role} onChange={e => changeRole(u.id, e.target.value)}
                      style={{ width: 'auto', padding: '6px 10px', fontSize: 13 }}>
                      {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card card-p" style={{ marginTop: 20 }}>
        <div className="card-title" style={{ marginBottom: 16 }}>ℹ️ О ролях</div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {ROLES.map(r => (
            <div key={r.v} style={{ flex: 1, minWidth: 180, background: 'var(--gray-50)', borderRadius: 8, padding: 14 }}>
              <span className={`user-role-lbl ${RC[r.v]}`} style={{ marginBottom: 8, display: 'inline-block' }}>{r.l}</span>
              <div style={{ fontSize: 13, color: 'var(--gray-600)' }}>{r.d}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
