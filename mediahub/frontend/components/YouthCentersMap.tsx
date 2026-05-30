'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FullscreenControl, Map, Placemark, YMaps, ZoomControl } from '@pbe/react-yandex-maps'
import type ymaps from 'yandex-maps'
import { api } from '@/lib/api'
import type { YouthCenter } from '@/lib/types'
import { useYandexMapsKey } from '@/lib/useYandexMapsKey'

type Coordinates = [number, number] // [lat, lon] for Yandex Maps

type Position = {
  coordinates: Coordinates
  source: 'user' | 'fallback'
}

declare global {
  interface Window {
    ymaps?: typeof ymaps
  }
}

const FALLBACK_POSITION: Position = { coordinates: [56.010563, 92.852572], source: 'fallback' }

const LOCAL_MOCK_CENTERS: YouthCenter[] = [
  {
    id: 1,
    name: 'Молодёжный творческий бизнес-центр «Пилот»',
    address: 'ул. Аэровокзальная, 10',
    coordinates: [56.030036, 92.906351],
    lat: 56.030036,
    lon: 92.906351,
  },
  {
    id: 2,
    name: 'Молодёжный центр «Новые имена»',
    address: 'ул. Академика Вавилова, 25А',
    coordinates: [55.996302, 92.927833],
    lat: 55.996302,
    lon: 92.927833,
  },
  {
    id: 3,
    name: 'Красноярский волонтёрский центр «Доброе дело»',
    address: 'ул. Ады Лебедевой, 149',
    coordinates: [56.014568, 92.842547],
    lat: 56.014568,
    lon: 92.842547,
  },
  {
    id: 4,
    name: 'Красноярский волонтёрский центр «Доброе дело» — филиал',
    address: 'ул. Красномосковская, 42',
    coordinates: [56.023163, 92.820856],
    lat: 56.023163,
    lon: 92.820856,
  },
  {
    id: 5,
    name: 'Молодёжный военно-спортивный центр «Патриот»',
    address: 'пр. им. газеты Красноярский Рабочий, 62',
    coordinates: [56.012343, 92.970454],
    lat: 56.012343,
    lon: 92.970454,
  },
  {
    id: 6,
    name: 'Молодёжный ИТ-центр',
    address: 'пр. им. газеты Красноярский Рабочий, 115А',
    coordinates: [55.998586, 92.919816],
    lat: 55.998586,
    lon: 92.919816,
  },
  {
    id: 7,
    name: 'Молодёжный центр «База»',
    address: 'ул. Глинки, 23',
    coordinates: [56.021373, 93.048990],
    lat: 56.021373,
    lon: 93.048990,
  },
  {
    id: 8,
    name: 'Молодёжный центр «Своё дело»',
    address: 'ул. Попова, 12',
    coordinates: [56.041454, 92.760624],
    lat: 56.041454,
    lon: 92.760624,
  },
  {
    id: 9,
    name: 'Центр продвижения молодёжных проектов «Вектор»',
    address: 'пр. Металлургов, 22А',
    coordinates: [56.052516, 92.952216],
    lat: 56.052516,
    lon: 92.952216,
  },
  {
    id: 10,
    name: 'Центр технического проектирования «ПроТехно»',
    address: 'ул. Алёши Тимошенкова, 87А',
    coordinates: [55.970091, 92.941041],
    lat: 55.970091,
    lon: 92.941041,
  },
  {
    id: 11,
    name: 'Центр путешественников',
    address: 'ул. Карла Маркса, 49',
    coordinates: [56.010637, 92.880036],
    lat: 56.010637,
    lon: 92.880036,
  },
  {
    id: 12,
    name: 'Трудовой отряд Главы города Красноярска',
    address: 'ул. Мичурина, 17',
    coordinates: [56.006241, 92.962945],
    lat: 56.006241,
    lon: 92.962945,
  },
  {
    id: 13,
    name: 'Центр авторского самоопределения молодёжи «Зеркало»',
    address: 'ул. Бограда, 65',
    coordinates: [56.007156, 92.857835],
    lat: 56.007156,
    lon: 92.857835,
  },
  {
    id: 14,
    name: 'Центр молодёжных инициатив «Форум»',
    address: 'остров Отдыха, 6',
    coordinates: [55.994841, 92.872365],
    lat: 55.994841,
    lon: 92.872365,
  },
  {
    id: 15,
    name: 'ЦОПП Красноярского края',
    address: 'ул. Партизана Железняка, 13',
    coordinates: [56.031944, 92.922629],
    lat: 56.031944,
    lon: 92.922629,
  },
  {
    id: 16,
    name: 'Кванториум',
    address: 'ул. Дубровинского, 1И',
    coordinates: [56.009112, 92.888053],
    lat: 56.009112,
    lon: 92.888053,
  },
  {
    id: 17,
    name: 'IT-Куб',
    address: 'ул. Железнодорожников, 22Д',
    coordinates: [56.025183, 92.841650],
    lat: 56.025183,
    lon: 92.841650,
  },
  {
    id: 18,
    name: 'Дом науки и техники',
    address: 'ул. Урицкого, 61',
    coordinates: [56.009287, 92.875364],
    lat: 56.009287,
    lon: 92.875364,
  },
]

function getCenterCoordinates(center: YouthCenter): Coordinates {
  if (center.coordinates) return center.coordinates
  return [center.lat, center.lon]
}

function getGlobalYMaps() {
  return typeof window !== 'undefined' ? window.ymaps ?? null : null
}

function normalizeCenters(centers: YouthCenter[]) {
  return centers.map(center => {
    const coordinates = getCenterCoordinates(center)
    return {
      ...center,
      coordinates,
      lat: coordinates[0],
      lon: coordinates[1],
    }
  })
}

function toRadians(value: number) {
  return value * Math.PI / 180
}

function distanceKm(from: Coordinates, to: Coordinates) {
  const earthRadiusKm = 6371
  const dLat = toRadians(to[0] - from[0])
  const dLon = toRadians(to[1] - from[1])
  const lat1 = toRadians(from[0])
  const lat2 = toRadians(to[0])
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return Math.round(earthRadiusKm * 2 * Math.asin(Math.sqrt(a)) * 100) / 100
}

function sortByDistance(centers: YouthCenter[], position: Position) {
  return normalizeCenters(centers)
    .map(center => ({
      ...center,
      distance_km: center.distance_km ?? distanceKm(position.coordinates, getCenterCoordinates(center)),
    }))
    .sort((a, b) => (a.distance_km ?? 0) - (b.distance_km ?? 0))
}

function escapeHtml(value: string) {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;')
}

function buildCenterBalloon(center: YouthCenter) {
  const distance = typeof center.distance_km === 'number'
    ? `<div style="margin-top:8px;color:#0840b5;font-weight:700">${center.distance_km.toFixed(2)} км от вас</div>`
    : ''

  return {
    balloonContentHeader: `<strong>${escapeHtml(center.name)}</strong>`,
    balloonContentBody: `<div>${escapeHtml(center.address)}</div>${distance}`,
    hintContent: center.name,
    iconCaption: center.name,
  }
}

export default function YouthCentersMap() {
  const { key: yandexMapsKey, loading: mapsKeyLoading, error: mapsKeyError } = useYandexMapsKey()
  const mapRef = useRef<ymaps.Map | null>(null)
  const ymapsRef = useRef<typeof ymaps | null>(null)
  const watchIdRef = useRef<number | null>(null)
  const fallbackTimerRef = useRef<number | null>(null)
  const [position, setPosition] = useState<Position | null>(null)
  const [centers, setCenters] = useState<YouthCenter[]>([])
  const [selectedCenterId, setSelectedCenterId] = useState<number | null>(null)
  const [geoLoading, setGeoLoading] = useState(true)
  const [centersLoading, setCentersLoading] = useState(false)
  const [mapReady, setMapReady] = useState(false)
  const [geoError, setGeoError] = useState('')
  const [dataError, setDataError] = useState('')

  const clearGeolocation = useCallback(() => {
    if (fallbackTimerRef.current !== null) {
      window.clearTimeout(fallbackTimerRef.current)
      fallbackTimerRef.current = null
    }
    if (watchIdRef.current !== null && 'geolocation' in navigator) {
      navigator.geolocation.clearWatch(watchIdRef.current)
      watchIdRef.current = null
    }
  }, [])

  const requestLocation = useCallback((fromButton = false) => {
    clearGeolocation()
    setGeoLoading(true)
    setGeoError('')

    if (!('geolocation' in navigator)) {
      setPosition(prev => prev ?? FALLBACK_POSITION)
      setGeoLoading(false)
      setGeoError('Геолокация недоступна в этом браузере. Используем fallback-точку.')
      return
    }

    let settled = false
    fallbackTimerRef.current = window.setTimeout(() => {
      if (settled) return
      settled = true
      clearGeolocation()
      setPosition(prev => prev ?? FALLBACK_POSITION)
      setGeoLoading(false)
      setGeoError(
        fromButton
          ? 'Не удалось быстро определить местоположение. Проверьте разрешение геолокации.'
          : 'Геолокация не ответила вовремя. Используем fallback-точку.'
      )
    }, 5000)

    watchIdRef.current = navigator.geolocation.watchPosition(
      location => {
        settled = true
        clearGeolocation()
        setPosition({
          coordinates: [location.coords.latitude, location.coords.longitude],
          source: 'user',
        })
        setGeoLoading(false)
        setGeoError('')
      },
      error => {
        settled = true
        clearGeolocation()
        setPosition(prev => prev ?? FALLBACK_POSITION)
        setGeoLoading(false)
        setGeoError(error.message || 'Не удалось получить геолокацию. Используем fallback-точку.')
      },
      {
        enableHighAccuracy: false,
        maximumAge: 60_000,
        timeout: 5000,
      }
    )
  }, [clearGeolocation])

  useEffect(() => {
    requestLocation()
    return clearGeolocation
  }, [clearGeolocation, requestLocation])

  useEffect(() => {
    if (!position) return
    let cancelled = false
    setCentersLoading(true)
    setDataError('')

    api.getYouthCenters(position.coordinates[0], position.coordinates[1])
      .then(data => {
        if (cancelled) return
        setCenters(Array.isArray(data) ? normalizeCenters(data) : sortByDistance(LOCAL_MOCK_CENTERS, position))
      })
      .catch(error => {
        if (cancelled) return
        setCenters(sortByDistance(LOCAL_MOCK_CENTERS, position))
        setDataError((error as Error).message || 'Не удалось загрузить центры. Показываем mock-данные.')
      })
      .finally(() => {
        if (!cancelled) setCentersLoading(false)
      })

    return () => { cancelled = true }
  }, [position])

  const visibleCenters = useMemo(
    () => position ? sortByDistance(centers, position) : normalizeCenters(centers),
    [centers, position]
  )

  const mapState = useMemo(
    () => ({
      center: position?.coordinates ?? FALLBACK_POSITION.coordinates,
      zoom: 13,
      controls: [],
    }),
    [position]
  )

  const fitMapToNearest = useCallback(() => {
    if (!mapRef.current || !ymapsRef.current || !position) return

    const nearestCenters = visibleCenters.slice(0, 3)
    const points = [position.coordinates, ...nearestCenters.map(getCenterCoordinates)]

    if (points.length === 1) {
      void mapRef.current.setCenter(position.coordinates, 14, { duration: 350 })
      return
    }

    const bounds = ymapsRef.current.util.bounds.fromPoints(points)
    void mapRef.current
      .setBounds(bounds, {
        checkZoomRange: true,
        duration: 450,
        zoomMargin: [70, 70, 70, 70],
      })
      .then(() => {
        if (mapRef.current && mapRef.current.getZoom() > 15) {
          void mapRef.current.setZoom(15, { duration: 200 })
        }
      })
  }, [position, visibleCenters])

  useEffect(() => {
    if (!mapReady || !position || visibleCenters.length === 0) return
    fitMapToNearest()
  }, [fitMapToNearest, mapReady, position, visibleCenters.length])

  function focusCenter(center: YouthCenter) {
    const coordinates = getCenterCoordinates(center)
    setSelectedCenterId(center.id)
    void mapRef.current?.setCenter(coordinates, 15, { duration: 350 })
  }

  return (
    <div className="youth-centers-shell">
      <div className="youth-centers-main">
        <div className="youth-map-card">
          <div className="youth-map-toolbar">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => requestLocation(true)}
              disabled={geoLoading}
            >
              {geoLoading ? 'Ищем...' : 'Найти меня'}
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fitMapToNearest}
              disabled={!position || !mapReady || visibleCenters.length === 0}
            >
              Ближайшие центры
            </button>
          </div>

          {mapsKeyLoading ? (
            <div className="youth-map youth-map-empty">
              Загружаем настройки Яндекс Карт...
            </div>
          ) : !yandexMapsKey ? (
            <div className="youth-map youth-map-empty">
              {mapsKeyError || 'Не задан NEXT_PUBLIC_YANDEX_MAPS_KEY в переменных frontend-сервиса Railway'}
            </div>
          ) : (
            <YMaps query={{ apikey: yandexMapsKey, lang: 'ru_RU', load: 'package.full' }}>
              <Map
                state={mapState}
                width="100%"
                height="100%"
                className="youth-map"
                modules={['geoObject.addon.balloon', 'geoObject.addon.hint', 'util.bounds']}
                onLoad={ymapsApi => {
                  ymapsRef.current = ymapsApi
                  setMapReady(true)
                }}
                instanceRef={(mapInstance: ymaps.Map | null) => {
                  mapRef.current = mapInstance
                  if (mapInstance) {
                    ymapsRef.current = ymapsRef.current ?? getGlobalYMaps()
                    setMapReady(true)
                  } else {
                    setMapReady(false)
                  }
                }}
                options={{
                  suppressMapOpenBlock: true,
                  yandexMapDisablePoiInteractivity: true,
                }}
              >
                <ZoomControl options={{ position: { right: 12, top: 92 } }} />
                <FullscreenControl options={{ position: { right: 12, top: 52 } }} />

                {position && (
                  <Placemark
                    geometry={position.coordinates}
                    properties={{
                      balloonContentHeader: '<strong>Вы здесь</strong>',
                      balloonContentBody: position.source === 'user'
                        ? 'Местоположение определено браузером'
                        : 'Fallback-точка, так как геолокация недоступна',
                      hintContent: position.source === 'user' ? 'Вы здесь' : 'Fallback-точка',
                    }}
                    options={{
                      preset: 'islands#blueCircleDotIcon',
                      iconColor: '#0840B5',
                    }}
                  />
                )}

                {visibleCenters.map(centerItem => (
                  <Placemark
                    key={centerItem.id}
                    geometry={getCenterCoordinates(centerItem)}
                    properties={buildCenterBalloon(centerItem)}
                    options={{
                      preset: centerItem.id === selectedCenterId ? 'islands#violetStretchyIcon' : 'islands#greenStretchyIcon',
                      iconColor: centerItem.id === selectedCenterId ? '#7C3AED' : '#10B981',
                    }}
                    onClick={() => setSelectedCenterId(centerItem.id)}
                  />
                ))}
              </Map>
            </YMaps>
          )}

          {(geoLoading || centersLoading || !mapReady) && yandexMapsKey && (
            <div className="youth-map-overlay">
              <span className="youth-map-loader" />
              {geoLoading ? 'Определяем ваше местоположение...' : centersLoading ? 'Загружаем молодежные центры...' : 'Загружаем Яндекс.Карту...'}
            </div>
          )}
        </div>

        {(geoError || dataError) && (
          <div className="youth-map-alert">
            {geoError || dataError}
          </div>
        )}
      </div>

      <aside className="youth-centers-panel">
        <div className="card-title" style={{ marginBottom: 8 }}>Молодежные центры</div>
        <div className="ts tg" style={{ marginBottom: 16 }}>
          Ближайшие точки рассчитываются относительно текущего положения или fallback-координат.
        </div>
        <div className="youth-centers-list">
          {visibleCenters.map(centerItem => (
            <button
              key={centerItem.id}
              type="button"
              className={`youth-center-item${centerItem.id === selectedCenterId ? ' active' : ''}`}
              onClick={() => focusCenter(centerItem)}
            >
              <div className="youth-center-name">{centerItem.name}</div>
              <div className="youth-center-address">{centerItem.address}</div>
              {typeof centerItem.distance_km === 'number' && (
                <div className="youth-center-distance">{centerItem.distance_km.toFixed(2)} км</div>
              )}
            </button>
          ))}
        </div>
      </aside>
    </div>
  )
}
