'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

type Coordinates = [number, number]

type Props = {
  open: boolean
  initialAddress?: string
  initialLat?: number | null
  initialLng?: number | null
  onClose: () => void
  onSelect: (payload: { address: string; lat: number | null; lng: number | null }) => void
}

type YMapEntity = {
  update?: (props: unknown) => void
}

type YMapInstance = {
  addChild: (entity: YMapEntity | unknown) => void
  removeChild: (entity: YMapEntity | unknown) => void
  setLocation: (location: { center: Coordinates; zoom?: number; duration?: number }) => void
  destroy: () => void
}

declare global {
  interface Window {
    ymaps3?: {
      ready: Promise<void>
      YMap: new (element: HTMLElement, props: unknown) => YMapInstance
      YMapDefaultSchemeLayer: new () => unknown
      YMapDefaultFeaturesLayer: new () => unknown
      YMapMarker: new (props: unknown, element?: HTMLElement) => YMapEntity
      YMapListener: new (props: unknown) => YMapEntity
    }
  }
}

type YandexMapsApi = NonNullable<typeof window.ymaps3>

const DEFAULT_CENTER: Coordinates = [92.852572, 56.010563]
const API_KEY = process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY ?? ''

let yandexMapsLoader: Promise<YandexMapsApi> | null = null

async function loadYandexMaps() {
  if (!API_KEY) throw new Error('Не задан NEXT_PUBLIC_YANDEX_MAPS_API_KEY для Яндекс Карт')
  if (typeof window === 'undefined') throw new Error('Яндекс Карты доступны только в браузере')
  if (window.ymaps3) {
    await window.ymaps3.ready
    return window.ymaps3
  }
  if (!yandexMapsLoader) {
    yandexMapsLoader = new Promise((resolve, reject) => {
      const existing = document.querySelector<HTMLScriptElement>('script[data-ymaps3="true"]')
      if (existing) {
        existing.addEventListener('load', async () => {
          if (!window.ymaps3) return reject(new Error('JS API Яндекс Карт не инициализировался'))
          await window.ymaps3.ready
          resolve(window.ymaps3)
        })
        existing.addEventListener('error', () => reject(new Error('Не удалось загрузить JS API Яндекс Карт')))
        return
      }

      const script = document.createElement('script')
      script.src = `https://api-maps.yandex.ru/v3/?apikey=${API_KEY}&lang=ru_RU`
      script.async = true
      script.dataset.ymaps3 = 'true'
      script.onload = async () => {
        if (!window.ymaps3) return reject(new Error('JS API Яндекс Карт не инициализировался'))
        await window.ymaps3.ready
        resolve(window.ymaps3)
      }
      script.onerror = () => reject(new Error('Не удалось загрузить JS API Яндекс Карт'))
      document.head.appendChild(script)
    })
  }
  return yandexMapsLoader
}

function parseGeocoderCoordinates(pos?: string): Coordinates | null {
  if (!pos) return null
  const [lng, lat] = pos.split(' ').map(Number)
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
  return [lng, lat]
}

async function geocodeAddress(address: string) {
  const response = await fetch(`https://geocode-maps.yandex.ru/v1/?apikey=${API_KEY}&geocode=${encodeURIComponent(address)}&lang=ru_RU&format=json&results=1`)
  if (!response.ok) throw new Error('Не удалось найти адрес через Геокодер Яндекса')
  const data = await response.json()
  const geoObject = data?.response?.GeoObjectCollection?.featureMember?.[0]?.GeoObject
  const coords = parseGeocoderCoordinates(geoObject?.Point?.pos)
  const text = geoObject?.metaDataProperty?.GeocoderMetaData?.text
  if (!coords || !text) throw new Error('Адрес не найден')
  return { coords, address: text as string }
}

async function reverseGeocode(coords: Coordinates) {
  const response = await fetch(`https://geocode-maps.yandex.ru/v1/?apikey=${API_KEY}&geocode=${coords[0]},${coords[1]}&lang=ru_RU&format=json&results=1&kind=house`)
  if (!response.ok) throw new Error('Не удалось определить адрес по точке на карте')
  const data = await response.json()
  const geoObject = data?.response?.GeoObjectCollection?.featureMember?.[0]?.GeoObject
  const text = geoObject?.metaDataProperty?.GeocoderMetaData?.text
  if (!text) throw new Error('Адрес по выбранной точке не найден')
  return text as string
}

export default function YandexLocationPickerModal({
  open,
  initialAddress = '',
  initialLat = null,
  initialLng = null,
  onClose,
  onSelect,
}: Props) {
  const mapContainerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<YMapInstance | null>(null)
  const markerRef = useRef<YMapEntity | null>(null)
  const [query, setQuery] = useState(initialAddress)
  const [selectedAddress, setSelectedAddress] = useState(initialAddress)
  const [selectedCoords, setSelectedCoords] = useState<Coordinates | null>(
    initialLat != null && initialLng != null ? [initialLng, initialLat] : null
  )
  const [loadingMap, setLoadingMap] = useState(false)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const [keyMissing, setKeyMissing] = useState(false)

  const center = useMemo<Coordinates>(() => selectedCoords ?? DEFAULT_CENTER, [selectedCoords])

  useEffect(() => {
    if (!open) return
    setQuery(initialAddress)
    setSelectedAddress(initialAddress)
    setSelectedCoords(initialLat != null && initialLng != null ? [initialLng, initialLat] : null)
    setError('')
    setKeyMissing(false)
  }, [open, initialAddress, initialLat, initialLng])

  useEffect(() => {
    if (!open) return
    if (!API_KEY) {
      setKeyMissing(true)
      return
    }

    let cancelled = false
    const initMap = async () => {
      if (!mapContainerRef.current) return
      setLoadingMap(true)
      setError('')
      try {
        const ymaps3 = await loadYandexMaps()
        if (!ymaps3) throw new Error('JS API Яндекс Карт не инициализировался')
        if (cancelled || !mapContainerRef.current) return

        const map = new ymaps3.YMap(mapContainerRef.current, {
          location: { center, zoom: selectedCoords ? 15 : 11 },
          behaviors: ['drag', 'scrollZoom', 'dblClick', 'pinchZoom'],
        })
        map.addChild(new ymaps3.YMapDefaultSchemeLayer())
        map.addChild(new ymaps3.YMapDefaultFeaturesLayer())

        const listener = new ymaps3.YMapListener({
          layer: 'any',
          onClick: async (_object: unknown, event: { coordinates?: Coordinates }) => {
            if (!event?.coordinates) return
            const coords = event.coordinates
            setSelectedCoords(coords)
            setError('')
            try {
              const address = await reverseGeocode(coords)
              if (cancelled) return
              setSelectedAddress(address)
              setQuery(address)
            } catch (err) {
              if (cancelled) return
              setError((err as Error).message)
            }
          },
        })
        map.addChild(listener)
        mapRef.current = map
      } catch (err) {
        if (!cancelled) setError((err as Error).message)
      } finally {
        if (!cancelled) setLoadingMap(false)
      }
    }

    void initMap()

    return () => {
      cancelled = true
      markerRef.current = null
      mapRef.current?.destroy()
      mapRef.current = null
    }
  }, [open, center, selectedCoords])

  useEffect(() => {
    if (!open || !mapRef.current || !window.ymaps3) return
    const map = mapRef.current
    map.setLocation({ center, zoom: selectedCoords ? 15 : 11, duration: 250 })
    if (markerRef.current) {
      map.removeChild(markerRef.current)
      markerRef.current = null
    }
    if (!selectedCoords) return

    const markerElement = document.createElement('div')
    markerElement.style.width = '22px'
    markerElement.style.height = '22px'
    markerElement.style.borderRadius = '50%'
    markerElement.style.background = '#ef4444'
    markerElement.style.border = '3px solid white'
    markerElement.style.boxShadow = '0 10px 22px rgba(0,0,0,0.35)'
    markerElement.style.transform = 'translate(-50%, -50%)'

    markerRef.current = new window.ymaps3.YMapMarker({ coordinates: selectedCoords }, markerElement)
    map.addChild(markerRef.current)
  }, [center, open, selectedCoords])

  async function handleSearch() {
    if (!query.trim()) {
      setError('Введите адрес для поиска')
      return
    }
    if (!API_KEY) {
      setSelectedAddress(query.trim())
      setError('')
      return
    }
    setSearching(true)
    setError('')
    try {
      const result = await geocodeAddress(query.trim())
      setSelectedCoords(result.coords)
      setSelectedAddress(result.address)
      setQuery(result.address)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSearching(false)
    }
  }

  if (!open) return null

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal location-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-hd">
          <div>
            <div className="card-title">Выбор адреса</div>
            <div className="ts tg" style={{ marginTop: 4 }}>
              Найдите адрес или кликните по карте, затем продолжите создание поста.
            </div>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Закрыть
          </button>
        </div>
        <div className="modal-bd">
          <div className="fg" style={{ marginBottom: 14 }}>
            <label>Адрес</label>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Введите адрес или выберите точку на карте"
                style={{ flex: 1, minWidth: 240 }}
              />
              <button type="button" className="btn btn-primary" onClick={handleSearch} disabled={searching}>
                {searching ? 'Ищем...' : 'Найти'}
              </button>
            </div>
          </div>

          {keyMissing ? (
            <div className="location-map-fallback">
              Чтобы включить карту Яндекса, добавьте `NEXT_PUBLIC_YANDEX_MAPS_API_KEY` в окружение. Пока можно сохранить адрес вручную.
            </div>
          ) : (
            <div>
              <div ref={mapContainerRef} className="location-map-box" />
              {loadingMap && <div className="location-map-note">Загружаем Яндекс Карту...</div>}
              <div className="location-map-note">Клик по карте выберет точку и попробует определить адрес автоматически.</div>
            </div>
          )}

          {selectedAddress && (
            <div className="location-selected-box">
              <div className="location-selected-title">Выбранный адрес</div>
              <div className="location-selected-text">{selectedAddress}</div>
              {selectedCoords && (
                <div className="location-selected-meta">
                  Координаты: {selectedCoords[1].toFixed(6)}, {selectedCoords[0].toFixed(6)}
                </div>
              )}
            </div>
          )}

          {error && <div className="location-error-box">{error}</div>}
        </div>
        <div className="modal-ft">
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={!query.trim() && !selectedAddress}
            onClick={() => onSelect({
              address: (selectedAddress || query).trim(),
              lat: selectedCoords ? selectedCoords[1] : null,
              lng: selectedCoords ? selectedCoords[0] : null,
            })}
          >
            Выбрать адрес
          </button>
        </div>
      </div>
    </div>
  )
}
