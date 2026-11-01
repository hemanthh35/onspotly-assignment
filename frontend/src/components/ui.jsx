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

/** Numbered pagination with prev/next; collapses long ranges with ellipses. */
export function Pagination({ page, pages, total, onChange, label = 'items' }) {
  if (pages <= 1) return total ? <p className="text-center text-xs text-muted">{total} {label}</p> : null
  const nums = []
  for (let p = 1; p <= pages; p++) {
    if (p === 1 || p === pages || Math.abs(p - page) <= 1) nums.push(p)
    else if (nums.at(-1) !== '…') nums.push('…')
  }
  const btn = 'grid h-9 min-w-9 place-items-center rounded-lg px-2 text-sm font-semibold transition disabled:opacity-40'
  return (
    <nav className="flex flex-col items-center gap-2 sm:flex-row sm:justify-between" aria-label="Pagination">
      <p className="text-xs text-muted">Page {page} of {pages} · {total} {label}</p>
      <div className="flex items-center gap-1">
        <button className={clsx(btn, 'border border-line bg-white hover:border-ink/30')} disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page">‹</button>
        {nums.map((n, i) => n === '…'
          ? <span key={`e${i}`} className="px-1 text-muted">…</span>
          : <button key={n} onClick={() => onChange(n)} aria-current={n === page ? 'page' : undefined}
              className={clsx(btn, n === page ? 'bg-ink text-white' : 'border border-line bg-white hover:border-ink/30')}>{n}</button>)}
        <button className={clsx(btn, 'border border-line bg-white hover:border-ink/30')} disabled={page >= pages} onClick={() => onChange(page + 1)} aria-label="Next page">›</button>
      </div>
    </nav>
  )
}

const round1 = (v) => Math.round(v * 10) / 10

export function Trim({ label, value, onChange, min, max }) {
  return (
    <div>
      <span className="label mb-1">{label}</span>
      <div className="flex items-center rounded-xl border border-line bg-white">
        <button type="button" aria-label={`${label} earlier`} className="grid h-9 w-9 place-items-center text-muted hover:text-ink" onClick={() => onChange(Math.max(min, round1(value - 0.5)))}>−</button>
        <input type="number" step={0.1} className="w-full min-w-0 bg-transparent text-center text-sm tabular-nums outline-none" value={value}
          onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value))))} />
        <button type="button" aria-label={`${label} later`} className="grid h-9 w-9 place-items-center text-muted hover:text-ink" onClick={() => onChange(Math.min(max, round1(value + 0.5)))}>+</button>
      </div>
    </div>
  )
}

export function Slider({ label, value, onChange, min = 0, max = 1, step = 0.05, fmt = (v) => `${Math.round(v * 100)}%`, disabled }) {
  return (
    <label className={clsx('block', disabled && 'opacity-50')}>
      <span className="flex items-center justify-between text-xs font-semibold text-muted"><span>{label}</span><span className="tabular-nums text-ink">{fmt(value)}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))} className="mt-1.5 w-full accent-brand" />
    </label>
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
