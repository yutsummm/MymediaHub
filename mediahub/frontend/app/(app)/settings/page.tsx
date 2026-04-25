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

const EMPTY_INVITE = { name: '', email: '', role: 'editor', password: '', confirm: '' }

export default function SettingsPage() {
  const { user: me } = useAuth()
  const { showToast } = useToast()
  const [users, setUsers] = useState<User[]>([])

  // VK integration state
  const [vk, setVk] = useState<VkSettings | null>(null)
  const [vkGroupId, setVkGroupId] = useState('')
  const [vkToken, setVkToken] = useState('')
  const [vkSaving, setVkSaving] = useState(false)
  const [vkDisconnecting, setVkDisconnecting] = useState(false)
  const [showVkForm, setShowVkForm] = useState(false)

  // Invite user state
  const [showInvite, setShowInvite] = useState(false)
  const [invite, setInvite] = useState(EMPTY_INVITE)
  const [inviteSaving, setInviteSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

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
      setVkGroupId(''); setVkToken(''); setShowVkForm(false)
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

  async function addUser() {
    if (!invite.name.trim()) { showToast('Введите имя', 'error'); return }
    if (!invite.email.trim()) { showToast('Введите email', 'error'); return }
    if (invite.password.length < 6) { showToast('Пароль — минимум 6 символов', 'error'); return }
    if (invite.password !== invite.confirm) { showToast('Пароли не совпадают', 'error'); return }
    setInviteSaving(true)
    try {
      const created = await api.createUser(invite.name.trim(), invite.email.trim(), invite.role, invite.password)
      setUsers(p => [...p, created])
      setInvite(EMPTY_INVITE)
      setShowInvite(false)
      showToast(`Участник «${created.name}» добавлен`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setInviteSaving(false) }
  }

  async function removeUser(u: User) {
    if (!confirm(`Удалить участника «${u.name}»?`)) return
    setDeletingId(u.id)
    try {
      await api.deleteUser(u.id)
      setUsers(p => p.filter(x => x.id !== u.id))
      showToast(`Участник «${u.name}» удалён`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setDeletingId(null) }
  }

  const isAdmin = me?.role === 'admin'

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
              <button className="btn btn-secondary" onClick={() => setShowVkForm(v => !v)}>
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
            <div style={{
              background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.25)',
              borderRadius: 'var(--r-md)', padding: '10px 14px', marginBottom: 14, fontSize: 12,
              color: 'var(--text-2)', lineHeight: 1.7,
            }}>
              <strong style={{ color: 'var(--text)' }}>Как получить токен с поддержкой фото:</strong><br />
              1. Зайдите на <strong>vk.com/dev</strong> → <strong>Мои приложения → Создать приложение</strong> (тип: Standalone)<br />
              2. В настройках приложения скопируйте <strong>ID приложения</strong><br />
              3. Откройте в браузере:<br />
              <span style={{
                display: 'block', fontFamily: 'monospace', fontSize: 11,
                background: 'var(--surface-2)', padding: '4px 8px', borderRadius: 4,
                marginTop: 4, wordBreak: 'break-all', userSelect: 'all',
              }}>
                https://oauth.vk.com/authorize?client_id=ВАШ_APP_ID&display=page&redirect_uri=https://oauth.vk.com/blank.html&scope=wall,photos,groups&response_type=token&v=5.199
              </span>
              4. После входа токен будет в адресной строке после <strong>access_token=</strong><br />
              <span style={{ color: 'var(--text-3)', marginTop: 4, display: 'block' }}>
                Токен группы (из «Работа с API») подходит только для публикации текста — фото с ним не загружаются.
              </span>
            </div>
            <div className="fg">
              <label>ID группы <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(числовой, без минуса)</span></label>
              <input
                type="text" inputMode="numeric" placeholder="Например: 123456789"
                value={vkGroupId} onChange={e => setVkGroupId(e.target.value.replace(/[^\d]/g, ''))}
              />
            </div>
            <div className="fg">
              <label>Токен доступа группы</label>
              <input
                type="password" placeholder="vk1.a.XXXXXXXX..."
                value={vkToken} onChange={e => setVkToken(e.target.value)} autoComplete="off"
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
          <span className="card-title">Участники команды</span>
          {isAdmin && (
            <button className="btn btn-primary" style={{ padding: '6px 14px', fontSize: 12 }} onClick={() => setShowInvite(v => !v)}>
              {showInvite ? 'Отмена' : '+ Добавить участника'}
            </button>
          )}
        </div>

        {/* Invite form */}
        {isAdmin && showInvite && (
          <div style={{
            margin: '0 0 0 0', padding: '16px 20px',
            borderBottom: '1px solid var(--border)',
            background: 'var(--surface-2)',
          }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 14 }}>
              Новый участник
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
              <div className="fg">
                <label>Имя и фамилия</label>
                <input
                  type="text" placeholder="Алексей Иванов"
                  value={invite.name} onChange={e => setInvite(p => ({ ...p, name: e.target.value }))}
                />
              </div>
              <div className="fg">
                <label>Email</label>
                <input
                  type="email" placeholder="user@email.com"
                  value={invite.email} onChange={e => setInvite(p => ({ ...p, email: e.target.value }))}
                />
              </div>
              <div className="fg">
                <label>Пароль</label>
                <input
                  type="password" placeholder="Минимум 6 символов"
                  value={invite.password} onChange={e => setInvite(p => ({ ...p, password: e.target.value }))}
                  autoComplete="new-password"
                />
              </div>
              <div className="fg">
                <label>Подтвердите пароль</label>
                <input
                  type="password" placeholder="Повторите пароль"
                  value={invite.confirm} onChange={e => setInvite(p => ({ ...p, confirm: e.target.value }))}
                  autoComplete="new-password"
                />
              </div>
            </div>
            <div className="fg" style={{ maxWidth: 260 }}>
              <label>Роль</label>
              <select value={invite.role} onChange={e => setInvite(p => ({ ...p, role: e.target.value }))}>
                {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
              <button className="btn btn-secondary" onClick={() => { setShowInvite(false); setInvite(EMPTY_INVITE) }}>
                Отмена
              </button>
              <button className="btn btn-primary" onClick={addUser} disabled={inviteSaving}>
                {inviteSaving ? 'Добавляем...' : 'Добавить участника'}
                {!inviteSaving && <span className="btn-icon">✓</span>}
              </button>
            </div>
          </div>
        )}

        <table>
          <thead>
            <tr>
              <th>Участник</th><th>Email</th><th>Роль</th>
              {isAdmin && <th>Изменить роль</th>}
              {isAdmin && <th></th>}
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
                      {u.avatar || u.name[0].toUpperCase()}
                    </div>
                    <div>
                      <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>{u.name}</span>
                      {u.id === me?.id && (
                        <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 6 }}>(вы)</span>
                      )}
                    </div>
                  </div>
                </td>
                <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{u.email}</td>
                <td><span className={`user-role-lbl ${RC[u.role]}`}>{ROLES.find(r => r.v === u.role)?.l ?? u.role}</span></td>
                {isAdmin && (
                  <td>
                    <select value={u.role} onChange={e => changeRole(u.id, e.target.value)}
                      style={{ width: 'auto', padding: '6px 10px', fontSize: 12 }}>
                      {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                  </td>
                )}
                {isAdmin && (
                  <td>
                    {u.id !== me?.id && (
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 10px', fontSize: 11, color: 'var(--error, #ef4444)' }}
                        onClick={() => removeUser(u)}
                        disabled={deletingId === u.id}
                      >
                        {deletingId === u.id ? '...' : 'Удалить'}
                      </button>
                    )}
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
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 'var(--r-lg)', padding: 14,
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
