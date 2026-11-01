import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Film, FileJson, FileSpreadsheet, FileCode2, Clapperboard, ScrollText, Download, Check, Loader2, X, History, Music, Type, Scissors, Upload } from 'lucide-react'
import clsx from 'clsx'
import { api, exportUrl, fmtBytes, pickRun, runFileUrl } from '../../api.js'
import { Empty, Segmented, Slider } from '../ui.jsx'
import { DEFAULT_MIX } from './TimelinePanel.jsx'

const FILES = [
  { kind: 'json', label: 'Clip list (JSON)', icon: FileJson, hint: 'Timestamps for every clip' },
  { kind: 'csv', label: 'Clip list (CSV)', icon: FileSpreadsheet, hint: 'Open in Excel / Sheets' },
  { kind: 'edl', label: 'EDL (CMX3600)', icon: Clapperboard, hint: 'Premiere · DaVinci Resolve' },
  { kind: 'fcpxml', label: 'FCPXML', icon: FileCode2, hint: 'Final Cut · Resolve' },
  { kind: 'results', label: 'Shot-finder results', icon: ScrollText, hint: 'Confidence, quality, alternatives' },
]

// Render stages, matched against the job's progress messages.
const STAGES = [
  { key: 'queue', label: 'Queued', test: (m) => /queued|starting/i.test(m) },
  { key: 'cut', label: 'Cutting clips', test: (m) => /cutting|fetch/i.test(m) },
  { key: 'join', label: 'Joining & transitions', test: (m) => /joining/i.test(m) },
  { key: 'finish', label: 'Music, title & encoding', test: (m) => /finishing/i.test(m) },
  { key: 'save', label: 'Saving the video', test: (m) => /saving|complete|done/i.test(m) },
]

function stageIndex(job) {
  if (job.status === 'done') return STAGES.length
  const i = STAGES.findIndex((s) => s.test(job.message || ''))
  return i < 0 ? 0 : i
}

function useElapsed(running, since) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(t)
  }, [running])
  return since ? Math.max(0, (now - new Date(since).getTime()) / 1000) : 0
}

/** Full-screen render screen: stages, progress, elapsed time, then the finished video. */
function RenderOverlay({ job, latest, onClose, onVersions }) {
  const running = ['queued', 'running'].includes(job.status)
  const elapsed = useElapsed(running, job.created_at)
  const idx = stageIndex(job)
  const pct = job.status === 'done' ? 100 : Math.round((job.progress || 0) * 100)
  const eta = running && job.progress > 0.08 ? Math.max(0, elapsed / job.progress - elapsed) : null
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink/80 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Rendering video">
      <div className="w-full max-w-lg overflow-hidden rounded-3xl bg-white shadow-2xl">
        {job.status === 'done' && latest ? (
          <>
            <video src={exportUrl(latest.id, true)} controls autoPlay playsInline
              className={clsx('w-full bg-ink', latest.options?.aspect === '9:16' && 'mx-auto max-h-[55vh] w-auto')} />
            <div className="space-y-4 p-5">
              <div className="flex items-center gap-2"><span className="grid h-7 w-7 place-items-center rounded-full bg-emerald-500 text-white"><Check size={15} /></span>
                <p className="font-display text-lg font-bold">Version {latest.options?.version} is ready</p></div>
              <p className="break-all text-xs text-muted">{latest.filename} · {latest.options?.duration?.toFixed?.(1)}s · {fmtBytes(latest.size_bytes)} · rendered in {Math.round(job.wall_seconds || elapsed)}s</p>
              <div className="flex flex-wrap gap-2">
                <a href={exportUrl(latest.id)} className="btn-primary flex-1"><Download size={15} /> Download MP4</a>
                <button className="btn-ghost flex-1" onClick={onVersions}><History size={15} /> All versions</button>
              </div>
              <button className="w-full text-center text-xs font-semibold text-muted hover:text-ink" onClick={onClose}>Close</button>
            </div>
          </>
        ) : job.status === 'failed' ? (
          <div className="space-y-4 p-6">
            <p className="font-display text-lg font-bold text-brand">Render failed</p>
            <p className="break-words rounded-xl bg-brand-soft p-3 text-xs text-ink/80">{job.error || job.message}</p>
            <button className="btn-dark w-full" onClick={onClose}>Close</button>
          </div>
        ) : (
          <div className="p-6">
            <div className="flex items-start justify-between">
              <div>
                <p className="label mb-1">Rendering</p>
                <p className="font-display text-2xl font-bold">Building your video…</p>
              </div>
              <button onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-stone-100" aria-label="Hide (keeps rendering)"><X size={16} /></button>
            </div>
            <div className="mt-6 flex items-end justify-between">
              <span className="font-display text-5xl font-bold tabular-nums">{pct}<span className="text-2xl text-muted">%</span></span>
              <span className="text-right text-xs text-muted tabular-nums">{Math.floor(elapsed)}s elapsed{eta != null && <><br />~{Math.ceil(eta)}s left</>}</span>
            </div>
            <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-stone-100">
              <div className="relative h-full rounded-full bg-brand transition-all duration-700" style={{ width: `${Math.max(pct, 3)}%` }}>
                <div className="absolute inset-0 animate-pulse bg-white/25" />
              </div>
            </div>
            <ol className="mt-6 space-y-2.5">
              {STAGES.map((s, i) => (
                <li key={s.key} className="flex items-center gap-3 text-sm">
                  <span className={clsx('grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold',
                    i < idx ? 'bg-emerald-500 text-white' : i === idx ? 'bg-brand text-white' : 'bg-stone-100 text-muted')}>
                    {i < idx ? <Check size={12} /> : i === idx ? <Loader2 size={12} className="animate-spin" /> : i + 1}
                  </span>
                  <span className={clsx(i === idx ? 'font-semibold text-ink' : i < idx ? 'text-ink/70' : 'text-muted')}>{s.label}</span>
                  {i === idx && <span className="ml-auto truncate text-xs text-muted">{job.message}</span>}
                </li>
              ))}
            </ol>
            <p className="mt-6 text-center text-xs text-muted">You can close this. Rendering continues in the background.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ExportStep({ project, refresh, goEditor, goVersions }) {
  const [params] = useSearchParams()
  const run = pickRun(project.runs, params.get('run'))
  const sl = project.shot_lists.find((s) => s.id === run?.shot_list_id)
  const saved = { ...DEFAULT_MIX, ...(run?.results?.mix || {}) }
  const [aspect, setAspect] = useState(project.aspect_ratio)
  const [opts, setOpts] = useState(saved)
  const [jobId, setJobId] = useState(null)
  const [overlay, setOverlay] = useState(false)
  const [uploading, setUploading] = useState(false)
  const musicRef = useRef(null)
  useEffect(() => { setOpts({ ...DEFAULT_MIX, ...(run?.results?.mix || {}) }) }, [run?.id, run?.updated_at]) // eslint-disable-line

  const music = project.assets.filter((a) => a.kind === 'music')
  const renderJob = project.jobs.find((j) => j.id === jobId) || project.jobs.find((j) => j.kind === 'render' && ['queued', 'running'].includes(j.status))
  const rendering = renderJob && ['queued', 'running'].includes(renderJob.status)
  const latest = project.latest_versions?.[0]
  const set = (patch) => setOpts((o) => ({ ...o, ...patch }))

  if (!run) return <Empty icon={<Film size={22} />} title="Nothing to export yet" action={<button className="btn-primary" onClick={goEditor}>Open editor</button>}>Find the shots first, then come back to download.</Empty>

  const total = run.timeline.reduce((s, c) => s + c.end - c.start, 0)

  async function render() {
    try {
      const { job_id } = await api.render(run.id, { aspect, ...opts })
      setJobId(job_id)
      setOverlay(true)
      refresh()
    } catch (e) { toast.error(e.message) }
  }

  async function uploadMusic(file) {
    setUploading(true)
    try { const a = await api.uploadMusic(project.id, file); set({ music_asset_id: a.id }); refresh() } catch (e) { toast.error(e.message) }
    setUploading(false)
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="card space-y-5 p-5">
        <div>
          <h3 className="text-lg font-bold">Download edited video</h3>
          <p className="text-sm text-muted">Renders your current cut, in order, as one MP4. Settings come from the editor’s mix.</p>
          <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
            <span className="chip bg-stone-100 text-ink"><Scissors size={11} /> {sl?.name || 'Cut'} · {run.timeline.length} clips · {total.toFixed(1)}s</span>
            {opts.music_asset_id && <span className="chip bg-sky-50 text-sky-700"><Music size={11} /> music</span>}
            {opts.title && <span className="chip bg-brand-soft text-brand"><Type size={11} /> title</span>}
          </div>
        </div>
        <div>
          <span className="label">Format</span>
          <Segmented value={aspect} onChange={setAspect} options={[{ value: '9:16', label: '9:16 Reel' }, { value: '16:9', label: '16:9' }, { value: '1:1', label: '1:1' }, { value: '4:5', label: '4:5' }]} />
        </div>
        <div>
          <span className="label">Transitions</span>
          <Segmented value={opts.crossfade} onChange={(v) => set({ crossfade: v })} options={[{ value: 0, label: 'Hard cuts' }, { value: 0.3, label: 'Quick fade' }, { value: 0.6, label: 'Soft fade' }]} />
        </div>
        <div>
          <label className="label" htmlFor="title">End title</label>
          <input id="title" className="input" placeholder="e.g. Bean & Bloom · Now open" value={opts.title} onChange={(e) => set({ title: e.target.value })} maxLength={60} />
        </div>
        <div className="space-y-3">
          <span className="label">Background music</span>
          <div className="flex flex-wrap items-center gap-2">
            <select className="input w-auto flex-1 py-2" value={opts.music_asset_id || ''} onChange={(e) => set({ music_asset_id: e.target.value || null })}>
              <option value="">Original sound only</option>
              {music.map((m) => <option key={m.id} value={m.id}>{m.filename.replace(/^_music_/, '')}</option>)}
            </select>
            <button className="btn-ghost" onClick={() => musicRef.current?.click()} disabled={uploading}>
              {uploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} Upload
            </button>
            <input ref={musicRef} type="file" accept="audio/*" className="hidden" onChange={(e) => { e.target.files[0] && uploadMusic(e.target.files[0]); e.target.value = '' }} />
          </div>
          {opts.music_asset_id && (
            <>
              <Slider label="Music volume" value={opts.music_volume} max={1.5} onChange={(v) => set({ music_volume: v })} />
              <label className="flex items-center gap-2 text-xs text-muted">
                <input type="checkbox" className="accent-brand" checked={opts.duck} onChange={(e) => set({ duck: e.target.checked })} /> Duck music under dialogue
              </label>
            </>
          )}
        </div>
        <button className="btn-primary w-full py-3" onClick={render} disabled={rendering}>
          {rendering ? <><Loader2 size={16} className="animate-spin" /> Rendering… {Math.round(renderJob.progress * 100)}%</> : <><Film size={16} /> Render video</>}
        </button>
        {rendering && !overlay && <button className="w-full text-xs font-semibold text-brand" onClick={() => setOverlay(true)}>Show progress</button>}
      </section>

      <section className="space-y-6">
        <div className="card p-5">
          <h3 className="text-lg font-bold">Download for editor</h3>
          <p className="text-sm text-muted">Everything a human editor needs to rebuild or fine-tune this cut.</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {FILES.map(({ kind, label, icon: Icon, hint }) => (
              <a key={kind} href={runFileUrl(run.id, kind)} className="flex items-center gap-3 rounded-xl border border-line p-3 transition hover:border-ink/30 hover:bg-stone-50">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ink text-white"><Icon size={16} /></span>
                <span className="min-w-0"><span className="block text-sm font-semibold">{label}</span><span className="block truncate text-xs text-muted">{hint}</span></span>
              </a>
            ))}
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold">Rendered versions</h3>
            <span className="chip bg-stone-100 text-muted">{project.version_count}</span>
          </div>
          {latest ? (
            <div className="mt-3 flex items-center gap-3 rounded-xl border border-line p-3">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-ink font-display text-sm font-bold text-white">v{latest.options?.version}</span>
              <div className="min-w-0 flex-1 text-xs">
                <p className="truncate font-semibold text-ink">{latest.filename}</p>
                <p className="text-muted">{latest.options?.aspect} · {latest.options?.duration?.toFixed?.(1)}s · {new Date(latest.created_at).toLocaleString()}</p>
              </div>
              <a href={exportUrl(latest.id)} className="btn-dark btn-sm shrink-0" aria-label="Download latest"><Download size={13} /></a>
            </div>
          ) : <p className="mt-2 text-sm text-muted">No renders yet.</p>}
          <button className="btn-ghost mt-3 w-full" onClick={goVersions}><History size={15} /> Open version history</button>
        </div>
      </section>

      {overlay && renderJob && (
        <RenderOverlay job={renderJob} latest={renderJob.status === 'done' ? latest : null}
          onClose={() => setOverlay(false)} onVersions={() => { setOverlay(false); goVersions() }} />
      )}
    </div>
  )
}
