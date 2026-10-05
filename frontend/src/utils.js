export function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

export function publicAssetUrl(url) {
  if (!url) return ''
  return url.startsWith('/library/') ? url : url
}

