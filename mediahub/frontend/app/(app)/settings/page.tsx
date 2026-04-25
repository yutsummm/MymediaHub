'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import type { User, VkSettings } from '@/lib/types'

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

  // VK integration state
  const [vk, setVk] = useState<VkSettings | null>(null)
  const [vkGroupId, setVkGroupId] = useState('')
  const [vkToken, setVkToken] = useState('')
  const [vkSaving, setVkSaving] = useState(false)
  const [vkDisconnecting, setVkDisconnecting] = useState(false)
  const [showVkForm, setShowVkForm] = useState(false)

  useEffect(() => {
    api.getUsers().then(setUsers).catch(console.error)
    api.getVkSettings().then(s => {
      setVk(s)
      if (s.connected) setShowVkForm(false)
    }).catch(console.error)
  }, [])

  async function changeRole(id: number, role: string) {
    try {
      const updated = await api.updateUserRole(id, role)
      setUsers(p => p.map(u => u.id === id ? { ...u, role: updated.role } : u))
      showToast('Роль обновлена', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  async function connectVk() {
    if (!vkGroupId.trim()) { showToast('Введите ID группы', 'error'); return }
    if (!vkToken.trim()) { showToast('Введите токен доступа', 'error'); return }
    setVkSaving(true)
    try {
      const result = await api.saveVkSettings(vkGroupId.trim(), vkToken.trim())
      setVk(result)
      setVkGroupId('')
      setVkToken('')
      setShowVkForm(false)
      showToast(`Группа «${result.group_name}» подключена`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setVkSaving(false) }
  }

  async function disconnectVk() {
    setVkDisconnecting(true)
    try {
      await api.deleteVkSettings()
      setVk({ connected: false })
      showToast('VK-группа отключена', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setVkDisconnecting(false) }
  }

  return (
    <div className="content">
      {/* VK Integration */}
      <div className="card card-p" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div className="card-title" style={{ marginBottom: 4 }}>Подключение ВКонтакте</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
              При публикации поста с платформой «ВКонтакте» он автоматически выкладывается в группу
            </div>
          </div>
          {vk?.connected && (
            <span style={{
              fontSize: 11, fontWeight: 700, padding: '3px 10px',
              borderRadius: 20, background: 'rgba(34,197,94,0.15)',
              color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)',
              letterSpacing: '0.05em',
            }}>
              Подключено
            </span>
          )}
        </div>

        {vk?.connected ? (
          <div>
            <div style={{
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 'var(--r-lg)', padding: '12px 16px', marginBottom: 14,
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              {/* VK logo */}
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="32" height="32" rx="8" fill="#0077FF"/>
                <path d="M17.07 22c-6.18 0-9.7-4.24-9.84-11.3H10.3c.1 5.18 2.38 7.37 4.18 7.82V10.7h2.8v4.27c1.78-.19 3.65-2.23 4.28-4.27h2.76c-.48 2.5-2.48 4.54-3.9 5.38 1.42.68 3.69 2.49 4.58 5.92h-3.04c-.7-2.18-2.43-3.87-4.68-4.09V22h-.21z" fill="white"/>
              </svg>
              <div>
                <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text)' }}>{vk.group_name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  ID группы: {vk.group_id} · Подключено: {vk.connected_at?.slice(0, 10)}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setShowVkForm(v => !v)}
              >
                {showVkForm ? 'Скрыть' : 'Изменить токен'}
              </button>
              <button
                className="btn btn-secondary"
                style={{ color: 'var(--error, #ef4444)' }}
                onClick={disconnectVk}
                disabled={vkDisconnecting}
              >
                {vkDisconnecting ? 'Отключаем...' : 'Отключить'}
              </button>
            </div>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={() => setShowVkForm(true)} style={{ marginBottom: showVkForm ? 16 : 0 }}>
            Подключить группу VK
            <span className="btn-icon">↗</span>
          </button>
        )}

        {showVkForm && (
          <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 14, lineHeight: 1.6 }}>
              Чтобы получить токен группы: откройте управление группой → <strong>Настройки → Работа с API → Создать ключ</strong> и выберите разрешение <strong>wall</strong>.
            </div>
            <div className="fg">
              <label>ID группы <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(числовой, без минуса)</span></label>
              <input
                type="text"
                inputMode="numeric"
                placeholder="Например: 123456789"
                value={vkGroupId}
                onChange={e => setVkGroupId(e.target.value.replace(/[^\d]/g, ''))}
              />
            </div>
            <div className="fg">
              <label>Токен доступа группы</label>
              <input
                type="password"
                placeholder="vk1.a.XXXXXXXX..."
                value={vkToken}
                onChange={e => setVkToken(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => { setShowVkForm(false); setVkGroupId(''); setVkToken('') }}>
                Отмена
              </button>
              <button className="btn btn-primary" onClick={connectVk} disabled={vkSaving}>
                {vkSaving ? 'Проверяем...' : 'Подключить'}
                {!vkSaving && <span className="btn-icon">✓</span>}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Users management */}
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
