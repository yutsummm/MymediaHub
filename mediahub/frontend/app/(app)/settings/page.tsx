'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { useToast } from '@/contexts/ToastContext'
import type { VkSettings, TgSettings, GroupMember, InviteLink } from '@/lib/types'

const ROLES = [
  { v: 'admin',    l: 'Администратор', d: 'Полный доступ ко всем функциям' },
  { v: 'editor',   l: 'Редактор',      d: 'Создание и редактирование постов' },
  { v: 'observer', l: 'Наблюдатель',   d: 'Только просмотр аналитики' },
]
const RC: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', observer: 'r-observer' }

export default function SettingsPage() {
  const router = useRouter()
  const { user: me } = useAuth()
  const { currentGroup, refreshGroups } = useGroup()
  const { showToast } = useToast()

  const [members, setMembers] = useState<GroupMember[]>([])
  const [inviteLinks, setInviteLinks] = useState<InviteLink[]>([])

  // VK integration state
  const [vk, setVk] = useState<VkSettings | null>(null)
  const [vkGroupId, setVkGroupId] = useState('')
  const [vkToken, setVkToken] = useState('')
  const [vkSaving, setVkSaving] = useState(false)
  const [vkDisconnecting, setVkDisconnecting] = useState(false)
  const [showVkForm, setShowVkForm] = useState(false)

  // Telegram integration state
  const [tg, setTg] = useState<TgSettings | null>(null)
  const [tgBotToken, setTgBotToken] = useState('')
  const [tgChatId, setTgChatId] = useState('')
  const [tgSaving, setTgSaving] = useState(false)
  const [tgDisconnecting, setTgDisconnecting] = useState(false)
  const [showTgForm, setShowTgForm] = useState(false)

  // Invite link creation state
  const [showCreateInvite, setShowCreateInvite] = useState(false)
  const [inviteRole, setInviteRole] = useState('editor')
  const [inviteHours, setInviteHours] = useState('24')
  const [creatingInvite, setCreatingInvite] = useState(false)
  const [revokingId, setRevokingId] = useState<number | null>(null)

  // Member management state
  const [deletingId, setDeletingId] = useState<number | null>(null)

  // Delete group state
  const [deletingGroup, setDeletingGroup] = useState(false)

  useEffect(() => {
    if (!currentGroup) return
    const gid = currentGroup.id
    setVk(null); setTg(null)
    api.getGroupVkSettings(gid).then(s => {
      setVk(s)
      if (s.connected) setShowVkForm(false)
    }).catch(console.error)
    api.getGroupTgSettings(gid).then(s => {
      setTg(s)
      if (s.connected) setShowTgForm(false)
    }).catch(console.error)
    api.getGroupMembers(gid).then(setMembers).catch(console.error)
    if (currentGroup.role === 'admin') {
      api.getInviteLinks(gid).then(setInviteLinks).catch(console.error)
    }
  }, [currentGroup?.id])

  async function connectTg() {
    if (!currentGroup) return
    if (!tgBotToken.trim()) { showToast('Введите токен бота', 'error'); return }
    if (!tgChatId.trim()) { showToast('Введите ID канала или @username', 'error'); return }
    setTgSaving(true)
    try {
      const result = await api.saveGroupTgSettings(currentGroup.id, tgBotToken.trim(), tgChatId.trim())
      setTg(result)
      setTgBotToken(''); setTgChatId(''); setShowTgForm(false)
      showToast(`Канал «${result.chat_title}» подключён`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setTgSaving(false) }
  }

  async function disconnectTg() {
    if (!currentGroup) return
    setTgDisconnecting(true)
    try {
      await api.deleteGroupTgSettings(currentGroup.id)
      setTg({ connected: false })
      showToast('Telegram-канал отключён', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setTgDisconnecting(false) }
  }

  async function connectVk() {
    if (!currentGroup) return
    if (!vkGroupId.trim()) { showToast('Введите ID группы', 'error'); return }
    if (!vkToken.trim()) { showToast('Введите токен доступа', 'error'); return }
    setVkSaving(true)
    try {
      const result = await api.saveGroupVkSettings(currentGroup.id, vkGroupId.trim(), vkToken.trim())
      setVk(result)
      setVkGroupId(''); setVkToken(''); setShowVkForm(false)
      showToast(`Группа «${result.group_name}» подключена`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setVkSaving(false) }
  }

  async function disconnectVk() {
    if (!currentGroup) return
    setVkDisconnecting(true)
    try {
      await api.deleteGroupVkSettings(currentGroup.id)
      setVk({ connected: false })
      showToast('VK-группа отключена', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setVkDisconnecting(false) }
  }

  async function changeRole(uid: number, role: string) {
    if (!currentGroup) return
    try {
      const updated = await api.updateMemberRole(currentGroup.id, uid, role)
      setMembers(p => p.map(m => m.id === uid ? { ...m, role: updated.role } : m))
      showToast('Роль обновлена', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
  }

  async function removeMember(m: GroupMember) {
    if (!currentGroup) return
    if (!confirm(`Удалить участника «${m.name}» из группы?`)) return
    setDeletingId(m.id)
    try {
      await api.removeGroupMember(currentGroup.id, m.id)
      setMembers(p => p.filter(x => x.id !== m.id))
      showToast(`Участник «${m.name}» удалён из группы`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setDeletingId(null) }
  }

  async function createInvite() {
    if (!currentGroup) return
    setCreatingInvite(true)
    try {
      const link = await api.createInviteLink(currentGroup.id, inviteRole, parseInt(inviteHours))
      setInviteLinks(p => [link, ...p])
      setShowCreateInvite(false)
      showToast('Ссылка создана', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setCreatingInvite(false) }
  }

  async function revokeInvite(id: number) {
    if (!currentGroup) return
    setRevokingId(id)
    try {
      await api.revokeInviteLink(currentGroup.id, id)
      setInviteLinks(p => p.filter(l => l.id !== id))
      showToast('Ссылка отозвана', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setRevokingId(null) }
  }

  function copyInviteLink(token: string) {
    const url = `${window.location.origin}/invite/${token}`
    navigator.clipboard.writeText(url).then(() => showToast('Ссылка скопирована', 'success'))
  }

  async function deleteGroup() {
    if (!currentGroup) return
    if (!confirm(`Удалить группу «${currentGroup.name}»? Все посты и настройки будут удалены безвозвратно.`)) return
    setDeletingGroup(true)
    try {
      await api.deleteGroup(currentGroup.id)
      await refreshGroups()
      router.push('/dashboard')
      showToast('Группа удалена', 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setDeletingGroup(false) }
  }

  const isAdmin = currentGroup?.role === 'admin'

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
              borderRadius: 'var(--r-md)', padding: '12px 16px', marginBottom: 16, fontSize: 12,
              color: 'var(--text-2)', lineHeight: 1.8,
            }}>
              <strong style={{ color: 'var(--text)', fontSize: 13 }}>Получение пользовательского токена (для постов с фото):</strong><br />
              <br />
              <strong>1.</strong> Нажмите кнопку <strong>«Получить токен ВК»</strong> ниже — откроется страница авторизации<br />
              <strong>2.</strong> Авторизуйтесь и нажмите <strong>«Разрешить»</strong><br />
              <strong>3.</strong> После этого браузер откроет белую страницу с длинным URL в адресной строке<br />
              <strong>4.</strong> В URL найдите <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>access_token=</code> и скопируйте всё значение <strong>до символа &amp;</strong><br />
              <strong>5.</strong> Введите ID группы и вставьте токен ниже<br />
              <br />
              <span style={{ color: 'var(--text-3)' }}>Вы должны быть <strong>администратором или редактором</strong> группы. Токен бессрочный, хранится только у вас на сервере.</span><br />
              <br />
              <strong>ID группы</strong>: число из URL <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>vk.com/club<strong>123456</strong></code>
            </div>
            <a
              href="https://oauth.vk.com/authorize?client_id=2685278&scope=wall,photos,groups,manage,offline&redirect_uri=https://oauth.vk.com/blank.html&display=page&response_type=token&revoke=1&v=5.199"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-secondary"
              style={{ display: 'inline-flex', marginBottom: 14, textDecoration: 'none' }}
            >
              Получить токен ВК ↗
            </a>
            <div className="fg">
              <label>ID группы <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(только цифры)</span></label>
              <input type="text" inputMode="numeric" placeholder="238076799"
                value={vkGroupId} onChange={e => setVkGroupId(e.target.value.replace(/[^\d]/g, ''))} />
            </div>
            <div className="fg">
              <label>Токен доступа <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(значение access_token= из URL)</span></label>
              <input type="password" placeholder="vk1.a.XXXXXXXX..."
                value={vkToken} onChange={e => setVkToken(e.target.value.trim())} autoComplete="off" />
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

      {/* Telegram Integration */}
      <div className="card card-p" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div className="card-title" style={{ marginBottom: 4 }}>Подключение Telegram</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
              При публикации поста с платформой «Telegram» он автоматически выкладывается в канал
            </div>
          </div>
          {tg?.connected && (
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

        {tg?.connected ? (
          <div>
            <div style={{
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 'var(--r-lg)', padding: '12px 16px', marginBottom: 14,
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="32" height="32" rx="8" fill="#229ED9"/>
                <path d="M22.95 9.51l-2.4 11.34c-.18.8-.66 1-1.34.62l-3.7-2.73-1.78 1.72c-.2.2-.36.36-.74.36l.26-3.76 6.84-6.18c.3-.26-.06-.4-.46-.14l-8.46 5.32-3.64-1.14c-.79-.25-.81-.79.16-1.17l14.24-5.49c.66-.24 1.24.16 1.02 1.15z" fill="white"/>
              </svg>
              <div>
                <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--text)' }}>{tg.chat_title}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  ID: {tg.chat_id} · Подключено: {tg.connected_at?.slice(0, 10)}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => setShowTgForm(v => !v)}>
                {showTgForm ? 'Скрыть' : 'Изменить'}
              </button>
              <button
                className="btn btn-secondary"
                style={{ color: 'var(--error, #ef4444)' }}
                onClick={disconnectTg}
                disabled={tgDisconnecting}
              >
                {tgDisconnecting ? 'Отключаем...' : 'Отключить'}
              </button>
            </div>
          </div>
        ) : (
          <button className="btn btn-primary" onClick={() => setShowTgForm(true)} style={{ marginBottom: showTgForm ? 16 : 0 }}>
            Подключить канал Telegram
            <span className="btn-icon">↗</span>
          </button>
        )}

        {showTgForm && (
          <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            <div style={{
              background: 'rgba(34,158,217,0.08)', border: '1px solid rgba(34,158,217,0.25)',
              borderRadius: 'var(--r-md)', padding: '12px 16px', marginBottom: 16, fontSize: 12,
              color: 'var(--text-2)', lineHeight: 1.8,
            }}>
              <strong style={{ color: 'var(--text)', fontSize: 13 }}>Как подключить Telegram-канал:</strong><br />
              <br />
              <strong>1.</strong> В Telegram найдите <strong>@BotFather</strong> → отправьте команду <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>/newbot</code><br />
              <strong>2.</strong> Задайте имя и юзернейм бота — получите <strong>токен</strong> вида <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>123456:ABC-...</code><br />
              <strong>3.</strong> Откройте свой канал → <strong>Управление каналом → Администраторы</strong> → добавьте бота с правом <strong>«Публикация сообщений»</strong><br />
              <strong>4.</strong> Введите данные ниже:<br />
              &nbsp;&nbsp;&nbsp;&nbsp;• <strong>Токен бота</strong> — из BotFather<br />
              &nbsp;&nbsp;&nbsp;&nbsp;• <strong>ID канала</strong> — для публичного: <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>@username</code>; для приватного: числовой <code style={{ background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>-100xxxxxxxxxx</code>
            </div>
            <div className="fg">
              <label>Токен бота</label>
              <input type="password" placeholder="123456:ABC-DEF..."
                value={tgBotToken} onChange={e => setTgBotToken(e.target.value.trim())} autoComplete="off" />
            </div>
            <div className="fg">
              <label>ID канала или @username</label>
              <input type="text" placeholder="@mychannel или -1001234567890"
                value={tgChatId} onChange={e => setTgChatId(e.target.value.trim())} />
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn btn-secondary" onClick={() => { setShowTgForm(false); setTgBotToken(''); setTgChatId('') }}>
                Отмена
              </button>
              <button className="btn btn-primary" onClick={connectTg} disabled={tgSaving}>
                {tgSaving ? 'Проверяем...' : 'Подключить'}
                {!tgSaving && <span className="btn-icon">✓</span>}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Invite links */}
      {isAdmin && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">
            <span className="card-title">Ссылки-приглашения</span>
            <button
              className="btn btn-primary"
              style={{ padding: '6px 14px', fontSize: 12 }}
              onClick={() => setShowCreateInvite(v => !v)}
            >
              {showCreateInvite ? 'Отмена' : '+ Создать ссылку'}
            </button>
          </div>

          {showCreateInvite && (
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div className="fg" style={{ margin: 0, minWidth: 160 }}>
                  <label>Роль</label>
                  <select value={inviteRole} onChange={e => setInviteRole(e.target.value)}>
                    {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                  </select>
                </div>
                <div className="fg" style={{ margin: 0, minWidth: 160 }}>
                  <label>Срок действия</label>
                  <select value={inviteHours} onChange={e => setInviteHours(e.target.value)}>
                    <option value="6">6 часов</option>
                    <option value="24">24 часа</option>
                    <option value="72">3 дня</option>
                    <option value="168">7 дней</option>
                    <option value="720">30 дней</option>
                  </select>
                </div>
                <button className="btn btn-primary" onClick={createInvite} disabled={creatingInvite}>
                  {creatingInvite ? 'Создаём...' : 'Создать'}
                  {!creatingInvite && <span className="btn-icon">✓</span>}
                </button>
              </div>
            </div>
          )}

          {inviteLinks.length === 0 ? (
            <div style={{ padding: '20px', color: 'var(--text-3)', fontSize: 13, textAlign: 'center' }}>
              Нет активных ссылок
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Роль</th>
                  <th>Использована</th>
                  <th>Истекает</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {inviteLinks.map(link => (
                  <tr key={link.id}>
                    <td><span className={`user-role-lbl ${RC[link.role]}`}>{ROLES.find(r => r.v === link.role)?.l ?? link.role}</span></td>
                    <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
                      {link.used_count}{link.max_uses ? ` / ${link.max_uses}` : ''} раз
                    </td>
                    <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
                      {new Date(link.expires_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '4px 10px', fontSize: 11 }}
                          onClick={() => copyInviteLink(link.token)}
                        >
                          Копировать
                        </button>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '4px 10px', fontSize: 11, color: 'var(--error, #ef4444)' }}
                          onClick={() => revokeInvite(link.id)}
                          disabled={revokingId === link.id}
                        >
                          {revokingId === link.id ? '...' : 'Отозвать'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Members */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <span className="card-title">Участники команды</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Участник</th><th>Email</th><th>Роль</th>
              {isAdmin && <th>Изменить роль</th>}
              {isAdmin && <th></th>}
            </tr>
          </thead>
          <tbody>
            {members.map(m => (
              <tr key={m.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 30, height: 30, borderRadius: '50%',
                      background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
                      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontWeight: 700, fontSize: 12, flexShrink: 0,
                    }}>
                      {m.avatar || m.name[0].toUpperCase()}
                    </div>
                    <div>
                      <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>{m.name}</span>
                      {m.id === me?.id && (
                        <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 6 }}>(вы)</span>
                      )}
                    </div>
                  </div>
                </td>
                <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{m.email}</td>
                <td><span className={`user-role-lbl ${RC[m.role]}`}>{ROLES.find(r => r.v === m.role)?.l ?? m.role}</span></td>
                {isAdmin && (
                  <td>
                    <select value={m.role} onChange={e => changeRole(m.id, e.target.value)}
                      style={{ width: 'auto', padding: '6px 10px', fontSize: 12 }}>
                      {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                  </td>
                )}
                {isAdmin && (
                  <td>
                    {m.id !== me?.id && (
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '4px 10px', fontSize: 11, color: 'var(--error, #ef4444)' }}
                        onClick={() => removeMember(m)}
                        disabled={deletingId === m.id}
                      >
                        {deletingId === m.id ? '...' : 'Удалить'}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card card-p" style={{ marginBottom: 16 }}>
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

      {/* Danger zone */}
      {isAdmin && (
        <div className="card card-p" style={{
          border: '1px solid rgba(239,68,68,0.3)',
          background: 'rgba(239,68,68,0.04)',
        }}>
          <div className="card-title" style={{ marginBottom: 6, color: '#ef4444' }}>Опасная зона</div>
          <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 16 }}>
            Удаление группы необратимо — все посты, настройки и участники будут удалены.
          </p>
          <button
            className="btn btn-secondary"
            style={{ color: '#ef4444', borderColor: 'rgba(239,68,68,0.4)' }}
            onClick={deleteGroup}
            disabled={deletingGroup}
          >
            {deletingGroup ? 'Удаляем...' : `Удалить группу «${currentGroup?.name}»`}
          </button>
        </div>
      )}
    </div>
  )
}
