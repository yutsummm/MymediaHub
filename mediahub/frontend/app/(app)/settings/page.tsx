'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useGroup } from '@/contexts/GroupContext'
import { useToast } from '@/contexts/ToastContext'
import type { VkSettings, TgSettings, GroupMember, InviteLink } from '@/lib/types'

const S14 = { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
const S12 = { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }

const IcoCheck    = <svg {...S14}><polyline points="20 6 9 17 4 12"/></svg>
const IcoExternal = <svg {...S14}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
const IcoCopy     = <svg {...S12}><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>

const ROLES = [
  { v: 'admin',    l: 'Администратор', d: 'Полный доступ ко всем функциям' },
  { v: 'editor',   l: 'Редактор',      d: 'Создание и редактирование постов' },
  { v: 'observer', l: 'Наблюдатель',   d: 'Только просмотр аналитики' },
]
const RC: Record<string, string> = { admin: 'r-admin', editor: 'r-editor', observer: 'r-observer' }

function SectionHead({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>{title}</div>
      {subtitle && <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 3, lineHeight: 1.5 }}>{subtitle}</div>}
    </div>
  )
}

function ConnectedBadge() {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 9px',
      borderRadius: 'var(--r-full)', background: 'var(--green-bg)',
      color: 'var(--green)', border: '1px solid rgba(16,185,129,0.25)',
      letterSpacing: '0.04em', flexShrink: 0,
    }}>
      Подключено
    </span>
  )
}

export default function SettingsPage() {
  const router = useRouter()
  const { user: me } = useAuth()
  const { currentGroup, refreshGroups } = useGroup()
  const { showToast } = useToast()

  const [members, setMembers]         = useState<GroupMember[]>([])
  const [inviteLinks, setInviteLinks] = useState<InviteLink[]>([])

  const [vk, setVk]                 = useState<VkSettings | null>(null)
  const [vkGroupId, setVkGroupId]   = useState('')
  const [vkToken, setVkToken]       = useState('')
  const [vkSaving, setVkSaving]     = useState(false)
  const [vkDis, setVkDis]           = useState(false)
  const [showVkForm, setShowVkForm] = useState(false)

  const [tg, setTg]                 = useState<TgSettings | null>(null)
  const [tgBotToken, setTgBotToken] = useState('')
  const [tgChatId, setTgChatId]     = useState('')
  const [tgSaving, setTgSaving]     = useState(false)
  const [tgDis, setTgDis]           = useState(false)
  const [showTgForm, setShowTgForm] = useState(false)

  const [showCreateInvite, setShowCreateInvite] = useState(false)
  const [inviteRole, setInviteRole]   = useState('editor')
  const [inviteHours, setInviteHours] = useState('24')
  const [creatingInvite, setCreatingInvite] = useState(false)
  const [revokingId, setRevokingId]   = useState<number | null>(null)
  const [deletingId, setDeletingId]   = useState<number | null>(null)
  const [deletingGroup, setDeletingGroup] = useState(false)

  useEffect(() => {
    if (!currentGroup) return
    const gid = currentGroup.id
    setVk(null); setTg(null)
    api.getGroupVkSettings(gid).then(s => { setVk(s); if (s.connected) setShowVkForm(false) }).catch(console.error)
    api.getGroupTgSettings(gid).then(s => { setTg(s); if (s.connected) setShowTgForm(false) }).catch(console.error)
    api.getGroupMembers(gid).then(setMembers).catch(console.error)
    if (currentGroup.role === 'admin') {
      api.getInviteLinks(gid).then(setInviteLinks).catch(console.error)
    }
  }, [currentGroup?.id])

  async function connectTg() {
    if (!currentGroup) return
    if (!tgBotToken.trim()) { showToast('Введите токен бота', 'error'); return }
    if (!tgChatId.trim())   { showToast('Введите ID канала', 'error'); return }
    setTgSaving(true)
    try {
      const r = await api.saveGroupTgSettings(currentGroup.id, tgBotToken.trim(), tgChatId.trim())
      setTg(r); setTgBotToken(''); setTgChatId(''); setShowTgForm(false)
      showToast(`Канал «${r.chat_title}» подключён`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setTgSaving(false) }
  }

  async function disconnectTg() {
    if (!currentGroup) return
    setTgDis(true)
    try { await api.deleteGroupTgSettings(currentGroup.id); setTg({ connected: false }); showToast('Telegram-канал отключён', 'success') }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setTgDis(false) }
  }

  async function connectVk() {
    if (!currentGroup) return
    if (!vkGroupId.trim()) { showToast('Введите ID группы', 'error'); return }
    if (!vkToken.trim())   { showToast('Введите токен', 'error'); return }
    setVkSaving(true)
    try {
      const r = await api.saveGroupVkSettings(currentGroup.id, vkGroupId.trim(), vkToken.trim())
      setVk(r); setVkGroupId(''); setVkToken(''); setShowVkForm(false)
      showToast(`Группа «${r.group_name}» подключена`, 'success')
    } catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setVkSaving(false) }
  }

  async function disconnectVk() {
    if (!currentGroup) return
    setVkDis(true)
    try { await api.deleteGroupVkSettings(currentGroup.id); setVk({ connected: false }); showToast('VK-группа отключена', 'success') }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setVkDis(false) }
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
      showToast(`«${m.name}» удалён из группы`, 'success')
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
    if (!confirm(`Удалить группу «${currentGroup.name}»? Все данные будут удалены безвозвратно.`)) return
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

  const IntegCard = ({
    platform, color, icon, title, subtitle, children,
  }: {
    platform: 'vk' | 'tg'; color: string; icon: React.ReactNode;
    title: string; subtitle: string; children: React.ReactNode;
  }) => {
    const connected = platform === 'vk' ? vk?.connected : tg?.connected
    return (
      <div className="card card-p anim-in" style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10, background: color,
              display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              {icon}
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>{title}</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 2 }}>{subtitle}</div>
            </div>
          </div>
          {connected && <ConnectedBadge />}
        </div>
        {children}
      </div>
    )
  }

  const infoBox = (bg: string, children: React.ReactNode) => (
    <div style={{
      background: bg, border: `1px solid ${bg.replace('0.08', '0.2')}`,
      borderRadius: 'var(--r-md)', padding: '12px 16px',
      marginBottom: 16, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.8,
    }}>
      {children}
    </div>
  )

  return (
    <div className="content">

      {/* VK */}
      <IntegCard
        platform="vk" color="#0077FF"
        icon={
          <svg width="20" height="20" viewBox="0 0 32 32" fill="none"><path d="M17.07 22c-6.18 0-9.7-4.24-9.84-11.3H10.3c.1 5.18 2.38 7.37 4.18 7.82V10.7h2.8v4.27c1.78-.19 3.65-2.23 4.28-4.27h2.76c-.48 2.5-2.48 4.54-3.9 5.38 1.42.68 3.69 2.49 4.58 5.92h-3.04c-.7-2.18-2.43-3.87-4.68-4.09V22h-.21z" fill="white"/></svg>
        }
        title="ВКонтакте"
        subtitle="Автоматическая публикация постов в группу"
      >
        {vk?.connected ? (
          <div>
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: '10px 14px', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>{vk.group_name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>ID: {vk.group_id} · {vk.connected_at?.slice(0, 10)}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowVkForm(v => !v)}>{showVkForm ? 'Скрыть' : 'Изменить токен'}</button>
              <button className="btn btn-secondary btn-sm" style={{ color: 'var(--red)' }} onClick={disconnectVk} disabled={vkDis}>{vkDis ? 'Отключаем...' : 'Отключить'}</button>
            </div>
          </div>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => setShowVkForm(true)}>Подключить группу VK <span className="btn-icon">{IcoExternal}</span></button>
        )}

        {showVkForm && (
          <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            {infoBox('rgba(59,130,246,0.08)', <>
              <strong style={{ color: 'var(--text)', fontSize: 12.5 }}>Как получить токен:</strong><br />
              <strong>1.</strong> Нажмите <strong>«Получить токен ВК»</strong> — откроется авторизация<br />
              <strong>2.</strong> Разрешите доступ → в URL найдите <code style={{ background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 3 }}>access_token=</code><br />
              <strong>3.</strong> Скопируйте значение <strong>до символа &amp;</strong><br />
              <strong>4.</strong> ID группы: число из URL <code style={{ background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 3 }}>vk.com/club<strong>123456</strong></code>
            </>)}
            <a href="https://oauth.vk.com/authorize?client_id=2685278&scope=wall,photos,groups,manage,offline&redirect_uri=https://oauth.vk.com/blank.html&display=page&response_type=token&revoke=1&v=5.199"
              target="_blank" rel="noopener noreferrer" className="btn btn-secondary btn-sm" style={{ display: 'inline-flex', marginBottom: 14, textDecoration: 'none' }}>
              Получить токен ВК {IcoExternal}
            </a>
            <div className="fg">
              <label>ID группы <span style={{ color: 'var(--text-3)', fontWeight: 400 }}>(только цифры)</span></label>
              <input type="text" inputMode="numeric" placeholder="238076799" value={vkGroupId} onChange={e => setVkGroupId(e.target.value.replace(/[^\d]/g, ''))} />
            </div>
            <div className="fg">
              <label>Токен доступа</label>
              <input type="password" placeholder="vk1.a.XXXXXXXX..." value={vkToken} onChange={e => setVkToken(e.target.value.trim())} autoComplete="off" />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => { setShowVkForm(false); setVkGroupId(''); setVkToken('') }}>Отмена</button>
              <button className="btn btn-primary btn-sm" onClick={connectVk} disabled={vkSaving}>{vkSaving ? 'Проверяем...' : <>{IcoCheck} Подключить</>}</button>
            </div>
          </div>
        )}
      </IntegCard>

      {/* Telegram */}
      <IntegCard
        platform="tg" color="#229ED9"
        icon={
          <svg width="20" height="20" viewBox="0 0 32 32" fill="none"><path d="M22.95 9.51l-2.4 11.34c-.18.8-.66 1-1.34.62l-3.7-2.73-1.78 1.72c-.2.2-.36.36-.74.36l.26-3.76 6.84-6.18c.3-.26-.06-.4-.46-.14l-8.46 5.32-3.64-1.14c-.79-.25-.81-.79.16-1.17l14.24-5.49c.66-.24 1.24.16 1.02 1.15z" fill="white"/></svg>
        }
        title="Telegram"
        subtitle="Автоматическая публикация постов в канал"
      >
        {tg?.connected ? (
          <div>
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: '10px 14px', marginBottom: 12 }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>{tg.chat_title}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>ID: {tg.chat_id} · {tg.connected_at?.slice(0, 10)}</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => setShowTgForm(v => !v)}>{showTgForm ? 'Скрыть' : 'Изменить'}</button>
              <button className="btn btn-secondary btn-sm" style={{ color: 'var(--red)' }} onClick={disconnectTg} disabled={tgDis}>{tgDis ? 'Отключаем...' : 'Отключить'}</button>
            </div>
          </div>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => setShowTgForm(true)}>Подключить Telegram <span className="btn-icon">{IcoExternal}</span></button>
        )}

        {showTgForm && (
          <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            {infoBox('rgba(34,158,217,0.08)', <>
              <strong style={{ color: 'var(--text)', fontSize: 12.5 }}>Как подключить канал:</strong><br />
              <strong>1.</strong> В Telegram: <strong>@BotFather</strong> → <code style={{ background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 3 }}>/newbot</code> → получите токен<br />
              <strong>2.</strong> В канале: Управление → Администраторы → добавьте бота с правом публикации<br />
              <strong>3.</strong> Публичный канал: <code style={{ background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 3 }}>@username</code>; приватный: <code style={{ background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 3 }}>-100xxxxxxxxxx</code>
            </>)}
            <div className="fg">
              <label>Токен бота</label>
              <input type="password" placeholder="123456:ABC-DEF..." value={tgBotToken} onChange={e => setTgBotToken(e.target.value.trim())} autoComplete="off" />
            </div>
            <div className="fg">
              <label>ID канала или @username</label>
              <input type="text" placeholder="@mychannel или -1001234567890" value={tgChatId} onChange={e => setTgChatId(e.target.value.trim())} />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => { setShowTgForm(false); setTgBotToken(''); setTgChatId('') }}>Отмена</button>
              <button className="btn btn-primary btn-sm" onClick={connectTg} disabled={tgSaving}>{tgSaving ? 'Проверяем...' : <>{IcoCheck} Подключить</>}</button>
            </div>
          </div>
        )}
      </IntegCard>

      {/* Invite links */}
      {isAdmin && (
        <div className="card anim-in" style={{ marginBottom: 12 }}>
          <div className="card-header">
            <span className="card-title">Ссылки-приглашения</span>
            <button className="btn btn-primary btn-sm" onClick={() => setShowCreateInvite(v => !v)}>
              {showCreateInvite ? 'Отмена' : '+ Создать'}
            </button>
          </div>

          {showCreateInvite && (
            <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--border)', background: 'var(--surface-2)' }}>
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
                <button className="btn btn-primary btn-sm" onClick={createInvite} disabled={creatingInvite}>
                  {creatingInvite ? 'Создаём...' : <>{IcoCheck} Создать</>}
                </button>
              </div>
            </div>
          )}

          {inviteLinks.length === 0 ? (
            <div style={{ padding: '24px', color: 'var(--text-3)', fontSize: 13, textAlign: 'center' }}>
              Нет активных ссылок
            </div>
          ) : (
            <table>
              <thead>
                <tr><th>Роль</th><th>Использована</th><th>Истекает</th><th></th></tr>
              </thead>
              <tbody>
                {inviteLinks.map(link => (
                  <tr key={link.id}>
                    <td><span className={`user-role-lbl ${RC[link.role]}`}>{ROLES.find(r => r.v === link.role)?.l ?? link.role}</span></td>
                    <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{link.used_count}{link.max_uses ? ` / ${link.max_uses}` : ''} раз</td>
                    <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
                      {new Date(link.expires_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button className="btn btn-secondary btn-sm" style={{ padding: '4px 10px', fontSize: 11, gap: 4 }} onClick={() => copyInviteLink(link.token)}>
                          {IcoCopy} Копировать
                        </button>
                        <button className="btn btn-secondary btn-sm" style={{ padding: '4px 10px', fontSize: 11, color: 'var(--red)' }} onClick={() => revokeInvite(link.id)} disabled={revokingId === link.id}>
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
      <div className="card anim-in" style={{ marginBottom: 12 }}>
        <div className="card-header">
          <span className="card-title">Участники команды</span>
          <span style={{ fontSize: 11, color: 'var(--text-3)', fontWeight: 600 }}>{members.length} чел.</span>
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
                      color: 'var(--btn-primary-fg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontWeight: 700, fontSize: 12, flexShrink: 0,
                    }}>
                      {m.avatar || m.name[0].toUpperCase()}
                    </div>
                    <div>
                      <span style={{ fontWeight: 600, color: 'var(--text)', fontSize: 13 }}>{m.name}</span>
                      {m.id === me?.id && <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 6 }}>(вы)</span>}
                    </div>
                  </div>
                </td>
                <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{m.email}</td>
                <td><span className={`user-role-lbl ${RC[m.role]}`}>{ROLES.find(r => r.v === m.role)?.l ?? m.role}</span></td>
                {isAdmin && (
                  <td>
                    <select value={m.role} onChange={e => changeRole(m.id, e.target.value)} style={{ width: 'auto', padding: '5px 10px', fontSize: 12 }}>
                      {ROLES.map(r => <option key={r.v} value={r.v}>{r.l}</option>)}
                    </select>
                  </td>
                )}
                {isAdmin && (
                  <td>
                    {m.id !== me?.id && (
                      <button className="btn btn-secondary btn-sm" style={{ padding: '4px 10px', fontSize: 11, color: 'var(--red)' }} onClick={() => removeMember(m)} disabled={deletingId === m.id}>
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

      {/* Roles info */}
      <div className="card card-p anim-in" style={{ marginBottom: 12 }}>
        <SectionHead title="О ролях" />
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
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
        <div className="card card-p anim-in" style={{ border: '1px solid rgba(239,68,68,0.2)', background: 'rgba(239,68,68,0.03)' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--red)', letterSpacing: '-0.02em', marginBottom: 4 }}>
                Опасная зона
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }}>
                Удаление группы необратимо — все посты, настройки и участники будут удалены.
              </div>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              style={{ color: 'var(--red)', borderColor: 'rgba(239,68,68,0.3)', flexShrink: 0 }}
              onClick={deleteGroup}
              disabled={deletingGroup}
            >
              {deletingGroup ? 'Удаляем...' : `Удалить группу «${currentGroup?.name}»`}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
