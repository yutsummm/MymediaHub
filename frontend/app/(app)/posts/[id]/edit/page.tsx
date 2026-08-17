'use client'
import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import { api } from '@/lib/api'
import { useGroup } from '@/contexts/GroupContext'
import type { Post } from '@/lib/types'
import PostEditor from '@/components/PostEditor'
import PostHistory from '@/components/PostHistory'

export default function EditPostPage() {
  const { id } = useParams<{ id: string }>()
  const { currentGroup } = useGroup()
  const [post, setPost] = useState<Post | null>(null)

  useEffect(() => {
    const numId = Number(id)
    if (currentGroup) api.getGroupPost(currentGroup.id, numId).then(setPost).catch(console.error)
    else api.getPost(numId).then(setPost).catch(console.error)
  }, [id, currentGroup])

  if (!post) return (
    <div className="content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
      <div style={{ textAlign: 'center', color: 'var(--text-3)' }}>
        <div style={{ marginBottom: 14, opacity: 0.2 }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </div>
        <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 700 }}>Загрузка</div>
      </div>
    </div>
  )
  return (
    <>
      <PostEditor editPost={post} />
      {/* Лента событий под редактором: замечание рецензента жило в одном
          уведомлении, которое легко смахнуть и больше не найти. */}
      <div className="content" style={{ paddingTop: 0 }}>
        {/* Та же ширина, что у редактора выше: лента на всю страницу
            выглядела бы отдельным разделом, а это продолжение карточки. */}
        <div style={{ maxWidth: 720, margin: '0 auto' }}>
          <PostHistory postId={post.id} />
        </div>
      </div>
    </>
  )
}
