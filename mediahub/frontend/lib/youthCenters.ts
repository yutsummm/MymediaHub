import type { YouthCenter } from '@/lib/types'

export type Coordinates = [number, number]

export const KRASNOYARSK_CENTER: Coordinates = [56.010563, 92.852572]

export const KRASNOYARSK_YOUTH_CENTERS: YouthCenter[] = [
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

export function getCenterCoordinates(center: YouthCenter): Coordinates {
  if (center.coordinates) return center.coordinates
  return [center.lat, center.lon]
}

export function normalizeYouthCenters(centers: YouthCenter[]) {
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

export function distanceKm(from: Coordinates, to: Coordinates) {
  const earthRadiusKm = 6371
  const dLat = toRadians(to[0] - from[0])
  const dLon = toRadians(to[1] - from[1])
  const lat1 = toRadians(from[0])
  const lat2 = toRadians(to[0])
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return Math.round(earthRadiusKm * 2 * Math.asin(Math.sqrt(a)) * 100) / 100
}

export function sortYouthCentersByDistance(centers: YouthCenter[], coordinates: Coordinates) {
  return normalizeYouthCenters(centers)
    .map(center => ({
      ...center,
      distance_km: center.distance_km ?? distanceKm(coordinates, getCenterCoordinates(center)),
    }))
    .sort((a, b) => (a.distance_km ?? 0) - (b.distance_km ?? 0))
}

export function formatYouthCenterAddress(center: YouthCenter) {
  return `${center.name}, ${center.address}`
}
