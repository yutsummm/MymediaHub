'use client'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Link from 'next/link'
import { helpTopic, type HelpTopicId } from '@/lib/help'

/** Ширина окошка. На узком экране — по экрану, с полями по краям. */
const WIDTH = 300
const MARGIN = 8

/**
 * Подсказка «?» рядом с непонятным местом интерфейса.
 *
 * Текст берётся из общего словаря справки, а не пишется здесь: тот же абзац
 * показывается на странице «Что умеет система», и написанный дважды он
 * разошёлся бы после первой правки.
 *
 * **Вешаем только туда, где сейчас не объяснено ничего.** Там, где рядом уже
 * стоит абзац — в редакторе поста, в настройках публикации, — подсказка не
 * нужна: спрятать читаемый текст под значок значит сделать хуже, а повторить
 * его рядом — засорить экран.
 *
 * **Мышь открывает наведением, палец — нажатием.** Наведение удобнее: не надо
 * ни целиться, ни закрывать за собой. Но только им ограничиться нельзя — с
 * телефона навести физически невозможно, и подсказка, доступная лишь с мыши,
 * для этих людей просто не существует. Различаем не по ширине экрана (она про
 * размер окна, а не про то, чем человек тычет), а по `(hover: hover)` и
 * `(pointer: fine)`. Нажатие работает всегда — им же пользуется клавиатура.
 *
 * **Окошко рисуется в конце страницы, а не на месте значка.** Карточки с
 * цифрами обрезают всё, что выходит за их границы, и подсказка внутри такой
 * карточки читалась наполовину. Место на экране считается по значку, поэтому
 * выглядит она по-прежнему привязанной к нему.
 */
export default function HelpTip({ topic }: { topic: HelpTopicId }) {
  const [open, setOpen] = useState(false)
  const [box, setBox] = useState<{ top: number; left: number } | null>(null)
  // Открыто наведением — закрывается само, когда курсор ушёл. Открыто
  // нажатием — держится, пока не закроют: иначе с клавиатуры до ссылок внутри
  // не добраться, а на планшете подсказка гасла бы от случайного касания.
  const byHover = useRef(false)
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const btn = useRef<HTMLButtonElement>(null)
  const pop = useRef<HTMLSpanElement>(null)
  const id = useId()
  const entry = helpTopic(topic)

  /** Есть ли чем наводить. Тач-экран сюда не попадает. */
  const canHover = () =>
    typeof window !== 'undefined' &&
    window.matchMedia('(hover: hover) and (pointer: fine)').matches

  const cancelClose = useCallback(() => {
    if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null }
  }, [])

  const openByHover = useCallback(() => {
    if (!canHover()) return
    cancelClose()
    byHover.current = true
    setOpen(true)
  }, [cancelClose])

  // Курсор идёт к окошку через восьмипиксельный зазор и по дороге покидает
  // значок. Без задержки подсказка захлопывалась бы ровно в этот момент, и
  // до ссылок внутри было бы не дотянуться.
  const closeByHover = useCallback(() => {
    if (!byHover.current) return
    cancelClose()
    closeTimer.current = setTimeout(() => setOpen(false), 180)
  }, [cancelClose])

  const place = useCallback(() => {
    const b = btn.current?.getBoundingClientRect()
    if (!b) return
    const width = Math.min(WIDTH, window.innerWidth - MARGIN * 2)
    // Прижимаем к значку, но не даём уехать за край экрана — с какой стороны
    // экрана стоит значок, заранее неизвестно: колонки зависят от ширины окна.
    const left = Math.min(Math.max(MARGIN, b.left - 6), window.innerWidth - width - MARGIN)
    setBox({ top: b.bottom + 8, left })
  }, [])

  useEffect(() => cancelClose, [cancelClose])

  useEffect(() => {
    if (!open) return
    place()
    function onDown(e: MouseEvent) {
      const t = e.target as Node
      if (!btn.current?.contains(t) && !pop.current?.contains(t)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    // Страница под окошком продолжает прокручиваться — пересчитываем, иначе
    // подсказка отрывается от своего значка.
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [open, place])

  if (!entry) return null

  return (
    <span className="help-tip">
      <button
        ref={btn}
        type="button"
        className={`help-tip-btn${open ? ' on' : ''}`}
        aria-expanded={open}
        aria-controls={id}
        aria-label={`Что это: ${entry.title}`}
        onMouseEnter={openByHover}
        onMouseLeave={closeByHover}
        onClick={e => {
          e.preventDefault(); e.stopPropagation()
          cancelClose()
          // Нажатие по открытой наведением подсказке закрепляет её, а не
          // гасит: на мыши курсор уже открыл окошко, и толкование нажатия как
          // «переключить» означало бы, что попытка закрепить закрывает.
          // Читать здесь `open` нельзя: между наведением и нажатием проходит
          // мгновение, обработчик остаётся от прежнего рендера и видит «закрыто».
          // Отсюда решение принимается по флагу, а состояние меняется функцией.
          const wasHover = byHover.current
          byHover.current = false
          setOpen(v => (wasHover ? true : !v))
        }}
      >
        ?
      </button>
      {open && box && typeof document !== 'undefined' && createPortal(
        <span
          ref={pop}
          className="help-tip-pop"
          id={id}
          role="note"
          style={{ top: box.top, left: box.left }}
          onMouseEnter={cancelClose}
          onMouseLeave={closeByHover}
        >
          <span className="help-tip-ttl">{entry.title}</span>
          <span className="help-tip-txt">{entry.text}</span>
          <span className="help-tip-foot">
            {entry.href && (
              <Link href={entry.href} className="help-tip-link" onClick={() => setOpen(false)}>
                Перейти
              </Link>
            )}
            <Link href={`/help#${topic}`} className="help-tip-link" onClick={() => setOpen(false)}>
              Вся справка
            </Link>
          </span>
        </span>,
        document.body,
      )}
    </span>
  )
}
