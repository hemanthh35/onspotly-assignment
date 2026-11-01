import { useCallback, useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { UploadCloud, Loader2, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'

export function StatusChip({ status }) {
  const map = {
    created: ['bg-stone-100 text-stone-600', 'New'],
    analyzing: ['bg-amber-50 text-amber-700', 'Analysing'],
    ready: ['bg-sky-50 text-sky-700', 'Ready'],
    finding: ['bg-amber-50 text-amber-700', 'Finding shots'],
    review: ['bg-emerald-50 text-emerald-700', 'In review'],
    done: ['bg-emerald-50 text-emerald-700', 'Done'],
    running: ['bg-amber-50 text-amber-700', 'Running'],
    queued: ['bg-stone-100 text-stone-600', 'Queued'],
    failed: ['bg-brand-soft text-brand', 'Failed'],
    pending: ['bg-stone-100 text-stone-600', 'Pending'],
    skip: ['bg-stone-100 text-stone-600', 'Audio'],
  }
  const [cls, label] = map[status] || ['bg-stone-100 text-stone-600', status]
  return <span className={clsx('chip', cls)}>{label}</span>
}

export function ScoreBar({ label, value, invert = false }) {
  const v = Math.max(0, Math.min(1, value ?? 0))
  const color = v >= 0.7 ? 'bg-emerald-500' : v >= 0.45 ? 'bg-amber-500' : 'bg-brand'
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between text-[11px] font-medium text-muted">
        <span>{label}</span>
        <span className="tabular-nums text-ink">{Math.round(v * 100)}</span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-stone-100">
        <div className={clsx('h-full rounded-full transition-all', invert ? 'bg-ink' : color)} style={{ width: `${v * 100}%` }} />
      </div>
    </div>
  )
}

export function Progress({ value, className }) {
  return (
    <div className={clsx('h-2 overflow-hidden rounded-full bg-stone-100', className)}>
      <div className="h-full rounded-full bg-brand transition-all duration-500" style={{ width: `${Math.round((value || 0) * 100)}%` }} />
    </div>
  )
}

const KIND = { analyze: 'Analysing footage', find: 'Finding shots', render: 'Rendering video' }

export function JobCard({ job }) {
  const icon = job.status === 'done' ? <CheckCircle2 size={16} className="text-ok" />
    : job.status === 'failed' ? <AlertTriangle size={16} className="text-brand" />
      : job.status === 'queued' ? <Clock size={16} className="text-muted" />
        : <Loader2 size={16} className="animate-spin text-brand" />
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2.5">
        {icon}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-sm font-semibold">{KIND[job.kind] || job.kind}</p>
            <span className="text-xs tabular-nums text-muted">{Math.round(job.progress * 100)}%</span>
          </div>
          <p className="truncate text-xs text-muted">{job.status === 'failed' ? job.error || job.message : job.message}</p>
        </div>
      </div>
      {['running', 'queued'].includes(job.status) && <Progress value={job.progress} className="mt-3" />}
    </div>
  )
}

export function Dropzone({ onFiles, accept = 'video/*,.zip', multiple = true, children, compact = false }) {
  const [over, setOver] = useState(false)
  const input = useRef(null)
  const handle = useCallback((list) => {
    const files = Array.from(list || [])
    if (files.length) onFiles(files)
  }, [onFiles])
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); handle(e.dataTransfer.files) }}
      onClick={() => input.current?.click()}
      className={clsx('group cursor-pointer rounded-2xl border-2 border-dashed text-center transition',
        compact ? 'p-5' : 'p-8 sm:p-10',
        over ? 'border-brand bg-brand-soft' : 'border-line bg-white hover:border-ink/30')}
    >
      <input ref={input} type="file" className="hidden" accept={accept} multiple={multiple}
        onChange={(e) => { handle(e.target.files); e.target.value = '' }} />
      {children || (
        <>
          <span className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-ink text-white transition group-hover:bg-brand">
            <UploadCloud size={22} />
          </span>
          <p className="mt-3 font-semibold">Drop videos or a .zip here</p>
          <p className="mt-1 text-sm text-muted">MP4, MOV, MKV or a zip of them · or tap to browse</p>
        </>
      )}
    </div>
  )
}

export function Empty({ icon, title, children, action }) {
  return (
    <div className="card flex flex-col items-center px-6 py-14 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-stone-100 text-muted">{icon}</span>
      <p className="mt-4 font-display text-lg font-semibold">{title}</p>
      <div className="mt-1 max-w-md text-sm text-muted">{children}</div>
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/** Plays only [start, end] of a source video, looping back to start. */
export function ClipPlayer({ src, poster, start, end, className, autoPlay = false }) {
  const ref = useRef(null)
  const [playing, setPlaying] = useState(false)
  useEffect(() => {
    const v = ref.current
    if (!v) return
    const seek = () => { try { v.currentTime = start } catch { /* not ready */ } }
    v.readyState >= 1 ? seek() : v.addEventListener('loadedmetadata', seek, { once: true })
  }, [start, src])
  return (
    <div className={clsx('relative overflow-hidden rounded-xl bg-ink', className)}>
      <video
        ref={ref} src={`${src}#t=${start.toFixed(2)}`} poster={poster} playsInline preload="metadata" autoPlay={autoPlay}
        muted={false} className="h-full w-full object-cover"
        onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
        onTimeUpdate={(e) => {
          if (e.currentTime >= end || e.currentTarget.currentTime >= end) {
            e.currentTarget.pause()
            e.currentTarget.currentTime = start
          }
        }}
        onClick={(e) => (e.currentTarget.paused ? e.currentTarget.play() : e.currentTarget.pause())}
      />
      {!playing && (
        <button type="button" onClick={() => ref.current?.play()}
          className="absolute inset-0 grid place-items-center bg-gradient-to-t from-black/40 to-transparent">
          <span className="grid h-11 w-11 place-items-center rounded-full bg-white/95 shadow-lg">
            <svg viewBox="0 0 16 16" className="ml-0.5 h-4 w-4 fill-ink"><path d="M4 2.5v11l9-5.5z" /></svg>
          </span>
        </button>
      )}
    </div>
  )
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-white p-1">
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)}
          className={clsx('rounded-lg px-3 py-1.5 text-xs font-semibold transition',
            value === o.value ? 'bg-ink text-white' : 'text-muted hover:text-ink')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
