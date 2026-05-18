'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FullscreenControl, Map, Placemark, YMaps, ZoomControl } from '@pbe/react-yandex-maps'
import type ymaps from 'yandex-maps'
import { useYandexMapsKey } from '@/lib/useYandexMapsKey'

type Coordinates = [number, number] // [lat, lon] for Yandex Maps

type Props = {
  open: boolean
  initialAddress?: string
  initialLat?: number | null
  initialLng?: number | null
  onClose: () => void
  onSelect: (payload: { address: string; lat: number | null; lng: number | null }) => void
}

type GeocodeResponse = {
  address?: string
  lat?: number
  lon?: number
  error?: string
}

declare global {
  interface Window {
    ymaps?: typeof ymaps
  }
}

const FALLBACK_CENTER: Coordinates = [55.751244, 37.618423]

function getGlobalYMaps() {
  return typeof window !== 'undefined' ? window.ymaps ?? null : null
}

async function requestGeocode(params: URLSearchParams) {
  const response = await fetch(`/config/maps/geocode?${params.toString()}`, {
    cache: 'no-store',
  })
  const data = await response.json() as GeocodeResponse

  if (!response.ok || !data.address || typeof data.lat !== 'number' || typeof data.lon !== 'number') {
    throw new Error(data.error || 'Не удалось определить адрес. Попробуйте выбрать точку рядом или ввести адрес вручную.')
  }

  return {
    address: data.address,
    coordinates: [data.lat, data.lon] as Coordinates,
  }
}

async function geocodeAddress(query: string) {
  return requestGeocode(new URLSearchParams({ q: query }))
}

async function reverseGeocode(coordinates: Coordinates) {
  const result = await requestGeocode(new URLSearchParams({
    lat: String(coordinates[0]),
    lon: String(coordinates[1]),
  }))
  return result.address
}

export default function EventLocationPickerModal({
  open,
  initialAddress = '',
  initialLat = null,
  initialLng = null,
  onClose,
  onSelect,
}: Props) {
  const { key: yandexMapsKey, loading: mapsKeyLoading, error: mapsKeyError } = useYandexMapsKey()
  const mapRef = useRef<ymaps.Map | null>(null)
  const ymapsRef = useRef<typeof ymaps | null>(null)
  const watchIdRef = useRef<number | null>(null)
  const fallbackTimerRef = useRef<number | null>(null)
  const reverseCallIdRef = useRef(0)
  const searchCallIdRef = useRef(0)
  const selectedCoordsRef = useRef<Coordinates | null>(null)

  const [address, setAddress] = useState(initialAddress)
  const [selectedCoords, setSelectedCoords] = useState<Coordinates | null>(
    initialLat != null && initialLng != null ? [initialLat, initialLng] : null
  )
  const [userCoords, setUserCoords] = useState<Coordinates | null>(null)
  const [mapCenter, setMapCenter] = useState<Coordinates>(
    initialLat != null && initialLng != null ? [initialLat, initialLng] : FALLBACK_CENTER
  )
  const [mapReady, setMapReady] = useState(false)
  const [geoLoading, setGeoLoading] = useState(false)
  const [reverseLoading, setReverseLoading] = useState(false)
  const [searching, setSearching] = useState(false)
  const [geoError, setGeoError] = useState('')
  const [searchError, setSearchError] = useState('')

  useEffect(() => {
    selectedCoordsRef.current = selectedCoords
  }, [selectedCoords])

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

  const requestLocation = useCallback((focusAfterDetect = false) => {
    clearGeolocation()
    setGeoLoading(true)
    setGeoError('')

    if (!('geolocation' in navigator)) {
      setGeoLoading(false)
      setGeoError('Геолокация недоступна в этом браузере. Выберите точку на карте вручную.')
      return
    }

    let settled = false
    fallbackTimerRef.current = window.setTimeout(() => {
      if (settled) return
      settled = true
      clearGeolocation()
      setGeoLoading(false)
      setGeoError('Не удалось быстро получить геолокацию. Можно выбрать точку на карте вручную.')
    }, 5000)

    watchIdRef.current = navigator.geolocation.watchPosition(
      position => {
        const coordinates: Coordinates = [position.coords.latitude, position.coords.longitude]
        settled = true
        clearGeolocation()
        setUserCoords(coordinates)
        setGeoLoading(false)
        setGeoError('')

        if (focusAfterDetect || !selectedCoordsRef.current) {
          setMapCenter(coordinates)
          void mapRef.current?.setCenter(coordinates, 15, { duration: 350 })
        }
      },
      error => {
        settled = true
        clearGeolocation()
        setGeoLoading(false)
        setGeoError(error.message || 'Не удалось получить геолокацию. Выберите точку на карте вручную.')
      },
      {
        enableHighAccuracy: false,
        maximumAge: 60_000,
        timeout: 5000,
      }
    )
  }, [clearGeolocation])

  useEffect(() => {
    if (!open) {
      clearGeolocation()
      return
    }

    const initialCoords = initialLat != null && initialLng != null ? [initialLat, initialLng] as Coordinates : null
    setAddress(initialAddress)
    setSelectedCoords(initialCoords)
    setUserCoords(null)
    setMapCenter(initialCoords ?? FALLBACK_CENTER)
    setGeoError('')
    setSearchError('')
    setMapReady(false)
    setReverseLoading(false)
    setSearching(false)
    requestLocation(false)

    return clearGeolocation
  }, [clearGeolocation, initialAddress, initialLat, initialLng, open, requestLocation])

  useEffect(() => {
    if (!open || !selectedCoords) return

    const callId = ++reverseCallIdRef.current
    setReverseLoading(true)
    reverseGeocode(selectedCoords)
      .then(nextAddress => {
        if (callId === reverseCallIdRef.current) setAddress(nextAddress)
      })
      .catch(() => {
        if (callId === reverseCallIdRef.current) setAddress('Место выбрано на карте')
      })
      .finally(() => {
        if (callId === reverseCallIdRef.current) setReverseLoading(false)
      })
  }, [open, selectedCoords])

  const mapState = useMemo(
    () => ({
      center: mapCenter,
      zoom: selectedCoords ? 15 : 13,
      controls: [],
    }),
    [mapCenter, selectedCoords]
  )

  function handlePick(coordinates: Coordinates) {
    setSelectedCoords(coordinates)
    setMapCenter(coordinates)
    setSearchError('')
    void mapRef.current?.setCenter(coordinates, 15, { duration: 300 })
  }

  function handleMapClick(event: ymaps.MapEvent) {
    const coords = event.get('coords') as Coordinates | undefined
    if (!coords) return
    handlePick([coords[0], coords[1]])
  }

  async function handleSearch() {
    const query = address.trim()

    if (!query) {
      setSearchError('Введите адрес или выберите точку на карте.')
      return
    }

    const callId = ++searchCallIdRef.current
    setSearching(true)
    setSearchError('')

    try {
      const result = await geocodeAddress(query)
      if (callId !== searchCallIdRef.current) return
      setAddress(result.address)
      handlePick(result.coordinates)
    } catch (error) {
      if (callId === searchCallIdRef.current) {
        setSearchError(error instanceof Error ? error.message : 'Не удалось найти адрес.')
      }
    } finally {
      if (callId === searchCallIdRef.current) setSearching(false)
    }
  }

  if (!open) return null

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal location-modal" onClick={event => event.stopPropagation()}>
        <div className="modal-hd">
          <div>
            <div className="card-title">Точка проведения события</div>
            <div className="ts tg" style={{ marginTop: 4 }}>
              Найдите адрес или кликните по Яндекс.Карте, чтобы поставить маркер события.
            </div>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Закрыть
          </button>
        </div>

        <div className="modal-bd">
          <div className="fg" style={{ marginBottom: 14 }}>
            <label>Адрес</label>
            <div className="location-search-row">
              <input
                type="text"
                value={address}
                onChange={event => setAddress(event.target.value)}
                onKeyDown={event => event.key === 'Enter' && handleSearch()}
                placeholder="Введите адрес или выберите точку на карте"
                style={{ flex: 1 }}
              />
              <button type="button" className="btn btn-primary" onClick={handleSearch} disabled={searching || !mapReady}>
                {searching ? 'Ищем...' : 'Найти'}
              </button>
              <button type="button" className="btn btn-secondary" onClick={() => requestLocation(true)} disabled={geoLoading}>
                {geoLoading ? 'Ищем...' : 'Найти меня'}
              </button>
            </div>
          </div>

          <div className="location-map-box event-location-map">
            {mapsKeyLoading ? (
              <div className="event-location-map-empty">
                Загружаем настройки Яндекс Карт...
              </div>
            ) : !yandexMapsKey ? (
              <div className="event-location-map-empty">
                {mapsKeyError || 'Не задан NEXT_PUBLIC_YANDEX_MAPS_KEY в переменных frontend-сервиса Railway'}
              </div>
            ) : (
              <YMaps query={{ apikey: yandexMapsKey, lang: 'ru_RU', load: 'package.full' }}>
                <Map
                  state={mapState}
                  width="100%"
                  height="100%"
                  className="event-location-map-inner"
                  modules={['geoObject.addon.balloon', 'geoObject.addon.hint']}
                  onClick={handleMapClick}
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
                  <ZoomControl options={{ position: { right: 12, top: 52 } }} />
                  <FullscreenControl options={{ position: { right: 12, top: 12 } }} />

                  {userCoords && (
                    <Placemark
                      geometry={userCoords}
                      properties={{
                        balloonContentHeader: '<strong>Вы здесь</strong>',
                        balloonContentBody: 'Местоположение определено браузером',
                        hintContent: 'Вы здесь',
                      }}
                      options={{
                        preset: 'islands#blueCircleDotIcon',
                        iconColor: '#0840B5',
                      }}
                    />
                  )}

                  {selectedCoords && (
                    <Placemark
                      geometry={selectedCoords}
                      properties={{
                        balloonContentHeader: '<strong>Место события</strong>',
                        balloonContentBody: address || 'Место выбрано на карте',
                        hintContent: 'Место события',
                        iconCaption: 'Событие',
                      }}
                      options={{
                        preset: 'islands#redStretchyIcon',
                        iconColor: '#EF4444',
                      }}
                    />
                  )}
                </Map>
              </YMaps>
            )}

            {yandexMapsKey && (geoLoading || reverseLoading || !mapReady) && (
              <div className="location-map-loading">
                {geoLoading ? 'Определяем ваше местоположение...' : reverseLoading ? 'Определяем адрес точки...' : 'Загружаем Яндекс.Карту...'}
              </div>
            )}
          </div>

          <div className="location-map-note">
            Клик по карте поставит маркер события. Адрес можно поправить вручную перед сохранением.
          </div>

          {(geoError || searchError) && (
            <div className="location-error-box" style={{ marginTop: 8 }}>
              {searchError || geoError}
            </div>
          )}

          {selectedCoords && (
            <div className="location-selected-box">
              <div className="location-selected-title">Выбранная точка</div>
              <div className="location-selected-text">{address || 'Место выбрано на карте'}</div>
              <div className="location-selected-meta">Адрес будет добавлен в пост как место проведения.</div>
            </div>
          )}
        </div>

        <div className="modal-ft">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!selectedCoords}
            onClick={() => {
              if (!selectedCoords) return
              onSelect({
                address: address.trim() || 'Место выбрано на карте',
                lat: selectedCoords[0],
                lng: selectedCoords[1],
              })
            }}
          >
            Выбрать точку
          </button>
        </div>
      </div>
    </div>
  )
}
