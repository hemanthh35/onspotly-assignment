const BASE = '/api/v1'

async function request(path, { method = 'GET', body, form } = {}) {
  const opts = { method, headers: {} }
  if (form) opts.body = form
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(BASE + path, opts)
  if (!res.ok) {
    let msg = res.statusText
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* not JSON */ }
    throw new Error(msg)
  }
  return res.status === 204 ? null : res.json()
}

/** Upload with progress (fetch has no upload progress events). */
function upload(path, form, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', BASE + path)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
    xhr.onload = () => {
      let data = null
      try { data = JSON.parse(xhr.responseText) } catch { /* empty */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data)
      else reject(new Error(data?.detail || `Upload failed (${xhr.status})`))
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.send(form)
  })
}

export const api = {
  health: () => request('/health'),
  projects: () => request('/projects'),
  project: (id) => request(`/projects/${id}`),
  createProject: (body) => request('/projects', { method: 'POST', body }),
  updateProject: (id, body) => request(`/projects/${id}`, { method: 'PATCH', body }),
  deleteProject: (id) => request(`/projects/${id}`, { method: 'DELETE' }),
  uploadFootage: (id, files, onProgress) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return upload(`/projects/${id}/assets`, form, onProgress)
  },
  uploadMusic: (id, file) => {
    const form = new FormData()
    form.append('file', file)
    return request(`/projects/${id}/music`, { method: 'POST', form })
  },
  deleteAsset: (id) => request(`/assets/${id}`, { method: 'DELETE' }),
  reanalyze: (id) => request(`/projects/${id}/analyze`, { method: 'POST' }),
  plan: (id) => request(`/projects/${id}/shot-lists/plan`, { method: 'POST' }),
  importShotList: (id, file, name) => {
    const form = new FormData()
    form.append('file', file)
    form.append('name', name)
    return request(`/projects/${id}/shot-lists/import`, { method: 'POST', form })
  },
  createShotList: (id, body) => request(`/projects/${id}/shot-lists`, { method: 'POST', body }),
  saveShotList: (id, body) => request(`/shot-lists/${id}`, { method: 'PUT', body }),
  deleteShotList: (id) => request(`/shot-lists/${id}`, { method: 'DELETE' }),
  find: (id, approach = 'hybrid') => request(`/shot-lists/${id}/find`, { method: 'POST', body: { approach } }),
  saveTimeline: (id, timeline) => request(`/runs/${id}/timeline`, { method: 'PUT', body: { timeline } }),
  render: (id, options) => request(`/runs/${id}/render`, { method: 'POST', body: options }),
  job: (id) => request(`/jobs/${id}`),
}

/** The run the editor/export should show: ?run= if set, else the newest hybrid run, else the newest. */
export function pickRun(runs, runId) {
  return runs.find((r) => r.id === runId) || [...runs].reverse().find((r) => r.approach === 'hybrid') || runs.at(-1)
}

export const streamUrl =(assetId) => `${BASE}/assets/${assetId}/stream`
export const thumbUrl = (assetId, t, w = 480) => `${BASE}/assets/${assetId}/thumb?t=${(t ?? 0).toFixed(1)}&w=${w}`
export const runFileUrl = (runId, kind) => `${BASE}/runs/${runId}/download/${kind}`
export const exportUrl = (exportId, inline = false) => `${BASE}/exports/${exportId}/download${inline ? '?inline=true' : ''}`

export const fmtTime = (s) => {
  if (s == null || Number.isNaN(s)) return '–'
  const m = Math.floor(s / 60)
  const sec = (s - m * 60).toFixed(1).padStart(4, '0')
  return m ? `${m}:${sec}` : `${(+s).toFixed(1)}s`
}
export const fmtBytes = (b) => (b > 2 ** 30 ? `${(b / 2 ** 30).toFixed(2)} GB` : b > 2 ** 20 ? `${(b / 2 ** 20).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`)
