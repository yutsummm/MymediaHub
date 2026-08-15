'use client'
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { api } from '@/lib/api'
import StateWrapper from '@/components/StateWrapper'
import type { User } from '@/lib/types'

const S = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const ROLES = [
  { value: 'admin',     label: 'Администратор', hint: 'Управляет пользователями и глобальными настройками' },
  { value: 'editor',    label: 'Редактор',      hint: 'Создаёт и публикует посты' },
  { value: 'volunteer', label: 'Волонтёр',      hint: 'Только загружает медиа' },
]
const ROLE_CLASS: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', volunteer: 'r-volunteer' }
const ROLE_LABEL: Record<string, string> = Object.fromEntries(ROLES.map(r => [r.value, r.label]))

export default function UsersPage() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const router = useRouter()

  const [users, setUsers] = useState<User[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'editor' })

  const load = useCallback(() => {
    setError('')
    api.getUsers()
      .then(d => setUsers(d.users))
      .catch(e => setError((e as Error).message))
  }, [])

  useEffect(() => {
    if (!user) return
    if (user.role !== 'admin') { router.replace('/dashboard'); return }
    load()
  }, [user, router, load])

  // Последнего администратора снимать нельзя: не останется никого, кто может
  // назначить нового, и управление пользователями закроется навсегда.
  const admins = (users ?? []).filter(u => u.role === 'admin')

  async function changeRole(target: User, role: string) {
    if (role === target.role) return
    if (target.role === 'admin' && role !== 'admin' && admins.length <= 1) {
      showToast('Это единственный администратор. Сначала назначьте другого', 'error')
      return
    }
    setBusy(target.id)
    try {
      await api.updateUserRole(target.id, role)
      showToast(`${target.name} — теперь ${ROLE_LABEL[role].toLowerCase()}`, 'success')
      load()
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  async function remove(target: User) {
    if (target.role === 'admin' && admins.length <= 1) {
      showToast('Нельзя удалить единственного администратора', 'error')
      return
    }
    if (!confirm(`Удалить ${target.name} (${target.email})? Действие необратимо.`)) return
    setBusy(target.id)
    try {
      await api.deleteUser(target.id)
      showToast('Пользователь удалён', 'success')
      load()
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    } finally {
      setBusy(null)
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault()
    try {
      await api.createUser(form.name.trim(), form.email.trim(), form.role, form.password)
      showToast('Пользователь создан', 'success')
      setForm({ name: '', email: '', password: '', role: 'editor' })
      setCreating(false)
      load()
    } catch (e: unknown) {
      showToast((e as Error).message, 'error')
    }
  }

  if (user && user.role !== 'admin') return null

  return (
    <div className="content">
      <div className="card">
        <div className="card-header">
          <div>
            <span className="card-title">Пользователи</span>
            {users && (
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 4 }}>
                Всего {users.length}, администраторов {admins.length}
              </div>
            )}
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => setCreating(v => !v)}>
            {creating ? 'Отмена' : (
              <>
                <svg {...S}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                Добавить
              </>
            )}
          </button>
        </div>

        {creating && (
          <form onSubmit={create} style={{
            padding: 16, borderBottom: '1px solid var(--border)',
            background: 'var(--surface-2)', display: 'grid', gap: 12,
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', alignItems: 'end',
          }}>
            <div className="fg" style={{ margin: 0 }}>
              <label>Имя и фамилия</label>
              <input value={form.name} required placeholder="Алексей Иванов"
                onChange={e => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="fg" style={{ margin: 0 }}>
              <label>Email</label>
              <input type="email" value={form.email} required placeholder="user@example.com"
                onChange={e => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="fg" style={{ margin: 0 }}>
              <label>Пароль</label>
              <input type="password" value={form.password} required placeholder="Минимум 8 символов"
                onChange={e => setForm({ ...form, password: e.target.value })} />
            </div>
            <div className="fg" style={{ margin: 0 }}>
              <label>Роль</label>
              <select value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
                {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
            <button type="submit" className="btn btn-primary" style={{ height: 38, justifyContent: 'center' }}>
              Создать
            </button>
          </form>
        )}

        <StateWrapper loading={users === null && !error} error={error} onRetry={load}
          empty={users?.length === 0} emptyText="Пользователей нет">
          <div style={{ overflowX: 'auto' }}>
            <table className="tbl" style={{ width: '100%', minWidth: 640 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>Пользователь</th>
                  <th style={{ textAlign: 'left' }}>Роль</th>
                  <th style={{ textAlign: 'left' }}>Регистрация</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(users ?? []).map(u => {
                  const self = u.id === user?.id
                  const lastAdmin = u.role === 'admin' && admins.length <= 1
                  return (
                    <tr key={u.id} style={{ opacity: busy === u.id ? 0.5 : 1 }}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{
                            width: 32, height: 32, borderRadius: 'var(--r-full)', flexShrink: 0,
                            background: 'var(--accent-light)', color: 'var(--accent)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: 11.5, fontWeight: 800,
                          }}>
                            {u.avatar || u.name.slice(0, 2).toUpperCase()}
                          </div>
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontWeight: 600, fontSize: 13 }}>
                              {u.name}{self && <span style={{ color: 'var(--text-3)', fontWeight: 500 }}> — это вы</span>}
                            </div>
                            <div style={{ fontSize: 11.5, color: 'var(--text-3)' }}>{u.email}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <select
                          value={u.role}
                          disabled={busy === u.id || self}
                          onChange={e => changeRole(u, e.target.value)}
                          style={{ fontSize: 12, padding: '5px 8px', minWidth: 150 }}
                        >
                          {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                        </select>
                        <div className={`user-role-lbl ${ROLE_CLASS[u.role] ?? ''}`}
                          style={{ fontSize: 10, marginTop: 4, display: 'inline-block' }}>
                          {ROLE_LABEL[u.role] ?? u.role}
                        </div>
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>
                        {u.created_at ? u.created_at.replace('T', ' ') : '—'}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <button className="btn btn-ghost btn-sm"
                          disabled={busy === u.id || self || lastAdmin}
                          title={self ? 'Нельзя удалить самого себя'
                            : lastAdmin ? 'Нельзя удалить единственного администратора' : 'Удалить'}
                          onClick={() => remove(u)}
                          style={{ color: self || lastAdmin ? 'var(--text-3)' : 'var(--red)' }}>
                          <svg {...S}><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </StateWrapper>

        <div style={{
          padding: '12px 16px', borderTop: '1px solid var(--border)',
          fontSize: 11.5, color: 'var(--text-3)', lineHeight: 1.7,
        }}>
          {ROLES.map(r => (
            <div key={r.value}>
              <strong style={{ color: 'var(--text-2)' }}>{r.label}</strong> — {r.hint}
            </div>
          ))}
          <div style={{ marginTop: 6 }}>
            Роль здесь — глобальная. Права внутри конкретной группы задаются отдельно,
            в составе участников группы.
          </div>
        </div>
      </div>
    </div>
  )
}
