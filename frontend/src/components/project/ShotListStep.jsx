import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { DndContext, closestCenter, PointerSensor, TouchSensor, KeyboardSensor, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, arrayMove, useSortable, verticalListSortingStrategy, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Sparkles, Upload, Plus, GripVertical, Trash2, Mic, Save, ScanSearch, Loader2, AlertTriangle, ListChecks, Quote } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../api.js'
import { Empty, JobCard, Segmented } from '../ui.jsx'

const SOURCE = { ai: 'AI', rules: 'Rule-based', reference: 'Imported', manual: 'Manual' }

/** "today 01:44", "yesterday 18:20" or "2 Nov, 18:20". */
function when(d) {
  const t = new Date(d)
  const time = t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  const today = new Date()
  const y = new Date(); y.setDate(today.getDate() - 1)
  if (t.toDateString() === today.toDateString()) return `today ${time}`
  if (t.toDateString() === y.toDateString()) return `yesterday ${time}`
  return `${t.toLocaleDateString([], { day: 'numeric', month: 'short' })}, ${time}`
}

function ShotRow({ shot, index, onChange, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: shot.shot_id })
  return (
    <div ref={setNodeRef} style={{ transform: CSS.Transform.toString(transform), transition }}
      className={clsx('card p-3 sm:p-4', isDragging && 'relative z-10 shadow-xl ring-2 ring-brand')}>
      <div className="flex gap-2 sm:gap-3">
        <button {...attributes} {...listeners} aria-label="Drag to reorder"
          className="mt-1 h-8 w-6 shrink-0 cursor-grab touch-none rounded text-muted hover:bg-stone-100 active:cursor-grabbing">
          <GripVertical size={16} className="mx-auto" />
        </button>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip bg-ink text-white">{index + 1}</span>
            <span className="text-xs font-semibold text-muted">{shot.shot_id}</span>
            {shot.grounded === false && (
              <span className="chip bg-amber-50 text-amber-700" title="This shot's source text was not found in the brief"><AlertTriangle size={11} /> not in brief?</span>
            )}
          </div>
          <input className="input font-semibold" value={shot.name} onChange={(e) => onChange({ name: e.target.value })} aria-label="Shot name" />
          <textarea rows={2} className="input resize-y text-sm" value={shot.description} onChange={(e) => onChange({ description: e.target.value })} aria-label="Shot description" />
          {shot.brief_quote && <p className="flex items-start gap-1.5 text-xs italic text-muted"><Quote size={11} className="mt-0.5 shrink-0" />{shot.brief_quote}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs font-semibold text-muted">
              Length
              <input type="number" step={0.5} min={0.5} max={60} className="input w-20 py-1.5" value={shot.target_seconds}
                onChange={(e) => onChange({ target_seconds: Number(e.target.value) })} />
              s
            </label>
            <button type="button" onClick={() => onChange({ needs_audio: !shot.needs_audio })}
              className={clsx('chip border transition', shot.needs_audio ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-white text-muted')}>
              <Mic size={11} /> {shot.needs_audio ? 'Found by audio' : 'Visual'}
            </button>
          </div>
        </div>
        <button onClick={onRemove} aria-label="Remove shot" className="h-8 w-8 shrink-0 rounded-lg text-muted hover:bg-stone-100 hover:text-brand"><Trash2 size={15} className="mx-auto" /></button>
      </div>
    </div>
  )
}

export default function ShotListStep({ project, refresh, next }) {
  const lists = project.shot_lists
  const [activeId, setActiveId] = useState(lists.at(-1)?.id)
  const active = lists.find((l) => l.id === activeId) || lists.at(-1)
  const [shots, setShots] = useState(active?.shots || [])
  const [name, setName] = useState(active?.name || '')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState('')
  const [approach, setApproach] = useState('hybrid')
  const fileRef = useRef(null)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 150, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))

  useEffect(() => {
    if (!dirty) { setShots(active?.shots || []); setName(active?.name || '') }
  }, [active?.id, active?.updated_at]) // eslint-disable-line react-hooks/exhaustive-deps

  const total = useMemo(() => shots.reduce((s, x) => s + (Number(x.target_seconds) || 0), 0), [shots])
  const findJob = project.jobs.find((j) => j.kind === 'find' && j.params?.shot_list_id === active?.id)
  const finding = findJob && ['queued', 'running'].includes(findJob.status)
  const videosReady = project.assets.some((a) => a.kind === 'video')

  const edit = (id, patch) => { setShots((s) => s.map((x) => (x.shot_id === id ? { ...x, ...patch } : x))); setDirty(true) }
  const add = () => {
    const used = new Set(shots.map((s) => s.shot_id))
    let n = shots.length + 1
    while (used.has(`N${n}`)) n++
    setShots((s) => [...s, { shot_id: `N${n}`, name: 'New shot', description: '', target_seconds: 3, needs_audio: false, visual_queries: [], negative_queries: [], audio_keywords: [] }])
    setDirty(true)
  }

  async function save(quiet = false) {
    const body = { name, source: active.source, shots: shots.map((s, i) => ({ ...s, order: i + 1 })) }
    await api.saveShotList(active.id, body)
    setDirty(false)
    if (!quiet) toast.success('Shot list saved')
    refresh()
  }

  async function plan() {
    if (!project.brief.trim()) return toast.error('This project has no brief')
    setBusy('plan')
    try {
      const sl = await api.plan(project.id)
      toast.success(`${sl.name}: ${sl.shots.length} shots (${sl.meta?.model})`)
      setActiveId(sl.id); setDirty(false); refresh()
    } catch (e) { toast.error(e.message) }
    setBusy('')
  }

  async function importFile(file) {
    setBusy('import')
    try {
      const sl = await api.importShotList(project.id, file, file.name.replace(/\.(json|csv)$/i, ''))
      toast.success(`Imported ${sl.shots.length} shots`)
      setActiveId(sl.id); setDirty(false); refresh()
    } catch (e) { toast.error(e.message) }
    setBusy('')
  }

  async function blank() {
    const sl = await api.createShotList(project.id, { name: 'Manual shot list', source: 'manual', shots: [{ shot_id: 'M1', name: 'First shot', description: '', target_seconds: 3 }] })
    setActiveId(sl.id); setDirty(false); refresh()
  }

  async function removeList() {
    const runs = project.runs.filter((r) => r.shot_list_id === active.id).length
    const msg = `Delete “${active.name}” (${when(active.created_at)})?` +
      (runs ? `\n\nIts ${runs} shot search result${runs > 1 ? 's' : ''} will be deleted too. Rendered videos stay in Versions.` : '')
    if (!confirm(msg)) return
    try {
      await api.deleteShotList(active.id)
      toast.success('Shot list deleted')
      setDirty(false)
      setActiveId(lists.filter((l) => l.id !== active.id).at(-1)?.id)
      refresh()
    } catch (e) { toast.error(e.message) }
  }

  async function find() {
    if (dirty) await save(true)
    try {
      await api.find(active.id, approach)
      toast.success('Searching the footage…')
      refresh()
    } catch (e) { toast.error(e.message) }
  }

  const toolbar = (
    <div className="flex flex-wrap gap-2">
      <button className="btn-primary" onClick={plan} disabled={!!busy}>
        {busy === 'plan' ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />} Generate from brief
      </button>
      <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={!!busy}>
        {busy === 'import' ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} Import JSON/CSV
      </button>
      <button className="btn-ghost" onClick={blank}><Plus size={15} /> Blank</button>
      <input ref={fileRef} type="file" accept=".json,.csv" className="hidden" onChange={(e) => { e.target.files[0] && importFile(e.target.files[0]); e.target.value = '' }} />
    </div>
  )

  if (!active) {
    return (
      <div className="space-y-4">
        {toolbar}
        <Empty icon={<ListChecks size={22} />} title="No shot list yet">
          Let the AI plan one from the brief, or import an existing list (e.g. a reference shot list in JSON or CSV).
        </Empty>
      </div>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        {toolbar}
        <div className="flex flex-wrap items-center gap-2">
          {lists.length > 1 && (
            <select className="input w-full py-2 sm:w-auto" value={active.id} aria-label="Choose shot list"
              onChange={(e) => { if (!dirty || confirm('Discard unsaved changes?')) { setDirty(false); setActiveId(e.target.value) } }}>
              {[...lists].reverse().map((l, i) => (
                <option key={l.id} value={l.id}>
                  {l.name} · {l.shots.length} shots · {SOURCE[l.source] || l.source} · {when(l.created_at)}{i === 0 ? ' (newest)' : ''}
                </option>
              ))}
            </select>
          )}
          <input className="input w-auto min-w-0 flex-1 py-2 font-semibold" value={name} onChange={(e) => { setName(e.target.value); setDirty(true) }} aria-label="Shot list name" />
          <span className="chip bg-stone-100 text-muted" title={`Created ${new Date(active.created_at).toLocaleString()}`}>
            {active.source === 'ai' ? `AI · ${active.meta?.model}` : SOURCE[active.source] || active.source} · {when(active.created_at)}
          </span>
          <button onClick={removeList} aria-label="Delete this shot list" title="Delete this shot list"
            className="grid h-9 w-9 place-items-center rounded-lg border border-line bg-white text-muted hover:border-brand hover:text-brand">
            <Trash2 size={15} />
          </button>
        </div>
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active: a, over }) => {
          if (over && a.id !== over.id) {
            setShots((s) => arrayMove(s, s.findIndex((x) => x.shot_id === a.id), s.findIndex((x) => x.shot_id === over.id)))
            setDirty(true)
          }
        }}>
          <SortableContext items={shots.map((s) => s.shot_id)} strategy={verticalListSortingStrategy}>
            <div className="space-y-3">
              {shots.map((s, i) => (
                <ShotRow key={s.shot_id} shot={s} index={i} onChange={(patch) => edit(s.shot_id, patch)}
                  onRemove={() => { setShots((x) => x.filter((y) => y.shot_id !== s.shot_id)); setDirty(true) }} />
              ))}
            </div>
          </SortableContext>
        </DndContext>
        <button className="btn-ghost w-full border-dashed" onClick={add}><Plus size={15} /> Add shot</button>
      </div>

      <aside className="space-y-4 lg:sticky lg:top-32 lg:self-start">
        <div className="card p-4">
          <div className="flex items-baseline justify-between">
            <span className="label mb-0">Planned length</span>
            <span className={clsx('font-display text-2xl font-bold tabular-nums', Math.abs(total - project.target_seconds) > 2 ? 'text-amber-600' : 'text-ink')}>
              {total.toFixed(1)}s
            </span>
          </div>
          <p className="mt-1 text-xs text-muted">Target {project.target_seconds}s · {shots.length} shots · {shots.filter((s) => s.needs_audio).length} found by audio</p>
          <button className="btn-ghost mt-3 w-full" onClick={() => save()} disabled={!dirty}><Save size={15} /> {dirty ? 'Save changes' : 'Saved'}</button>
        </div>
        <div className="card space-y-3 p-4">
          <span className="label mb-0">Search the footage</span>
          <Segmented value={approach} onChange={setApproach} options={[{ value: 'hybrid', label: 'Hybrid (best)' }, { value: 'baseline', label: 'Plain CLIP' }]} />
          <p className="text-xs leading-relaxed text-muted">
            {approach === 'hybrid'
              ? 'Compares every shot against look-alikes, stays inside scenes, prefers sharp/bright/steady takes and confirms spoken moments in the transcript.'
              : 'Baseline for comparison: best single frame by CLIP similarity, no quality or look-alike checks.'}
          </p>
          <button className="btn-primary w-full" onClick={find} disabled={finding || !videosReady || !shots.length}>
            {finding ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />} Find shots
          </button>
          {!videosReady && <p className="text-xs text-brand">Upload footage first.</p>}
        </div>
        {findJob && <JobCard job={findJob} />}
        {findJob?.status === 'done' && <button className="btn-dark w-full" onClick={() => next(findJob.result?.run_id)}>Open editor</button>}
      </aside>
    </div>
  )
}
