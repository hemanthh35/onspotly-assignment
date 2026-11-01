import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Download, History, Music, Play, Trash2, Type, X, Film, Clock, Layers } from 'lucide-react'
import clsx from 'clsx'
import { api, exportUrl, fmtBytes } from '../../api.js'
import { Empty, Pagination } from '../ui.jsx'

const PAGE_SIZE = 6

function dayLabel(d) {
  const day = new Date(d)
  const today = new Date()
  const y = new Date(); y.setDate(today.getDate() - 1)
  if (day.toDateString() === today.toDateString()) return 'Today'
  if (day.toDateString() === y.toDateString()) return 'Yesterday'
  return day.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
}

function Player({ v, onClose }) {
  const vertical = v.options?.aspect === '9:16' || v.options?.aspect === '4:5'
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/85 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`Version ${v.options?.version}`} onClick={onClose}>
      <div className="w-full max-w-3xl overflow-hidden rounded-3xl bg-white" onClick={(e) => e.stopPropagation()}>
        <video src={exportUrl(v.id, true)} controls autoPlay playsInline className={clsx('w-full bg-ink', vertical && 'mx-auto max-h-[70vh] w-auto')} />
        <div className="flex flex-wrap items-center gap-3 p-4">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-ink font-display text-sm font-bold text-white">v{v.options?.version}</span>
          <div className="min-w-0 flex-1 text-xs">
            <p className="break-all font-semibold text-ink">{v.filename}</p>
            <p className="text-muted">{v.options?.cut} · {v.options?.aspect} · {v.options?.duration?.toFixed?.(1)}s · {fmtBytes(v.size_bytes)}</p>
          </div>
          <a href={exportUrl(v.id)} className="btn-primary btn-sm"><Download size={13} /> Download</a>
          <button onClick={onClose} className="btn-ghost btn-sm" aria-label="Close"><X size={13} /></button>
        </div>
      </div>
    </div>
  )
}

function VersionCard({ v, latest, onPlay, onDelete }) {
  const o = v.options || {}
  return (
    <div className="card group overflow-hidden">
      <button onClick={onPlay} className="relative block aspect-video w-full overflow-hidden bg-ink" aria-label={`Play version ${o.version}`}>
        <video src={`${exportUrl(v.id, true)}#t=${Math.min(2, (o.duration || 4) / 2)}`} preload="metadata" muted playsInline
          className={clsx('h-full w-full', o.aspect === '9:16' || o.aspect === '4:5' ? 'object-contain' : 'object-cover')} />
        <span className="absolute inset-0 grid place-items-center bg-black/20 opacity-0 transition group-hover:opacity-100">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-white/95 text-ink"><Play size={18} className="ml-0.5" /></span>
        </span>
        <span className="absolute left-2 top-2 rounded-md bg-ink/85 px-2 py-0.5 font-display text-xs font-bold text-white">v{o.version}</span>
        {latest && <span className="absolute right-2 top-2 chip bg-brand text-white">Latest</span>}
        <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 text-[11px] tabular-nums text-white">{o.duration?.toFixed?.(1)}s</span>
      </button>
      <div className="space-y-2 p-3.5">
        <p className="break-all text-xs font-semibold leading-snug" title={v.filename}>{v.filename}</p>
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          <span className="chip bg-stone-100 text-ink"><Layers size={10} /> {o.cut || 'Cut'}</span>
          <span className="chip bg-stone-100 text-ink">{o.aspect}</span>
          {o.crossfade > 0 && <span className="chip bg-stone-100 text-ink">fades</span>}
          {o.music_asset_id && <span className="chip bg-sky-50 text-sky-700"><Music size={10} /> music</span>}
          {o.title && <span className="chip bg-brand-soft text-brand"><Type size={10} /> title</span>}
        </div>
        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="flex items-center gap-1 text-[11px] text-muted"><Clock size={11} /> {new Date(v.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {fmtBytes(v.size_bytes)}</span>
          <div className="flex gap-1">
            <button onClick={onDelete} className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-stone-100 hover:text-brand" aria-label={`Delete version ${o.version}`}><Trash2 size={14} /></button>
            <a href={exportUrl(v.id)} className="btn-dark btn-sm" aria-label={`Download version ${o.version}`}><Download size={13} /></a>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function VersionsStep({ project, goExport }) {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [runId, setRunId] = useState('')
  const [playing, setPlaying] = useState(null)
  const { data, isLoading } = useQuery({
    queryKey: ['versions', project.id, page, runId, project.version_count],
    queryFn: () => api.versions(project.id, { page, pageSize: PAGE_SIZE, runId }),
    placeholderData: keepPreviousData,
  })
  const cutName = (rid) => {
    const r = project.runs.find((x) => x.id === rid)
    const sl = project.shot_lists.find((s) => s.id === r?.shot_list_id)
    return `${sl?.name || 'Cut'} · ${r?.approach || ''}`
  }
  const groups = useMemo(() => {
    const g = []
    for (const v of data?.items || []) {
      const label = dayLabel(v.created_at)
      if (g.at(-1)?.label !== label) g.push({ label, items: [] })
      g.at(-1).items.push(v)
    }
    return g
  }, [data])
  const newestId = data?.page === 1 && !runId ? data.items[0]?.id : null

  async function remove(v) {
    if (!confirm(`Delete version ${v.options?.version} (${v.filename})? This removes the file.`)) return
    await api.deleteExport(v.id)
    toast.success(`Version ${v.options?.version} deleted`)
    qc.invalidateQueries({ queryKey: ['versions', project.id] })
    qc.invalidateQueries({ queryKey: ['project', project.id] })
  }

  if (!isLoading && !data?.total && !runId) {
    return <Empty icon={<History size={22} />} title="No rendered versions yet" action={<button className="btn-primary" onClick={goExport}><Film size={15} /> Render the first version</button>}>
      Every render is kept here as a numbered version with its settings, so you can compare and download any of them.
    </Empty>
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold">Version history</h3>
          <p className="text-sm text-muted">{data?.total ?? 0} rendered version{data?.total === 1 ? '' : 's'}, newest first</p>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto">
          <select className="input w-full py-2 sm:w-64" value={runId} onChange={(e) => { setRunId(e.target.value); setPage(1) }} aria-label="Filter by cut">
            <option value="">All cuts</option>
            {(data?.cuts || []).map((c) => <option key={c.run_id} value={c.run_id}>{cutName(c.run_id)} ({c.count})</option>)}
          </select>
          <button className="btn-primary w-full sm:w-auto" onClick={goExport}><Film size={15} /> New render</button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="card aspect-[4/3] animate-pulse bg-stone-100" />)}</div>
      ) : groups.map((g) => (
        <section key={g.label}>
          <p className="label mb-2 flex items-center gap-2"><span>{g.label}</span><span className="h-px flex-1 bg-line" /></p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {g.items.map((v) => <VersionCard key={v.id} v={v} latest={v.id === newestId} onPlay={() => setPlaying(v)} onDelete={() => remove(v)} />)}
          </div>
        </section>
      ))}

      {data && <Pagination page={data.page} pages={data.pages} total={data.total} label="versions" onChange={setPage} />}
      {playing && <Player v={playing} onClose={() => setPlaying(null)} />}
    </div>
  )
}
