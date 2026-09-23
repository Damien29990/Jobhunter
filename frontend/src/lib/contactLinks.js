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
  const text = stripHandle(raw).replace(/^@/, '')
  if (!text) return ''
  const fromIn = text.match(
    /(?:^|https?:\/\/)?(?:[a-z]{2}\.)?(?:www\.)?linkedin\.com\/(?:in|pub|mwlite\/in)\/([^/?#]+)/i,
  )
  if (fromIn) return `https://www.linkedin.com/in/${fromIn[1].replace(/\/$/, '')}`
  if (/^in\//i.test(text)) {
    const slug = text.slice(3).replace(/^\/+|\/+$/g, '')
    return slug ? `https://www.linkedin.com/in/${slug}` : ''
  }
  const slug = text.split('/').filter(Boolean).pop() || ''
  return slug ? `https://www.linkedin.com/in/${slug}` : ''
}

export function websiteUrl(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  if (/^https?:\/\//i.test(text)) return text
  return `https://${text.replace(/^\/+/, '')}`
}

const LINKEDIN_SLUG = /^[A-Za-z0-9](?:[A-Za-z0-9-]{1,98}[A-Za-z0-9])?$/

export function isValidLinkedinUsername(raw) {
  const text = String(raw || '').trim()
  if (!text || /\s/.test(text)) return false
  const lower = text.toLowerCase()
  if (
    lower.includes('/company/') ||
    lower.includes('/school/') ||
    lower.includes('/jobs/') ||
    lower.includes('linkedin.com/company') ||
    lower.includes('linkedin.com/school') ||
    lower.includes('linkedin.com/jobs')
  ) {
    return false
  }
  const url = linkedinProfileUrl(text)
  const slug = url.replace(/\/$/, '').split('/').pop() || ''
  if (slug.length < 3 || slug.length > 100) return false
  return LINKEDIN_SLUG.test(slug)
}

function stripHandle(value) {
  return String(value || '')
    .trim()
    .split('?')[0]
    .split('#')[0]
    .replace(/\/+$/, '')
}
