'use client'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useToast } from '@/contexts/ToastContext'
import type { Group, HashtagSet, PublishingSlot } from '@/lib/types'

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

/** Ходовые времена публикации — чтобы не набирать «12:00» руками каждый раз. */
const HOURS = ['09:00', '10:00', '12:00', '15:00', '18:00', '19:00']

type Props = {
  group: Group
  onSaved: () => Promise<void> | void
}

/**
 * Три настройки группы, которые касаются содержания постов: расписание
 * публикаций, UTM-метки и подстановки с хештегами.
 *
 * Вынесены в отдельный компонент, потому что страница настроек и без них
 * длинная, а эти три вещи читаются как одна тема — «как мы публикуем».
 */
export default function GroupContentSettings({ group, onSaved }: Props) {
  const { showToast } = useToast()

  const [slots, setSlots] = useState<PublishingSlot[] | null>(null)
  const [slotsSaving, setSlotsSaving] = useState(false)
  const [newSlotDay, setNewSlotDay] = useState(0)
  const [newSlotAt, setNewSlotAt] = useState('12:00')

  const [utmSaving, setUtmSaving] = useState(false)

  const [vars, setVars] = useState<[string, string][]>([])
  const [sets, setSets] = useState<HashtagSet[]>([])
  const [libSaving, setLibSaving] = useState(false)

  useEffect(() => {
    api.getSlots(group.id).then(d => setSlots(d.slots)).catch(() => setSlots([]))
    setVars(Object.entries(group.variables ?? {}))
    setSets(group.hashtag_sets ?? [])
    // Только по смене группы. Добавить сюда сами variables значило бы
    // перезатирать несохранённые правки при каждом обновлении списка групп —
    // человек набирает адрес, а поле под ним схлопывается к прежнему значению.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group.id])

  async function saveSlots(next: PublishingSlot[]) {
    setSlotsSaving(true)
    try {
      const saved = await api.saveSlots(group.id, next)
      setSlots(saved.slots)
    }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setSlotsSaving(false) }
  }

  function addSlot() {
    const exists = (slots ?? []).some(s => s.weekday === newSlotDay && s.at === newSlotAt)
    if (exists) { showToast('Такое окно уже есть', 'info'); return }
    saveSlots([...(slots ?? []), { weekday: newSlotDay, at: newSlotAt }])
  }

  async function toggleUtm(value: boolean) {
    setUtmSaving(true)
    try {
      await api.updateGroup(group.id, { utm_enabled: value })
      await onSaved()
      showToast(value ? 'Метки включены' : 'Метки выключены', 'success')
    }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setUtmSaving(false) }
  }

  async function saveLibrary() {
    setLibSaving(true)
    try {
      const variables: Record<string, string> = {}
      for (const [k, v] of vars) {
        const key = k.trim()
        if (key) variables[key] = v
      }
      await api.updateGroup(group.id, {
        variables,
        hashtag_sets: sets.filter(s => s.name.trim() && s.tags.trim()),
      })
      await onSaved()
      showToast('Сохранено', 'success')
    }
    catch (e: unknown) { showToast((e as Error).message, 'error') }
    finally { setLibSaving(false) }
  }

  return (
    <>
      {/* ─── Расписание ─── */}
      <div className="card anim-in" style={{ marginBottom: 12 }}>
        <div className="card-header">
          <span className="card-title">Расписание публикаций</span>
        </div>
        <div style={{ padding: '16px 20px' }}>
          <div className="ts tg" style={{ marginBottom: 14, maxWidth: '68ch' }}>
            Когда группа обычно публикует. Пост можно поставить в очередь одной кнопкой —
            он займёт ближайшее свободное окно, и дату не придётся выбирать вручную.
          </div>

          {slots === null ? (
            <div style={{ color: 'var(--text-3)', fontSize: 13 }}>Загрузка...</div>
          ) : slots.length === 0 ? (
            <div style={{ color: 'var(--text-3)', fontSize: 13, marginBottom: 14 }}>
              Окон пока нет. Пока расписание пустое, очередь недоступна — дату придётся
              выбирать вручную.
            </div>
          ) : (
            <div className="slot-grid">
              {slots.map(s => (
                <span key={`${s.weekday}-${s.at}`} className="slot-chip">
                  <b>{WEEKDAYS[s.weekday]}</b> {s.at}
                  <button
                    type="button"
                    aria-label="Убрать окно"
                    onClick={() => saveSlots(slots.filter(
                      x => !(x.weekday === s.weekday && x.at === s.at)))}
                    disabled={slotsSaving}
                  >×</button>
                </span>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 14 }}>
            <select value={newSlotDay} onChange={e => setNewSlotDay(Number(e.target.value))}
              style={{ width: 'auto', minWidth: 120 }}>
              {WEEKDAYS.map((d, i) => <option key={i} value={i}>{d}</option>)}
            </select>
            <input type="time" value={newSlotAt} onChange={e => setNewSlotAt(e.target.value)}
              style={{ width: 'auto' }} />
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {HOURS.map(h => (
                <button key={h} type="button" className="tag" style={{ cursor: 'pointer' }}
                  onClick={() => setNewSlotAt(h)}>{h}</button>
              ))}
            </div>
            <button className="btn btn-secondary btn-sm" onClick={addSlot} disabled={slotsSaving}>
              + Добавить окно
            </button>
          </div>
        </div>
      </div>

      {/* ─── UTM ─── */}
      <div className="card anim-in" style={{ marginBottom: 12 }}>
        <div className="card-header">
          <span className="card-title">Метки для статистики сайта</span>
        </div>
        <div style={{ padding: '16px 20px' }}>
          <label className="opt-toggle">
            <input type="checkbox" checked={!!group.utm_enabled} disabled={utmSaving}
              onChange={e => toggleUtm(e.target.checked)} />
            <span>
              <span className="opt-toggle-ttl">Размечать ссылки UTM-метками</span>
              <span className="opt-toggle-sub">
                К ссылкам в тексте добавляется, из какой соцсети и по какой рубрике пришёл
                человек. Без этого переходы видны в статистике сайта как «прямые заходы»,
                и узнать, сколько людей привели соцсети, задним числом уже нельзя.
                Метки добавляются при публикации — текст поста остаётся таким, каким вы его
                написали. Свою разметку, если она уже есть в ссылке, не трогаем.
              </span>
            </span>
          </label>
        </div>
      </div>

      {/* ─── Переменные и хештеги ─── */}
      <div className="card anim-in" style={{ marginBottom: 12 }}>
        <div className="card-header">
          <span className="card-title">Подстановки и хештеги</span>
          <button className="btn btn-primary btn-sm" onClick={saveLibrary} disabled={libSaving}>
            {libSaving ? 'Сохраняем...' : 'Сохранить'}
          </button>
        </div>
        <div style={{ padding: '16px 20px' }}>
          <div className="ts tg" style={{ marginBottom: 12, maxWidth: '68ch' }}>
            Подстановка — это то, что повторяется в каждом втором посте: название центра,
            адрес, телефон. В тексте пишется <code>{'{{адрес}}'}</code>, а при публикации
            подставляется значение. Неизвестный ключ остаётся в тексте как есть — так его
            видно, а не теряется молча.
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {vars.map(([key, value], i) => (
              <div key={i} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input placeholder="ключ" value={key} style={{ flex: '0 0 160px' }}
                  onChange={e => setVars(p => p.map((row, j) => j === i ? [e.target.value, row[1]] : row))} />
                <input placeholder="значение" value={value} style={{ flex: 1, minWidth: 200 }}
                  onChange={e => setVars(p => p.map((row, j) => j === i ? [row[0], e.target.value] : row))} />
                <button className="btn btn-ghost btn-sm"
                  onClick={() => setVars(p => p.filter((_, j) => j !== i))}>Убрать</button>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" style={{ marginTop: 10 }}
            onClick={() => setVars(p => [...p, ['', '']])}>+ Подстановка</button>

          <div style={{ height: 1, background: 'var(--border)', margin: '18px 0' }} />

          <div className="ts tg" style={{ marginBottom: 12, maxWidth: '68ch' }}>
            Наборы хештегов по рубрикам — чтобы не набирать одно и то же заново.
            В редакторе они добавляются в конец текста одним нажатием.
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {sets.map((set, i) => (
              <div key={i} style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <input placeholder="название набора" value={set.name} style={{ flex: '0 0 160px' }}
                  onChange={e => setSets(p => p.map((row, j) => j === i ? { ...row, name: e.target.value } : row))} />
                <input placeholder="#молодёжь #красноярск" value={set.tags} style={{ flex: 1, minWidth: 200 }}
                  onChange={e => setSets(p => p.map((row, j) => j === i ? { ...row, tags: e.target.value } : row))} />
                <button className="btn btn-ghost btn-sm"
                  onClick={() => setSets(p => p.filter((_, j) => j !== i))}>Убрать</button>
              </div>
            ))}
          </div>
          <button className="btn btn-secondary btn-sm" style={{ marginTop: 10 }}
            onClick={() => setSets(p => [...p, { name: '', tags: '' }])}>+ Набор хештегов</button>
        </div>
      </div>
    </>
  )
}
