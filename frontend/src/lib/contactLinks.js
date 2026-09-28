/** Expand GitHub / LinkedIn handles to profile URLs (mirrors src/validators/contact_links.py). */

export function githubProfileUrl(raw) {
  const text = stripHandle(raw).replace(/^@/, '')
  if (!text) return ''
  const fromHost = text.match(/(?:^|https?:\/\/)?(?:www\.)?github\.com\/([^/?#]+)/i)
  if (fromHost) return `https://github.com/${fromHost[1].replace(/\/$/, '')}`
  if (/^https?:\/\//i.test(text)) {
    try {
      const path = new URL(text).pathname.replace(/^\/+|\/+$/g, '')
      const user = path.split('/')[0] || ''
      return user ? `https://github.com/${user}` : ''
    } catch {
      return ''
    }
  }
  const user = text.split('/').filter(Boolean).pop() || ''
  return user ? `https://github.com/${user}` : ''
}

export function linkedinProfileUrl(raw) {
  return parseLinkedinRef(raw)?.url || ''
}

export function isValidLinkedinUsername(raw) {
  return Boolean(parseLinkedinRef(raw))
}

const MEMBER_ID = /^ACoAA[A-Za-z0-9_-]{8,120}$/
const LINKEDIN_SLUG = /^[A-Za-z0-9](?:[A-Za-z0-9-]{1,98}[A-Za-z0-9])?$/
const PATH_SUFFIXES = new Set([
  'overlay', 'details', 'recent-activity', 'edit', 'about-this-profile',
  'en', 'fr', 'de', 'es', 'it', 'pt', 'nl', 'ja', 'ko', 'ru', 'tr', 'pl',
  'sv', 'da', 'fi', 'no', 'cs', 'ro', 'hu', 'th', 'vi', 'id', 'ms', 'ar',
  'he', 'zh', 'zh-cn', 'zh-tw', 'zh-hk', 'zh-hant', 'zh-hans',
])
const RESERVED = new Set([
  'in', 'pub', 'company', 'school', 'jobs', 'feed', 'login', 'signup',
  'mwlite', 'overlay', 'details', 'edit', 'sales', 'recruiter', 'talent',
])

function parseLinkedinRef(raw) {
  let text = String(raw || '').trim()
  if (!text || /\s/.test(text)) return null
  text = text.replace(/^@/, '')
  const lower = text.toLowerCase()
  if (
    lower.includes('/company/') ||
    lower.includes('/school/') ||
    lower.includes('/jobs/') ||
    lower.includes('/sales/') ||
    lower.includes('/recruiter/') ||
    lower.includes('linkedin.com/company') ||
    lower.includes('linkedin.com/school') ||
    lower.includes('linkedin.com/jobs')
  ) {
    return null
  }
  const short = text.match(/(?:^|https?:\/\/)?(?:www\.)?lnkd\.in\/([A-Za-z0-9_-]{4,24})/i)
  if (short) {
    return { handle: short[1], url: `https://lnkd.in/${short[1]}` }
  }
  let href = text
  if (!/^https?:\/\//i.test(href) && !href.startsWith('in/')) {
    href = `https://${href}`
  } else if (/^in\//i.test(href)) {
    href = `https://www.linkedin.com/${href}`
  }
  let parsed
  try {
    parsed = new URL(href)
  } catch {
    parsed = null
  }
  const host = (parsed?.hostname || '').replace(/^www\./i, '').toLowerCase()
  const memberFromQuery = memberIdFromSearch(parsed?.search || '')
  let slug = ''
  if (host.includes('linkedin.com')) {
    slug = pathProfileSlug(parsed.pathname || '')
  } else if (!lower.includes('linkedin.com') && !text.split('?')[0].includes('/')) {
    slug = text.split('?')[0].replace(/^\/+|\/+$/g, '')
  }
  const token = slug || memberFromQuery
  if (!token || RESERVED.has(token.toLowerCase())) return null
  if (MEMBER_ID.test(token)) {
    const url = slug
      ? `https://www.linkedin.com/in/${token}`
      : `https://www.linkedin.com/in/?profileId=${token}`
    return { handle: token, url }
  }
  if (!LINKEDIN_SLUG.test(token) || token.length < 3 || token.length > 100) return null
  return { handle: token, url: `https://www.linkedin.com/in/${token}` }
}

function memberIdFromSearch(search) {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  for (const key of ['profileId', 'miniProfileId', 'memberId']) {
    const value = (params.get(key) || '').trim()
    if (value) return decodeURIComponent(value)
  }
  for (const key of ['miniProfileUrn', 'profileUrn', 'urn']) {
    const value = decodeURIComponent((params.get(key) || '').trim())
    if (value.includes(':')) return value.split(':').pop() || ''
  }
  return ''
}

function pathProfileSlug(pathname) {
  const parts = pathname.split('/').filter(Boolean).map((p) => decodeURIComponent(p))
  const lowered = parts.map((p) => p.toLowerCase())
  for (const marker of ['in', 'pub']) {
    const idx = lowered.indexOf(marker)
    if (idx < 0) continue
    for (const segment of parts.slice(idx + 1)) {
      if (PATH_SUFFIXES.has(segment.toLowerCase())) continue
      if (RESERVED.has(segment.toLowerCase())) return ''
      return segment
    }
  }
  if (lowered[0] === 'mwlite' && lowered[1] === 'in') {
    for (const segment of parts.slice(2)) {
      if (!PATH_SUFFIXES.has(segment.toLowerCase())) return segment
    }
  }
  return ''
}

export function websiteUrl(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  if (/^https?:\/\//i.test(text)) return text
  return `https://${text.replace(/^\/+/, '')}`
}

function stripHandle(value) {
  return String(value || '')
    .trim()
    .split('?')[0]
    .split('#')[0]
    .replace(/\/+$/, '')
}
