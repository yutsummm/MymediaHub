'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'
import type { Post } from '@/lib/types'
import PostEditor from '@/components/PostEditor'

export default function EditPostPage() {
  const { id } = useParams<{ id: string }>()
  const [post, setPost] = useState<Post | null>(null)

  useEffect(() => {
    api.getPost(Number(id)).then(setPost).catch(console.error)
  }, [id])

  if (!post) return <div className="content">⏳ Загрузка...</div>
  return <PostEditor editPost={post} />
}
