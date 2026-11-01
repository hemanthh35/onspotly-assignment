import { useState } from 'react'
import { toast } from 'sonner'
import { ArrowRight, Mic, Trash2, Film, RefreshCw } from 'lucide-react'
import clsx from 'clsx'
import { api, fmtBytes, fmtTime, thumbUrl } from '../../api.js'
import { Dropzone, Empty, JobCard, Progress, StatusChip } from '../ui.jsx'

function SceneStrip({ asset }) {
  if (!asset.scenes?.length || !asset.duration) return null
  return (
    <div>
      <div className="flex h-7 gap-px overflow-hidden rounded-md">
        {asset.scenes.map((s) => {
          const q = s.overall
          return (
            <div key={s.start} title={`${fmtTime(s.start)}–${fmtTime(s.end)} · quality ${Math.round(q * 100)} (sharp ${Math.round(s.sharpness * 100)}, light ${Math.round(s.brightness * 100)}, steady ${Math.round(s.stability * 100)})`}
              style={{ width: `${((s.end - s.start) / asset.duration) * 100}%` }}
              className={clsx('min-w-[3px]', q >= 0.75 ? 'bg-emerald-500/80' : q >= 0.5 ? 'bg-amber-400/90' : 'bg-brand/80')} />
          )
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted"><span>0s</span><span>{asset.scenes.length} scenes · colour = take quality</span><span>{fmtTime(asset.duration)}</span></div>
    </div>
  )
}

export default function FootageStep({ project, refresh, next }) {
  const [uploading, setUploading] = useState(null)
  const videos = project.assets.filter((a) => a.kind === 'video')
  const jobs = project.jobs.filter((j) => j.kind === 'analyze').slice(0, 3)
  const active = jobs.filter((j) => ['queued', 'running'].includes(j.status))
  const allDone = videos.length > 0 && videos.every((a) => a.analysis_status === 'done')

  async function onFiles(files) {
    setUploading(0)
    try {
      const r = await api.uploadFootage(project.id, files, setUploading)
      toast.success(`Uploaded ${r.assets.length} file(s), analysis started`)
      if (r.skipped?.length) toast.message(`Skipped: ${r.skipped.join(', ')}`)
      refresh()
    } catch (e) { toast.error(e.message) }
    setUploading(null)
  }

  async function del(a) {
    if (!confirm(`Remove ${a.filename}?`)) return
    await api.deleteAsset(a.id)
    refresh()
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        {videos.length === 0 ? (
          <Empty icon={<Film size={22} />} title="No footage yet">Upload the creator’s videos — individual files or one zip.</Empty>
        ) : videos.map((a) => (
          <div key={a.id} className="card overflow-hidden">
            <div className="flex flex-col sm:flex-row">
              <div className="aspect-video w-full shrink-0 bg-ink sm:w-56">
                {a.duration > 0 && <img src={thumbUrl(a.id, a.duration / 3)} alt="" className="h-full w-full object-cover" loading="lazy" />}
              </div>
              <div className="min-w-0 flex-1 space-y-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{a.filename}</p>
                    <p className="text-xs text-muted">{fmtTime(a.duration)} · {a.width}×{a.height} · {a.fps} fps · {fmtBytes(a.size_bytes)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <StatusChip status={a.analysis_status} />
                    <button onClick={() => del(a)} aria-label={`Remove ${a.filename}`} className="rounded-lg p-1.5 text-muted hover:bg-stone-100 hover:text-brand"><Trash2 size={14} /></button>
                  </div>
                </div>
                <SceneStrip asset={a} />
                {a.transcript?.length > 0 && (
                  <div className="rounded-xl bg-stone-50 p-3 text-xs">
                    <p className="mb-1 flex items-center gap-1 font-semibold text-muted"><Mic size={12} /> Speech detected</p>
                    {a.transcript.slice(0, 3).map((s) => (
                      <p key={s.start} className="truncate"><span className="tabular-nums text-muted">{fmtTime(s.start)}</span> “{s.text}”</p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      <aside className="space-y-4 lg:sticky lg:top-32 lg:self-start">
        <Dropzone onFiles={onFiles} compact>
          <p className="font-semibold">Add more footage</p>
          <p className="mt-1 text-xs text-muted">Videos or a .zip</p>
        </Dropzone>
        {uploading !== null && <div className="card p-4"><p className="mb-2 text-sm font-semibold">Uploading… {Math.round(uploading * 100)}%</p><Progress value={uploading} /></div>}
        {jobs.map((j) => <JobCard key={j.id} job={j} />)}
        {videos.length > 0 && !active.length && !allDone && (
          <button className="btn-ghost w-full" onClick={async () => { await api.reanalyze(project.id); refresh() }}>
            <RefreshCw size={15} /> Re-run analysis
          </button>
        )}
        <div className="card p-4 text-sm">
          <p className="font-semibold">What the analysis does</p>
          <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-muted">
            <li>• Splits each video into scenes so clips never cross a cut</li>
            <li>• Scores every take for sharpness, light and camera shake</li>
            <li>• Indexes frames with CLIP so shots can be found by description</li>
            <li>• Transcribes speech with Whisper to find spoken moments</li>
          </ul>
        </div>
        <button className="btn-dark w-full" onClick={next} disabled={!videos.length}>Plan the shots <ArrowRight size={15} /></button>
      </aside>
    </div>
  )
}
