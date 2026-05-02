import { store, json } from '../../_store'

export async function GET() {
  const published = store.posts.filter(p => p.status === 'published')
  const summary = {
    total_posts: store.posts.length,
    published: published.length,
    scheduled: store.posts.filter(p => p.status === 'scheduled').length,
    drafts: store.posts.filter(p => p.status === 'draft').length,
    total_views: published.reduce((s, p) => s + p.views, 0),
    total_reactions: published.reduce((s, p) => s + p.reactions, 0),
    total_comments: published.reduce((s, p) => s + p.comments, 0),
    total_shares: published.reduce((s, p) => s + p.shares, 0),
    avg_views: published.length ? Math.round(published.reduce((s, p) => s + p.views, 0) / published.length) : 0,
    engagement_rate: 4.7,
    top_posts: [...published].sort((a, b) => b.views - a.views).slice(0, 3),
    platform_stats: [
      { platform: 'vk', count: published.filter(p => p.platforms.includes('vk')).length, views: 24500, reactions: 1820 },
      { platform: 'telegram', count: published.filter(p => p.platforms.includes('telegram')).length, views: 16800, reactions: 1340 },
    ],
  }
  return json(summary)
}
