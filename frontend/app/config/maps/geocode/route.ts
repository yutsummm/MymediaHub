import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'
export const revalidate = 0

type YandexGeoObject = {
  name?: string
  description?: string
  Point?: {
    pos?: string
  }
  metaDataProperty?: {
    GeocoderMetaData?: {
      text?: string
      Address?: {
        formatted?: string
      }
    }
  }
}

type YandexGeocodeResponse = {
  response?: {
    GeoObjectCollection?: {
      featureMember?: Array<{
        GeoObject?: YandexGeoObject
      }>
    }
  }
}

type GeocodeResult = {
  address: string
  lat: number
  lon: number
}

type OsmSearchItem = {
  display_name?: string
  lat?: string
  lon?: string
  name?: string
  address?: Record<string, string | undefined>
}

function getYandexMapsKey() {
  return (
    process.env.NEXT_PUBLIC_YANDEX_MAPS_KEY ||
    process.env.NEXT_PUBLIC_YANDEX_MAPS_API_KEY ||
    process.env.YANDEX_MAPS_KEY ||
    process.env.YANDEX_MAPS_API_KEY ||
    ''
  ).trim()
}

function parsePoint(pos?: string) {
  if (!pos) return null
  const [lon, lat] = pos.split(' ').map(Number)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  return { lat, lon }
}

function getReadableAddress(geoObject: YandexGeoObject) {
  const meta = geoObject.metaDataProperty?.GeocoderMetaData
  const formatted = meta?.Address?.formatted?.trim()
  const text = meta?.text?.trim()
  const name = geoObject.name?.trim()
  const description = geoObject.description?.trim()

  if (formatted) return formatted
  if (text) return text
  if (description && name) return `${description}, ${name}`
  return name || description || ''
}

function jsonError(message: string, status: number) {
  return NextResponse.json({ error: message }, { status })
}

function parseYandexResponse(data: YandexGeocodeResponse): GeocodeResult | null {
  const geoObject = data.response?.GeoObjectCollection?.featureMember?.[0]?.GeoObject
  if (!geoObject) return null

  const point = parsePoint(geoObject.Point?.pos)
  const address = getReadableAddress(geoObject)
  if (!point || !address) return null

  return {
    address,
    lat: point.lat,
    lon: point.lon,
  }
}

function formatOsmAddress(item: OsmSearchItem) {
  const address = item.address || {}
  const road = address.road || address.pedestrian || address.footway || address.neighbourhood
  const house = address.house_number
  const city = address.city || address.town || address.village || address.municipality || address.county
  const name = item.name?.trim()
  const street = [road, house].filter(Boolean).join(', ')
  const parts: string[] = []

  if (name && name !== road && name !== house) parts.push(name)
  if (street) parts.push(street)
  if (city) parts.push(city)

  return parts.length > 0 ? parts.join(', ') : item.display_name || ''
}

function parseOsmItem(item?: OsmSearchItem): GeocodeResult | null {
  if (!item?.display_name || !item.lat || !item.lon) return null
  const lat = Number(item.lat)
  const lon = Number(item.lon)
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null
  return {
    address: formatOsmAddress(item),
    lat,
    lon,
  }
}

async function geocodeWithYandex(key: string, geocode: string, isReverse: boolean): Promise<GeocodeResult | null> {
  const params = new URLSearchParams({
    apikey: key,
    geocode,
    format: 'json',
    lang: 'ru_RU',
    results: '1',
  })
  if (isReverse) params.set('kind', 'house')

  const response = await fetch(`https://geocode-maps.yandex.ru/v1/?${params.toString()}`, {
    cache: 'no-store',
  })

  if (!response.ok) return null
  return parseYandexResponse(await response.json() as YandexGeocodeResponse)
}

async function geocodeWithOpenStreetMap(query: string, isReverse: boolean): Promise<GeocodeResult | null> {
  const url = isReverse
    ? `https://nominatim.openstreetmap.org/reverse?${query}`
    : `https://nominatim.openstreetmap.org/search?${query}`

  const response = await fetch(url, {
    cache: 'no-store',
    headers: {
      'Accept-Language': 'ru',
      'User-Agent': 'MediaHub/1.0 youth media platform',
    },
  })

  if (!response.ok) return null

  if (isReverse) {
    return parseOsmItem(await response.json() as OsmSearchItem)
  }

  const data = await response.json() as OsmSearchItem[]
  return parseOsmItem(data[0])
}

export async function GET(request: NextRequest) {
  const key = getYandexMapsKey()
  const { searchParams } = request.nextUrl
  const query = searchParams.get('q')?.trim()
  const lat = searchParams.get('lat')
  const lon = searchParams.get('lon')
  const latNumber = lat ? Number(lat) : NaN
  const lonNumber = lon ? Number(lon) : NaN
  const isReverse = Number.isFinite(latNumber) && Number.isFinite(lonNumber)

  if (!query && !isReverse) {
    return jsonError('Передайте адрес или координаты точки.', 400)
  }

  try {
    const yandexGeocode = isReverse ? `${lonNumber},${latNumber}` : query || ''
    const yandexResult = key ? await geocodeWithYandex(key, yandexGeocode, isReverse) : null
    if (yandexResult) {
      return NextResponse.json(yandexResult, {
        headers: {
          'Cache-Control': 'no-store, no-cache, must-revalidate',
        },
      })
    }

    const osmQuery = isReverse
      ? new URLSearchParams({
        format: 'jsonv2',
        lat: String(latNumber),
        lon: String(lonNumber),
        zoom: '18',
        addressdetails: '1',
        'accept-language': 'ru',
      }).toString()
      : new URLSearchParams({
        format: 'jsonv2',
        q: query || '',
        limit: '1',
        addressdetails: '1',
        'accept-language': 'ru',
      }).toString()

    const osmResult = await geocodeWithOpenStreetMap(osmQuery, isReverse)
    if (osmResult) {
      return NextResponse.json(osmResult, {
        headers: {
          'Cache-Control': 'no-store, no-cache, must-revalidate',
        },
      })
    }

    return jsonError('Адрес не найден. Попробуйте указать его точнее или выберите точку на карте.', 404)
  } catch {
    return jsonError('Не удалось определить адрес. Попробуйте ещё раз.', 502)
  }
}
