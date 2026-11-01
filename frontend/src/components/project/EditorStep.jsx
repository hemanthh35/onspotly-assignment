import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { DndContext, closestCenter, PointerSensor, TouchSensor, KeyboardSensor, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Save, ArrowRight, AlertTriangle, Replace, Minus, Plus, X, Mic, ScanSearch, Undo2, Scaling } from 'lucide-react'
import clsx from 'clsx'
import { useSearchParams } from 'react-router-dom'
import { api, fmtTime, pickRun, streamUrl, thumbUrl } from '../../api.js'
import { ClipPlayer, Empty, ScoreBar, Segmented } from '../ui.jsx'
import TimelinePanel, { DEFAULT_MIX } from './TimelinePanel.jsx'

const round = (v) => Math.round(v * 10) / 10

function Confidence({ value }) {
  const v = value ?? 0
  const cls = v >= 0.7 ? 'bg-emerald-50 text-emerald-700' : v >= 0.45 ? 'bg-amber-50 text-amber-700' : 'bg-brand-soft text-brand'
  return <span className={clsx('chip', cls)}>{Math.round(v * 100)}% match</span>
}

function Trim({ label, value, onChange, min, max }) {
  return (
    <div>
      <span className="label mb-1">{label}</span>
      <div className="flex items-center rounded-xl border border-line bg-white">
        <button type="button" aria-label={`${label} earlier`} className="grid h-9 w-9 place-items-center text-muted hover:text-ink" onClick={() => onChange(Math.max(min, round(value - 0.5)))}><Minus size={14} /></button>
        <input type="number" step={0.1} className="w-full min-w-0 bg-transparent text-center text-sm tabular-nums outline-none" value={value}
          onChange={(e) => onChange(Math.min(max, Math.max(min, Number(e.target.value))))} />
        <button type="button" aria-label={`${label} later`} className="grid h-9 w-9 place-items-center text-muted hover:text-ink" onClick={() => onChange(Math.min(max, round(value + 0.5)))}><Plus size={14} /></button>
      </div>
    </div>
  )
}

function ClipCard({ item, index, result, shot, assets, onChange, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.shot_id })
  const [showAlts, setShowAlts] = useState(false)
  const asset = assets[item.file]
  const best = result?.best
  const dur = item.end - item.start
  const changed = best && (best.file !== item.file || Math.abs(best.start - item.start) > 0.05 || Math.abs(best.end - item.end) > 0.05)
  const options = [best, ...(result?.alternatives || [])].filter(Boolean)

  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}
      className={clsx('card overflow-hidden', isDragging && 'relative z-10 shadow-2xl ring-2 ring-brand')}>
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5 sm:px-4">
        <button {...attributes} {...listeners} aria-label="Drag to reorder" className="grid h-8 w-7 cursor-grab touch-none place-items-center rounded text-muted hover:bg-stone-100 active:cursor-grabbing">
          <GripVertical size={16} />
        </button>
        <span className="chip bg-ink text-white">{index + 1}</span>
        <p className="min-w-0 flex-1 truncate font-semibold">{item.name || shot?.name}</p>
        <span className="hidden text-xs text-muted sm:inline">{item.shot_id}</span>
        <button onClick={onRemove} aria-label="Remove from cut" className="grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-stone-100 hover:text-brand"><X size={15} /></button>
      </div>
      <div className="grid gap-4 p-3 sm:grid-cols-[minmax(0,260px)_1fr] sm:p-4">
        {asset ? (
          <ClipPlayer src={streamUrl(asset.id)} poster={thumbUrl(asset.id, item.start + dur / 2)} start={item.start} end={item.end} className="aspect-video" />
        ) : <div className="grid aspect-video place-items-center rounded-xl bg-stone-100 text-xs text-muted">File not found</div>}
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {best && !changed && <Confidence value={best.confidence} />}
            {changed && <span className="chip bg-sky-50 text-sky-700">Edited</span>}
            {item.needs_audio && <span className="chip bg-brand-soft text-brand"><Mic size={11} /> audio</span>}
            <span className="truncate text-xs text-muted">{item.file} · {fmtTime(item.start)}–{fmtTime(item.end)} · <b className="text-ink">{dur.toFixed(1)}s</b></span>
          </div>
          {best && !changed && <p className="text-sm leading-relaxed text-ink/80">{best.reason}</p>}
          {best?.quality && !changed && (
            <div className="grid grid-cols-3 gap-3">
              <ScoreBar label="Sharp" value={best.quality.sharpness} />
              <ScoreBar label="Light" value={best.quality.brightness} />
              <ScoreBar label="Steady" value={best.quality.stability} />
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Trim label="Start" value={item.start} min={0} max={item.end - 0.3} onChange={(v) => onChange({ start: v })} />
            <Trim label="End" value={item.end} min={item.start + 0.3} max={asset?.duration || 9999} onChange={(v) => onChange({ end: v })} />
          </div>
          <div className="flex flex-wrap gap-2">
            {options.length > 1 && (
              <button className="btn-ghost btn-sm" onClick={() => setShowAlts((s) => !s)}><Replace size={13} /> {showAlts ? 'Hide' : 'Swap take'} ({options.length - 1})</button>
            )}
            {changed && <button className="btn-ghost btn-sm" onClick={() => onChange({ file: best.file, start: best.start, end: best.end })}><Undo2 size={13} /> Reset to AI pick</button>}
          </div>
          {showAlts && (
            <div className="grid gap-2 sm:grid-cols-2">
              {options.map((o, k) => {
                const a = assets[o.file]
                const selected = o.file === item.file && Math.abs(o.start - item.start) < 0.05
                return (
                  <button key={k} type="button" onClick={() => onChange({ file: o.file, start: o.start, end: o.end })}
                    className={clsx('flex gap-2.5 rounded-xl border p-2 text-left transition', selected ? 'border-brand bg-brand-soft' : 'border-line hover:border-ink/30')}>
                    {a && <img src={thumbUrl(a.id, (o.start + o.end) / 2, 240)} alt="" className="h-12 w-20 shrink-0 rounded-md object-cover" />}
                    <span className="min-w-0 text-xs">
                      <span className="block font-semibold">{k === 0 ? 'AI pick' : `Option ${k + 1}`} · {Math.round(o.confidence * 100)}%</span>
                      <span className="block truncate text-muted">{o.file} {fmtTime(o.start)}–{fmtTime(o.end)}</span>
                      <span className="line-clamp-2 text-muted">{o.reason}</span>
                    </span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function EditorStep({ project, refresh, next, goShots }) {
  const runs = project.runs
  const [params, setParams] = useSearchParams()
  const run = pickRun(runs, params.get('run'))
  const setRunId = (id) => setParams((s) => { s.set('run', id); return s }, { replace: true })
  const [timeline, setTimeline] = useState(run?.timeline || [])
  const [dirty, setDirty] = useState(false)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))

  const [mix, setMixRaw] = useState({ ...DEFAULT_MIX, ...(run?.results?.mix || {}) })
  const [view, setView] = useState('timeline')
  const setMix = (fn) => { setMixRaw(fn); setDirty(true) }
  const setTimelineDirty = (fn) => { setTimeline(fn); setDirty(true) }

  useEffect(() => {
    if (!dirty) { setTimeline(run?.timeline || []); setMixRaw({ ...DEFAULT_MIX, ...(run?.results?.mix || {}) }) }
  }, [run?.id, run?.updated_at]) // eslint-disable-line

  const assets = useMemo(() => Object.fromEntries(project.assets.map((a) => [a.filename, a])), [project.assets])
  const shotList = project.shot_lists.find((s) => s.id === run?.shot_list_id)
  const shotsById = useMemo(() => Object.fromEntries((shotList?.shots || []).map((s) => [s.shot_id, s])), [shotList])
  const results = useMemo(() => Object.fromEntries((run?.results?.shots || []).map((r) => [r.shot_id, r])), [run])
  const inCut = new Set(timeline.map((t) => t.shot_id))
  const missing = (run?.results?.shots || []).filter((r) => !inCut.has(r.shot_id))
  const total = timeline.reduce((s, c) => s + (c.end - c.start), 0)

  if (!run) {
    return <Empty icon={<ScanSearch size={22} />} title="No shots found yet" action={<button className="btn-primary" onClick={goShots}>Go to shot list</button>}>
      Run “Find shots” on a shot list. Results show up here as an editable rough cut.
    </Empty>
  }

  const change = (id, patch) => { setTimeline((t) => t.map((c) => (c.shot_id === id ? { ...c, ...patch } : c))); setDirty(true) }
  const addBack = (r, option) => {
    const s = shotsById[r.shot_id] || {}
    const o = option || r.best
    if (!o) return
    const order = (shotList?.shots || []).map((x) => x.shot_id)
    const item = { shot_id: r.shot_id, name: s.name || r.shot_id, file: o.file, start: o.start, end: o.end, needs_audio: !!s.needs_audio }
    setTimeline((t) => {
      const next = [...t, item]
      return next.sort((a, b) => order.indexOf(a.shot_id) - order.indexOf(b.shot_id))
    })
    setDirty(true)
  }

  /** Stretch/shrink every clip proportionally to hit the target length, staying inside its scene. */
  function fitToTarget() {
    const target = project.target_seconds
    const cur = timeline.reduce((s, c) => s + (c.end - c.start), 0)
    if (!cur) return
    const factor = target / cur
    let next = timeline.map((c) => {
      const a = assets[c.file]
      const scene = a?.scenes?.find((s) => c.start >= s.start - 0.15 && c.start < s.end) || { start: 0, end: a?.duration || c.end }
      const lo = Math.max(0, scene.start + 0.1), hi = Math.min(a?.duration || c.end, scene.end - 0.1)
      const want = (c.end - c.start) * factor
      const mid = (c.start + c.end) / 2
      let start = Math.max(lo, mid - want / 2)
      let end = Math.min(hi, start + want)
      start = Math.max(lo, end - want)
      return { ...c, start: round(start), end: round(Math.max(start + 0.5, end)) }
    })
    // Clips that hit a scene boundary can't grow further; give the remainder to the others.
    for (let pass = 0; pass < 3; pass++) {
      const rest = target - next.reduce((s, c) => s + (c.end - c.start), 0)
      if (Math.abs(rest) < 0.15) break
      next = next.map((c) => {
        const a = assets[c.file]
        const scene = a?.scenes?.find((s) => c.start >= s.start - 0.15 && c.start < s.end) || { end: a?.duration || c.end }
        const room = Math.min(a?.duration || c.end, scene.end - 0.1) - c.end
        const add = Math.max(0, Math.min(room, rest / next.length))
        return rest > 0 ? { ...c, end: round(c.end + add) } : { ...c, end: round(Math.max(c.start + 0.5, c.end + rest / next.length)) }
      })
    }
    setTimeline(next)
    setDirty(true)
    toast.success(`Fitted to ${next.reduce((s, c) => s + (c.end - c.start), 0).toFixed(1)}s`)
  }

  async function save(quiet = false) {
    await api.saveTimeline(run.id, timeline)
    await api.saveMix(run.id, mix)
    setDirty(false)
    if (!quiet) toast.success('Cut saved')
    refresh()
  }

  const toolbar = (
    <div className="flex flex-wrap items-center gap-2">
      {runs.length > 1 && (
        <select className="input w-full py-2 sm:w-auto sm:max-w-xs" value={run.id} onChange={(e) => { if (!dirty || confirm('Discard unsaved edits?')) { setDirty(false); setRunId(e.target.value) } }}>
          {runs.map((r) => {
            const sl = project.shot_lists.find((s) => s.id === r.shot_list_id)
            return <option key={r.id} value={r.id}>{sl?.name || 'Shot list'} · {r.approach} · {new Date(r.created_at).toLocaleTimeString()}</option>
          })}
        </select>
      )}
      <Segmented value={view} onChange={setView} options={[{ value: 'timeline', label: 'Timeline' }, { value: 'cards', label: 'Cards' }]} />
      {view === 'timeline' && (
        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <span className={clsx('font-display text-lg font-bold tabular-nums', Math.abs(total - project.target_seconds) > 3 ? 'text-amber-600' : 'text-ink')}>{total.toFixed(1)}s</span>
          {Math.abs(total - project.target_seconds) > 0.5 && timeline.length > 0 && (
            <button className="btn-ghost btn-sm" onClick={fitToTarget}><Scaling size={13} /> Fit to {project.target_seconds}s</button>
          )}
          <button className="btn-ghost btn-sm" disabled={!dirty} onClick={() => save()}><Save size={13} /> {dirty ? 'Save' : 'Saved'}</button>
          <button className="btn-primary btn-sm" onClick={async () => { if (dirty) await save(true); next() }} disabled={!timeline.length}>Export <ArrowRight size={13} /></button>
        </div>
      )}
    </div>
  )

  return (
    <div className="space-y-4">
      {toolbar}
      {view === 'timeline' && (
        <TimelinePanel project={project} run={run} timeline={timeline} setTimeline={setTimelineDirty} mix={mix} setMix={setMix}
          assets={assets} results={results} refresh={refresh} />
      )}
    <div className={clsx('grid gap-6', view === 'cards' && 'lg:grid-cols-[1fr_300px]')}>
      <div className="min-w-0 space-y-4">
        {view === 'cards' && <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => {
          if (over && active.id !== over.id) {
            setTimeline((t) => arrayMove(t, t.findIndex((x) => x.shot_id === active.id), t.findIndex((x) => x.shot_id === over.id)))
            setDirty(true)
          }
        }}>
          <SortableContext items={timeline.map((c) => c.shot_id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-4">
              {timeline.map((c, i) => (
                <ClipCard key={c.shot_id} item={c} index={i} result={results[c.shot_id]} shot={shotsById[c.shot_id]} assets={assets}
                  onChange={(patch) => change(c.shot_id, patch)} onRemove={() => { setTimeline((t) => t.filter((x) => x.shot_id !== c.shot_id)); setDirty(true) }} />
              ))}
            </div>
          </SortableContext>
        </DndContext>}

        {missing.length > 0 && (
          <div className="space-y-3">
            <h3 className="flex items-center gap-2 pt-2 text-lg font-bold"><AlertTriangle size={18} className="text-brand" /> Not in the cut ({missing.length})</h3>
            {missing.map((r) => {
              const s = shotsById[r.shot_id] || {}
              const opts = r.best ? [r.best, ...(r.alternatives || [])] : (r.suggestions || [])
              return (
                <div key={r.shot_id} className={clsx('card p-4', r.status === 'missing' && 'border-brand/30 bg-brand-soft/40')}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={clsx('chip', r.status === 'missing' ? 'bg-brand text-white' : 'bg-stone-200 text-muted')}>{r.status === 'missing' ? 'Missing in footage' : 'Removed'}</span>
                    <p className="font-semibold">{s.name || r.shot_id}</p>
                    <span className="text-xs text-muted">{r.shot_id}</span>
                  </div>
                  {r.reason && <p className="mt-2 text-sm text-ink/80">{r.reason}</p>}
                  {s.description && <p className="mt-1 text-xs text-muted">Wanted: {s.description}</p>}
                  {opts.length > 0 && (
                    <div className="mt-3">
                      <p className="label">{r.status === 'missing' ? 'Closest low-confidence candidates (use only if acceptable)' : 'Add back'}</p>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {opts.slice(0, 3).map((o, k) => {
                          const a = assets[o.file]
                          return (
                            <button key={k} onClick={() => addBack(r, o)} className="flex gap-2.5 rounded-xl border border-line bg-white p-2 text-left hover:border-ink/30">
                              {a && <img src={thumbUrl(a.id, (o.start + o.end) / 2, 240)} alt="" className="h-12 w-20 shrink-0 rounded-md object-cover" />}
                              <span className="min-w-0 text-xs">
                                <span className="block font-semibold">{Math.round(o.confidence * 100)}% · {fmtTime(o.start)}–{fmtTime(o.end)}</span>
                                <span className="line-clamp-2 text-muted">{o.reason}</span>
                              </span>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {view === 'cards' && <aside className="space-y-4 lg:sticky lg:top-32 lg:self-start">
        <div className="card p-4">
          <div className="flex items-baseline justify-between">
            <span className="label mb-0">Cut length</span>
            <span className={clsx('font-display text-3xl font-bold tabular-nums', Math.abs(total - project.target_seconds) > 3 ? 'text-amber-600' : 'text-ink')}>{total.toFixed(1)}s</span>
          </div>
          <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-stone-100">
            {timeline.map((c, i) => (
              <div key={c.shot_id} title={c.name} style={{ width: `${((c.end - c.start) / Math.max(total, project.target_seconds)) * 100}%` }}
                className={clsx('border-r border-white', i % 2 ? 'bg-ink' : 'bg-brand')} />
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">Target {project.target_seconds}s · {timeline.length} clips · {missing.filter((m) => m.status === 'missing').length} missing</p>
          {Math.abs(total - project.target_seconds) > 0.5 && timeline.length > 0 && (
            <button className="btn-ghost mt-3 w-full" onClick={fitToTarget}><Scaling size={15} /> Fit to {project.target_seconds}s</button>
          )}
          <button className="btn-ghost mt-2 w-full" disabled={!dirty} onClick={() => save()}><Save size={15} /> {dirty ? 'Save edits' : 'Saved'}</button>
        </div>
        <button className="btn-primary w-full" onClick={async () => { if (dirty) await save(true); next() }} disabled={!timeline.length}>
          Export <ArrowRight size={15} />
        </button>
        <p className="px-1 text-xs leading-relaxed text-muted">Drag cards to reorder. Trim with − / +, or swap to another take. Missing shots are never faked — pick a candidate only if it really works.</p>
      </aside>}
    </div>
    </div>
  )
}
