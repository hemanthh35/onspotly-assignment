import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { Film, FileJson, FileSpreadsheet, FileCode2, Clapperboard, Music, Loader2, Download, ScrollText } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { api, exportUrl, fmtBytes, pickRun, runFileUrl } from '../../api.js'
import { Empty, JobCard, Segmented } from '../ui.jsx'

const FILES = [
  { kind: 'json', label: 'Clip list (JSON)', icon: FileJson, hint: 'Timestamps for every clip' },
  { kind: 'csv', label: 'Clip list (CSV)', icon: FileSpreadsheet, hint: 'Open in Excel / Sheets' },
  { kind: 'edl', label: 'EDL (CMX3600)', icon: Clapperboard, hint: 'Premiere · DaVinci Resolve' },
  { kind: 'fcpxml', label: 'FCPXML', icon: FileCode2, hint: 'Final Cut · Resolve' },
  { kind: 'results', label: 'Shot-finder results', icon: ScrollText, hint: 'Confidence, quality, alternatives' },
]

export default function ExportStep({ project, refresh, goEditor }) {
  const [params] = useSearchParams()
  const run = pickRun(project.runs, params.get('run'))
  const sl = project.shot_lists.find((s) => s.id === run?.shot_list_id)
  const [aspect, setAspect] = useState(project.aspect_ratio)
  const [crossfade, setCrossfade] = useState(0)
  const [title, setTitle] = useState('')
  const [musicId, setMusicId] = useState('')
  const [volume, setVolume] = useState(0.5)
  const [uploading, setUploading] = useState(false)
  const musicRef = useRef(null)
  const music = project.assets.filter((a) => a.kind === 'music')
  const renderJob = project.jobs.find((j) => j.kind === 'render')
  const rendering = renderJob && ['queued', 'running'].includes(renderJob.status)
  const videos = project.exports.filter((e) => e.kind === 'mp4')

  if (!run) return <Empty icon={<Film size={22} />} title="Nothing to export yet" action={<button className="btn-primary" onClick={goEditor}>Open editor</button>}>Find the shots first, then come back to download.</Empty>

  async function render() {
    try {
      await api.render(run.id, { aspect, crossfade, title, music_asset_id: musicId || null, music_volume: volume })
      toast.success('Rendering started')
      refresh()
    } catch (e) { toast.error(e.message) }
  }

  async function uploadMusic(file) {
    setUploading(true)
    try {
      const a = await api.uploadMusic(project.id, file)
      setMusicId(a.id)
      refresh()
    } catch (e) { toast.error(e.message) }
    setUploading(false)
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="card space-y-5 p-5">
        <div>
          <h3 className="text-lg font-bold">Download edited video</h3>
          <p className="text-sm text-muted">Joins the clips of your current cut, in order, into one MP4.</p>
          <p className="mt-1 text-xs text-muted">Cut: <b className="text-ink">{sl?.name || 'Shot list'}</b> · {run.approach} · {run.timeline.length} clips · {run.timeline.reduce((s, c) => s + c.end - c.start, 0).toFixed(1)}s</p>
        </div>
        <div>
          <span className="label">Format</span>
          <Segmented value={aspect} onChange={setAspect} options={[{ value: '9:16', label: '9:16 Reel' }, { value: '16:9', label: '16:9' }, { value: '1:1', label: '1:1' }, { value: '4:5', label: '4:5' }]} />
        </div>
        <div>
          <span className="label">Transitions</span>
          <Segmented value={crossfade} onChange={setCrossfade} options={[{ value: 0, label: 'Hard cuts' }, { value: 0.3, label: 'Quick fade' }, { value: 0.6, label: 'Soft fade' }]} />
        </div>
        <div>
          <label className="label" htmlFor="title">End title (optional)</label>
          <input id="title" className="input" placeholder="e.g. Bean & Bloom · Now open" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={60} />
        </div>
        <div>
          <span className="label">Background music (optional)</span>
          <div className="flex flex-wrap items-center gap-2">
            <select className="input w-auto flex-1 py-2" value={musicId} onChange={(e) => setMusicId(e.target.value)}>
              <option value="">Original sound only</option>
              {music.map((m) => <option key={m.id} value={m.id}>{m.filename.replace(/^_music_/, '')}</option>)}
            </select>
            <button className="btn-ghost" onClick={() => musicRef.current?.click()} disabled={uploading}>
              {uploading ? <Loader2 size={15} className="animate-spin" /> : <Music size={15} />} Upload
            </button>
            <input ref={musicRef} type="file" accept="audio/*" className="hidden" onChange={(e) => { e.target.files[0] && uploadMusic(e.target.files[0]); e.target.value = '' }} />
          </div>
          {musicId && (
            <label className="mt-3 flex items-center gap-3 text-xs text-muted">
              Music volume <input type="range" min={0.1} max={1} step={0.05} value={volume} onChange={(e) => setVolume(Number(e.target.value))} className="flex-1 accent-brand" />
            </label>
          )}
          {musicId && <p className="mt-1 text-xs text-muted">Original sound is lowered under the music, except shots that need their audio (e.g. the welcome line).</p>}
        </div>
        <button className="btn-primary w-full py-3" onClick={render} disabled={rendering}>
          {rendering ? <><Loader2 size={16} className="animate-spin" /> Rendering…</> : <><Film size={16} /> Render video</>}
        </button>
        {renderJob && <JobCard job={renderJob} />}
      </section>

      <section className="space-y-6">
        <div className="card p-5">
          <h3 className="text-lg font-bold">Download for editor</h3>
          <p className="text-sm text-muted">Everything a human editor needs to rebuild or fine-tune the cut.</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {FILES.map(({ kind, label, icon: Icon, hint }) => (
              <a key={kind} href={runFileUrl(run.id, kind)} className="flex items-center gap-3 rounded-xl border border-line p-3 transition hover:border-ink/30 hover:bg-stone-50">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-ink text-white"><Icon size={16} /></span>
                <span className="min-w-0"><span className="block text-sm font-semibold">{label}</span><span className="block truncate text-xs text-muted">{hint}</span></span>
              </a>
            ))}
          </div>
        </div>

        {videos.length > 0 && (
          <div className="space-y-3">
            <h3 className="text-lg font-bold">Rendered videos</h3>
            {videos.map((v) => (
              <div key={v.id} className="card overflow-hidden">
                <video src={exportUrl(v.id, true)} controls playsInline preload="metadata"
                  className={v.options?.aspect === '9:16' ? 'mx-auto max-h-[70vh] bg-ink' : 'w-full bg-ink'} />
                <div className="flex items-center justify-between gap-3 p-3">
                  <div className="min-w-0 text-xs text-muted">
                    <p className="truncate font-semibold text-ink">{v.filename}</p>
                    <p>{v.options?.duration?.toFixed?.(1)}s · {v.options?.aspect} · {fmtBytes(v.size_bytes)} · {new Date(v.created_at).toLocaleString()}</p>
                  </div>
                  <a href={exportUrl(v.id)} className="btn-dark btn-sm shrink-0"><Download size={13} /> MP4</a>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
