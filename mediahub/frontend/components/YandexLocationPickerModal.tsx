'use client'

import { useEffect, useRef, useState } from 'react'

type Coordinates = [number, number] // [lng, lat]

type Props = {
  open: boolean
  initialAddress?: string
  initialLat?: number | null
  initialLng?: number | null
  onClose: () => void
  onSelect: (payload: { address: string; lat: number | null; lng: number | null }) => void
}

declare global {
  interface Window {
    ymaps3?: {
      ready: Promise<void>
      YMap: new (element: HTMLElement, props: unknown) => {
        addChild: (entity: unknown) => void
        removeChild: (entity: unknown) => void
        setLocation: (loc: { center: Coordinates; zoom?: number; duration?: number }) => void
        destroy: () => void
      }
      YMapDefaultSchemeLayer: new () => unknown
      YMapDefaultFeaturesLayer: new () => unknown
      YMapMarker: new (props: unknown, element?: HTMLElement) => unknown
      YMapListener: new (props: unknown) => unknown
    }
  }
}

const DEFAULT_CENTER: Coordinates = [37.617617, 55.755819] // Moscow
const API_KEY = process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY ?? ''

let mapsPromise: Promise<NonNullable<typeof window.ymaps3>> | null = null

function loadYandexMaps() {
  if (mapsPromise) return mapsPromise
  mapsPromise = new Promise((resolve, reject) => {
    if (typeof window === 'undefined') return reject(new Error('SSR'))
    if (window.ymaps3) {
      window.ymaps3.ready.then(() => resolve(window.ymaps3!)).catch(reject)
      return
    }
    const script = document.createElement('script')
    script.src = `https://api-maps.yandex.ru/v3/?apikey=${API_KEY}&lang=ru_RU`
    script.async = true
    script.onload = () => {
      if (!window.ymaps3) return reject(new Error('ymaps3 not available after script load'))
      window.ymaps3.ready.then(() => resolve(window.ymaps3!)).catch(reject)
    }
    script.onerror = () => {
      mapsPromise = null
      reject(new Error('Failed to load Yandex Maps script'))
    }
    document.head.appendChild(script)
  })
  return mapsPromise
}

async function geocode(query: string): Promise<{ coords: Coordinates; address: string }> {
  const url = `https://geocode-maps.yandex.ru/v1/?apikey=${API_KEY}&geocode=${encodeURIComponent(query)}&lang=ru_RU&format=json&results=1`
  const res = await fetch(url)
  if (!res.ok) throw new Error('Geocoder request failed')
  const data = await res.json()
  const geo = data?.response?.GeoObjectCollection?.featureMember?.[0]?.GeoObject
  const pos = geo?.Point?.pos as string | undefined
  const text = geo?.metaDataProperty?.GeocoderMetaData?.text as string | undefined
  if (!pos || !text) throw new Error('Адрес не найден')
  const [lng, lat] = pos.split(' ').map(Number)
  return { coords: [lng, lat], address: text }
}

async function reverseGeocode(coords: Coordinates): Promise<string> {
  const url = `https://geocode-maps.yandex.ru/v1/?apikey=${API_KEY}&geocode=${coords[0]},${coords[1]}&lang=ru_RU&format=json&results=1&kind=house`
  const res = await fetch(url)
  if (!res.ok) throw new Error('Reverse geocoder request failed')
  const data = await res.json()
  const geo = data?.response?.GeoObjectCollection?.featureMember?.[0]?.GeoObject
  const text = geo?.metaDataProperty?.GeocoderMetaData?.text as string | undefined
  return text ?? `${coords[1].toFixed(6)}, ${coords[0].toFixed(6)}`
}

export default function YandexLocationPickerModal({
  open,
  initialAddress = '',
  initialLat = null,
  initialLng = null,
  onClose,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<InstanceType<NonNullable<typeof window.ymaps3>['YMap']> | null>(null)
  const markerRef = useRef<unknown>(null)

  const [query, setQuery] = useState(initialAddress)
  const [selectedAddress, setSelectedAddress] = useState(initialAddress)
  const [selectedCoords, setSelectedCoords] = useState<Coordinates | null>(
    initialLat != null && initialLng != null ? [initialLng, initialLat] : null
  )
  const [mapError, setMapError] = useState('')
  const [mapLoading, setMapLoading] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')

  // Reset state when modal opens
  useEffect(() => {
    if (!open) return
    setQuery(initialAddress)
    setSelectedAddress(initialAddress)
    setSelectedCoords(initialLat != null && initialLng != null ? [initialLng, initialLat] : null)
    setMapError('')
    setSearchError('')
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Initialize map once when modal opens, destroy when closes
  useEffect(() => {
    if (!open) return
    if (!API_KEY) {
      setMapError('Не задан NEXT_PUBLIC_YANDEX_MAPS_API_KEY')
      return
    }

    let cancelled = false
    setMapLoading(true)
    setMapError('')

    const init = async () => {
      // Wait for container to be in DOM
      await new Promise(r => setTimeout(r, 50))
      if (cancelled || !containerRef.current) return

      try {
        const ymaps3 = await loadYandexMaps()
        if (cancelled || !containerRef.current) return

        const center = selectedCoords ?? DEFAULT_CENTER
        const map = new ymaps3.YMap(containerRef.current, {
          location: { center, zoom: selectedCoords ? 15 : 10 },
          behaviors: ['drag', 'scrollZoom', 'dblClick', 'pinchZoom'],
        })
        map.addChild(new ymaps3.YMapDefaultSchemeLayer())
        map.addChild(new ymaps3.YMapDefaultFeaturesLayer())

        const listener = new ymaps3.YMapListener({
          layer: 'any',
          onClick: async (_obj: unknown, event: { coordinates?: Coordinates }) => {
            if (cancelled || !event?.coordinates) return
            const coords = event.coordinates as Coordinates
            setSelectedCoords(coords)
            setSearchError('')
            try {
              const address = await reverseGeocode(coords)
              if (cancelled) return
              setSelectedAddress(address)
              setQuery(address)
            } catch {
              // coords still set, address will be coordinate string
            }
          },
        })
        map.addChild(listener)
        mapRef.current = map

        // Add initial marker if coords set
        if (selectedCoords) {
          const el = makeMarkerEl()
          const marker = new ymaps3.YMapMarker({ coordinates: selectedCoords }, el)
          map.addChild(marker)
          markerRef.current = marker
        }
      } catch (err) {
        if (!cancelled) setMapError((err as Error).message)
      } finally {
        if (!cancelled) setMapLoading(false)
      }
    }

    void init()

    return () => {
      cancelled = true
      if (mapRef.current) {
        mapRef.current.destroy()
        mapRef.current = null
      }
      markerRef.current = null
      setMapLoading(false)
    }
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  // Update marker and pan map when selectedCoords changes (after initial mount)
  useEffect(() => {
    if (!open || !mapRef.current || !window.ymaps3) return
    const map = mapRef.current

    if (markerRef.current) {
      map.removeChild(markerRef.current)
      markerRef.current = null
    }

    if (selectedCoords) {
      map.setLocation({ center: selectedCoords, zoom: 15, duration: 400 })
      const el = makeMarkerEl()
      const marker = new window.ymaps3.YMapMarker({ coordinates: selectedCoords }, el)
      map.addChild(marker)
      markerRef.current = marker
    }
  }, [selectedCoords, open])

  function makeMarkerEl() {
    const el = document.createElement('div')
    el.style.cssText = 'width:22px;height:22px;border-radius:50%;background:#ef4444;border:3px solid #fff;box-shadow:0 2px 12px rgba(0,0,0,.4);transform:translate(-50%,-50%)'
    return el
  }

  async function handleSearch() {
    const q = query.trim()
    if (!q) { setSearchError('Введите адрес'); return }
    setSearching(true)
    setSearchError('')
    try {
      const { coords, address } = await geocode(q)
      setSelectedCoords(coords)
      setSelectedAddress(address)
      setQuery(address)
    } catch (err) {
      setSearchError((err as Error).message)
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
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Введите адрес или выберите точку на карте"
                style={{ flex: 1 }}
              />
              <button type="button" className="btn btn-primary" onClick={handleSearch} disabled={searching}>
                {searching ? 'Ищем...' : 'Найти'}
              </button>
            </div>
          </div>

          <div
            ref={containerRef}
            className="location-map-box"
            style={{ position: 'relative' }}
          >
            {mapLoading && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                color: 'var(--text-3)', fontSize: 13, zIndex: 1, pointerEvents: 'none',
              }}>
                Загружаем карту...
              </div>
            )}
          </div>

          {mapError && (
            <div className="location-error-box" style={{ marginTop: 8 }}>{mapError}</div>
          )}
          {searchError && (
            <div className="location-error-box" style={{ marginTop: 8 }}>{searchError}</div>
          )}

          <div className="location-map-note">Клик по карте выберет точку и определит адрес автоматически.</div>

          {selectedAddress && (
            <div className="location-selected-box">
              <div className="location-selected-title">Выбранный адрес</div>
              <div className="location-selected-text">{selectedAddress}</div>
              {selectedCoords && (
                <div className="location-selected-meta">
                  {selectedCoords[1].toFixed(6)}, {selectedCoords[0].toFixed(6)}
                </div>
              )}
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
            disabled={!selectedAddress && !query.trim()}
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
