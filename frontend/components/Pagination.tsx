'use client'

/**
 * Навигация по страницам списка.
 *
 * Бэкенд всегда отдавал только первую сотню записей, а интерфейс ничего не
 * листал — на 101-м посте список молча обрывался, и понять это со стороны было
 * невозможно. Поэтому здесь всегда видно, сколько всего записей и какие из них
 * сейчас показаны, даже когда страница одна.
 */

const S = {
  width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
  strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const,
}

export default function Pagination({
  total, limit, offset, onChange, unit = 'записей',
}: {
  total: number
  limit: number
  offset: number
  onChange: (offset: number) => void
  unit?: string
}) {
  if (!total) return null

  const page = Math.floor(offset / limit) + 1
  const pages = Math.max(1, Math.ceil(total / limit))
  const from = offset + 1
  const to = Math.min(offset + limit, total)

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 12, padding: '12px 16px', borderTop: '1px solid var(--border)',
      flexWrap: 'wrap',
    }}>
      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
        {total <= limit
          ? `Всего ${total} ${unit}`
          : <>Показаны <strong style={{ color: 'var(--text-2)' }}>{from}–{to}</strong> из {total} {unit}</>}
      </div>

      {pages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <button
            className="btn btn-secondary btn-sm"
            disabled={offset <= 0}
            onClick={() => onChange(Math.max(0, offset - limit))}
          >
            <svg {...S}><polyline points="15 18 9 12 15 6" /></svg>
            Назад
          </button>
          <span style={{ fontSize: 12, color: 'var(--text-3)', minWidth: 74, textAlign: 'center' }}>
            Стр. {page} из {pages}
          </span>
          <button
            className="btn btn-secondary btn-sm"
            disabled={to >= total}
            onClick={() => onChange(offset + limit)}
          >
            Вперёд
            <svg {...S}><polyline points="9 18 15 12 9 6" /></svg>
          </button>
        </div>
      )}
    </div>
  )
}
