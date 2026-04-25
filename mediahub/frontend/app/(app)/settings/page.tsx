'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import type { User } from '@/lib/types'

const ROLES = [
  { v: 'admin',    l: 'Администратор', d: 'Полный доступ ко всем функциям' },
  { v: 'editor',   l: 'Редактор',      d: 'Создание и редактирование постов' },
  { v: 'observer', l: 'Наблюдатель',   d: 'Только просмотр аналитики' },
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
          <span className="card-title">Управление пользователями</span>
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
                    <div style={{
                      width: 30, height: 30, borderRadius: '50%',
                      background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
                      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontWeight: 700, fontSize: 12, flexShrink: 0,
                    }}>
                      {u.name[0].toUpperCase()}
                    </div>
                    <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>{u.name}</span>
                  </div>
                </td>
                <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{u.email}</td>
                <td><span className={`user-role-lbl ${RC[u.role]}`}>{ROLES.find(r => r.v === u.role)?.l ?? u.role}</span></td>
                {user?.role === 'admin' && (
                  <td>
                    <select value={u.role} onChange={e => changeRole(u.id, e.target.value)}
                      style={{ width: 'auto', padding: '6px 10px', fontSize: 12 }}>
                      {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card card-p" style={{ marginTop: 16 }}>
        <div className="card-title" style={{ marginBottom: 16 }}>О ролях</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {ROLES.map(r => (
            <div key={r.v} style={{
              flex: 1, minWidth: 180,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--r-lg)',
              padding: 14,
            }}>
              <span className={`user-role-lbl ${RC[r.v]}`} style={{ marginBottom: 8, display: 'inline-block' }}>{r.l}</span>
              <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{r.d}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
