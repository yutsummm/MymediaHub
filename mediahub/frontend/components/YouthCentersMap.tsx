'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FullscreenControl, Map, Placemark, YMaps, ZoomControl } from '@pbe/react-yandex-maps'
import type ymaps from 'yandex-maps'
import { api } from '@/lib/api'
import type { YouthCenter } from '@/lib/types'
import { useYandexMapsKey } from '@/lib/useYandexMapsKey'
import {
  getCenterCoordinates,
  KRASNOYARSK_CENTER,
  KRASNOYARSK_YOUTH_CENTERS,
  normalizeYouthCenters,
  sortYouthCentersByDistance,
  type Coordinates,
} from '@/lib/youthCenters'

type Position = {
  coordinates: Coordinates
  source: 'user' | 'fallback'
}

declare global {
  interface Window {
    ymaps?: typeof ymaps
  }
}

const FALLBACK_POSITION: Position = { coordinates: KRASNOYARSK_CENTER, source: 'fallback' }

function getGlobalYMaps() {
  return typeof window !== 'undefined' ? window.ymaps ?? null : null
}

function sortByDistance(centers: YouthCenter[], position: Position) {
  return sortYouthCentersByDistance(centers, position.coordinates)
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
        setCenters(Array.isArray(data) ? normalizeYouthCenters(data) : sortByDistance(KRASNOYARSK_YOUTH_CENTERS, position))
      })
      .catch(error => {
        if (cancelled) return
        setCenters(sortByDistance(KRASNOYARSK_YOUTH_CENTERS, position))
        setDataError((error as Error).message || 'Не удалось загрузить центры. Показываем mock-данные.')
      })
      .finally(() => {
        if (!cancelled) setCentersLoading(false)
      })

    return () => { cancelled = true }
  }, [position])

  const visibleCenters = useMemo(
    () => position ? sortByDistance(centers, position) : normalizeYouthCenters(centers),
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
