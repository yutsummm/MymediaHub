import PostEditor from '@/components/PostEditor'

type SearchParams = Record<string, string | string[] | undefined>

function readString(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value
}

export default function NewPostPage({ searchParams }: { searchParams?: SearchParams }) {
  const status = readString(searchParams?.status)
  const scheduledAt = readString(searchParams?.scheduled_at)
  const locationAddress = readString(searchParams?.location_address)
  const locationLatValue = readString(searchParams?.location_lat)
  const locationLngValue = readString(searchParams?.location_lng)

  const locationLat = locationLatValue ? Number(locationLatValue) : null
  const locationLng = locationLngValue ? Number(locationLngValue) : null

  return (
    <PostEditor
      initialStatus={status === 'scheduled' || status === 'published' || status === 'draft' ? status : undefined}
      initialScheduledAt={scheduledAt}
      initialLocationAddress={locationAddress}
      initialLocationLat={Number.isFinite(locationLat) ? locationLat : null}
      initialLocationLng={Number.isFinite(locationLng) ? locationLng : null}
    />
  )
}
