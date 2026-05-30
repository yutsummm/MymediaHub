'use client'

import dynamic from 'next/dynamic'

const YouthCentersMap = dynamic(() => import('@/components/YouthCentersMap'), {
  ssr: false,
  loading: () => (
    <div className="youth-map-skeleton">
      Загружаем карту...
    </div>
  ),
})

export default function YouthCentersPage() {
  return (
    <div className="content">
      <div className="youth-centers-hero">
        <div>
          <div className="ts tg" style={{ textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700, marginBottom: 8 }}>
            Карта рядом с пользователем
          </div>
          <h1 className="youth-centers-title">Молодежные центры рядом</h1>
          <p className="youth-centers-subtitle">
            Карта определяет вашу геолокацию, центрируется по текущей точке и показывает молодежные центры с адресами.
          </p>
        </div>
      </div>
      <YouthCentersMap />
    </div>
  )
}
