const API_BASE = import.meta.env.VITE_API_BASE_URL || ''
const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL || '').replace(/\/$/, '')
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || ''
const SUPABASE_BUCKET = import.meta.env.VITE_SUPABASE_STORAGE_BUCKET || 'images'

const hasSupabase = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY)

async function parseError(response) {
  const text = await response.text()
  if (!text) return response.statusText
  try {
    const data = JSON.parse(text)
    return data.detail || data.message || text
  } catch {
    return text
  }
}

export async function requestJson(path, options) {
  const response = await fetch(`${API_BASE}${path}`, options)
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  return response.json()
}

export function listJobs() {
  if (!hasSupabase) return requestJson('/api/v1/library')
  return listSupabaseJobs().catch(() => requestJson('/api/v1/library'))
}

export function getJob(jobId) {
  if (!hasSupabase) return requestJson(`/api/v1/library/${encodeURIComponent(jobId)}`)
  return getSupabaseJob(jobId).catch(() => requestJson(`/api/v1/library/${encodeURIComponent(jobId)}`))
}

export function deleteJob(jobId) {
  return requestJson(`/api/v1/library/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
}

export function processPdf(file) {
  const formData = new FormData()
  formData.append('file', file)
  return requestJson('/api/v1/process/pdf', { method: 'POST', body: formData })
}

async function supabaseRequest(path, options = {}) {
  const response = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...options,
    headers: {
      apikey: SUPABASE_ANON_KEY,
      Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
      Accept: 'application/json',
      ...(options.headers || {}),
    },
  })
  if (!response.ok) throw new Error(await parseError(response))
  return response.json()
}

function storageUrl(path) {
  if (!path) return ''
  return `${SUPABASE_URL}/storage/v1/object/public/${encodeURIComponent(SUPABASE_BUCKET)}/${path
    .split('/')
    .map((part) => encodeURIComponent(part))
    .join('/')}`
}

async function listSupabaseJobs() {
  const rows = await supabaseRequest('wiring_tables?select=*&order=created_at.desc')
  const grouped = new Map()
  for (const row of rows) {
    const current = grouped.get(row.job_id) || { rows: [], row }
    current.rows.push(row)
    grouped.set(row.job_id, current)
  }
  return [...grouped.values()].map(({ rows, row }) => summarizeSupabaseJob(row, rows))
}

async function getSupabaseJob(jobId) {
  const rows = await supabaseRequest(
    `wiring_tables?job_id=eq.${encodeURIComponent(jobId)}&select=*&order=created_at.asc`,
  )
  if (!rows.length) throw new Error('Supabase job not found')
  return buildSupabaseJob(rows[0], rows)
}

function summarizeSupabaseJob(row, rows) {
  const job = buildSupabaseJob(row, rows)
  return {
    job_id: job.job_id,
    name: job.name,
    status: job.status,
    created_at: job.created_at,
    source_filename: job.source_filename,
    source_url: job.source_url,
    page_count: job.page_count,
    group_count: job.group_count,
    record_count: job.record_count,
    status_message: job.status_message,
  }
}

function buildSupabaseJob(firstRow, rows) {
  const allPagePaths = new Set()
  for (const row of rows) {
    for (const path of row.all_page_paths || []) allPagePaths.add(path)
  }
  const pages = [...allPagePaths]
    .sort(pagePathSort)
    .map((path, index) => ({
      page_id: `page-${index + 1}`,
      page_number: pageNumber(path, index + 1),
      filename: path.split('/').pop(),
      url: storageUrl(path),
    }))
  const groups = rows.map((row) => ({
    group_id: row.group_id,
    title: row.title,
    pages: row.pages || [],
    reason: row.reason,
    status: row.status,
    record_count: row.record_count || row.records?.length || 0,
    records: row.records || [],
    json_url: storageUrl(row.records_path),
    xlsx_url: storageUrl(row.xlsx_path),
    import_xls_url: storageUrl(row.import_xls_path),
    import_xlsx_url: storageUrl(row.import_xlsx_path),
    error: row.error,
  }))
  const sourceUrl = storageUrl(firstRow.source_pdf_path)
  const statuses = rows.map((row) => row.status)
  const status = statuses.every((value) => value === 'success')
    ? 'success'
    : statuses.some((value) => value === 'success')
      ? 'partial'
      : statuses.some((value) => value === 'failed')
        ? 'failed'
        : 'processing'
  return {
    job_id: firstRow.job_id,
    name: firstRow.metadata?.job_name || firstRow.source_filename.replace(/\.pdf$/i, ''),
    status,
    created_at: rows.map((row) => row.created_at).sort()[0] || firstRow.created_at,
    source_filename: firstRow.source_filename,
    source_url: sourceUrl,
    page_count: pages.length,
    group_count: groups.length,
    record_count: groups.reduce((total, group) => total + group.record_count, 0),
    status_message: firstRow.metadata?.status_message || `${groups.length} 个线表批次`,
    pages,
    groups,
    manifest: { source_url: sourceUrl, supabase: true },
  }
}

function pageNumber(path, fallback) {
  const match = path.match(/page_(\d+)\.png$/i)
  return match ? Number(match[1]) : fallback
}

function pagePathSort(left, right) {
  return pageNumber(left, 0) - pageNumber(right, 0)
}
