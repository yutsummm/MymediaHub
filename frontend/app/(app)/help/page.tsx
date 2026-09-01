'use client'
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { HELP_PAGE, SUPPORT_TELEGRAM } from '@/lib/help'
import { useGroup } from '@/contexts/GroupContext'

/**
 * «Что умеет система» — список возможностей со смыслом каждой.
 *
 * Это не частые вопросы: их у нас нет, а придуманный за людей список
 * отвечает не на то, о чём спрашивают. И не пошаговая инструкция: описания
 * кликов устаревают после первой правки вёрстки, а неверная инструкция хуже
 * отсутствующей — ей верят.
 *
 * Страница решает другую задачу — обнаружения. У системы больше тридцати
 * возможностей, и о половине неоткуда узнать: человек не ищет то, о
 * существовании чего не подозревает.
 *
 * Весь текст живёт в lib/help.ts. Здесь только вёрстка.
 */
export default function HelpPage() {
  const { currentGroup } = useGroup()
  const [q, setQ] = useState('')

  // Переход из подсказки ведёт на #тему. Браузер не всегда доскроллит сам:
  // якорь появляется вместе с отрисовкой, а не до неё.
  useEffect(() => {
    const hash = decodeURIComponent(window.location.hash.slice(1))
    if (!hash) return
    const t = setTimeout(() => {
      document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 60)
    return () => clearTimeout(t)
  }, [])

  const needle = q.trim().toLowerCase()
  const sections = useMemo(() => {
    if (!needle) return HELP_PAGE.map(s => ({ ...s, topics: [...s.topics] }))
    return HELP_PAGE
      .map(s => ({
        ...s,
        topics: s.topics.filter(t =>
          `${t.title} ${t.text} ${t.where ?? ''}`.toLowerCase().includes(needle)),
      }))
      .filter(s => s.topics.length > 0)
  }, [needle])

  const found = sections.reduce((n, s) => n + s.topics.length, 0)

  // Ссылка на поддержку несёт, откуда человек пришёл: иначе первым сообщением
  // всегда идёт «а где вы это видели».
  const supportHref = useMemo(() => {
    if (!SUPPORT_TELEGRAM) return null
    const about = currentGroup ? `Группа «${currentGroup.name}». ` : ''
    return `${SUPPORT_TELEGRAM}?text=${encodeURIComponent(`${about}Вопрос по медиаПространству: `)}`
  }, [currentGroup])

  return (
    <div className="content">
      <div className="card anim-in help-intro">
        <div style={{ padding: '20px 24px' }}>
          <h2 className="help-h1">Что умеет система</h2>
          <p className="help-lead">
            Не пошаговая инструкция, а список возможностей со смыслом каждой: что происходит,
            почему сделано именно так и где это лежит. Разделы можно читать вразнобой.
          </p>
          <input
            type="search"
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Поиск по справке: очередь, метки, обращения..."
            className="srch help-search"
            aria-label="Поиск по справке"
          />
          {needle && (
            <div className="help-found">
              {found === 0
                ? `Ничего не нашлось.${supportHref ? ' Спросите нас — внизу страницы есть связь.' : ''}`
                : `Нашлось: ${found}`}
            </div>
          )}
        </div>
      </div>

      {!needle && (
        <nav className="help-jump" aria-label="Разделы справки">
          {HELP_PAGE.map(s => (
            <a key={s.id} href={`#${s.id}`} className="help-jump-item">{s.title}</a>
          ))}
        </nav>
      )}

      {sections.map(section => (
        <section key={section.id} id={section.id} className="card anim-in help-section">
          <div className="card-header">
            <span className="card-title">{section.title}</span>
          </div>
          <div style={{ padding: '14px 24px 22px' }}>
            <p className="help-section-intro">{section.intro}</p>
            <div className="help-list">
              {section.topics.map(topic => (
                <article key={topic.id} id={topic.id} className="help-item">
                  <h3 className="help-item-ttl">{topic.title}</h3>
                  <p className="help-item-txt">{topic.text}</p>
                  {(topic.where || topic.href) && (
                    <div className="help-item-foot">
                      {topic.where && <span className="help-where">{topic.where}</span>}
                      {topic.href && (
                        <Link href={topic.href} className="help-item-link">Открыть →</Link>
                      )}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </div>
        </section>
      ))}

      {/* Блока связи нет, пока не задан адрес: кнопка в никуда хуже её
          отсутствия — нажавший решит, что писать некуда. */}
      {supportHref && (
        <section className="card anim-in help-support">
          <div style={{ padding: '20px 24px' }}>
            <h3 className="help-item-ttl" style={{ fontSize: 15 }}>Не нашли ответ — напишите нам</h3>
            <p className="help-item-txt" style={{ marginBottom: 14 }}>
              Справка отвечает на предвиденные вопросы, а непредвиденных всегда больше.
              Если что-то не получается или ведёт себя странно — напишите, разберёмся.
              И заодно поймём, чего здесь не хватает.
            </p>
            <a
              href={supportHref}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-primary btn-sm"
            >
              Написать в Telegram
            </a>
          </div>
        </section>
      )}
    </div>
  )
}
