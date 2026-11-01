import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { DndContext, PointerSensor, KeyboardSensor, useSensor, useSensors, closestCenter } from '@dnd-kit/core'
import { SortableContext, arrayMove, horizontalListSortingStrategy, useSortable, sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Play, Pause, SkipBack, Music, Type, Film, Plus, Trash2, Upload, Loader2, Volume2, VolumeX, ZoomIn, Mic, Replace } from 'lucide-react'
import clsx from 'clsx'
import { api, fmtTime, streamUrl, thumbUrl } from '../../api.js'
import { Segmented, Slider, Trim } from '../ui.jsx'

const HEAD = 76 // px width of the track-label column
const round = (v) => Math.round(v * 100) / 100

export const DEFAULT_MIX = { music_asset_id: null, music_volume: 0.5, music_offset: 0, duck: true, title: '', title_seconds: 3, crossfade: 0 }

/** Same rule as the renderer (exporter.clip_volume) so the preview sounds like the export. */
export function clipVolume(c, hasMusic) {
  if (c.mute) return 0
  if (c.volume != null) return c.volume
  return !hasMusic || c.needs_audio ? 1 : 0.12
}

function Ruler({ total, pps, onSeek }) {
  const step = pps >= 60 ? 1 : pps >= 25 ? 2 : 5
  const ticks = []
  for (let t = 0; t <= total + 0.001; t += step) ticks.push(t)
  return (
    <div className="relative h-6 cursor-pointer border-b border-white/10" style={{ width: total * pps }}
      onPointerDown={(e) => onSeek((e.clientX - e.currentTarget.getBoundingClientRect().left) / pps)}>
      {ticks.map((t) => (
        <span key={t} className="absolute top-0 h-full border-l border-white/15 pl-1 text-[10px] tabular-nums text-white/40" style={{ left: t * pps }}>{t}s</span>
      ))}
    </div>
  )
}

function ClipBlock({ c, pps, asset, selected, onSelect, onTrim, index }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: c.shot_id })
  const dur = c.end - c.start
  const startDrag = (edge) => (e) => {
    e.stopPropagation()
    e.preventDefault()
    const x0 = e.clientX, s0 = c.start, e0 = c.end
    const move = (ev) => {
      const dt = (ev.clientX - x0) / pps
      if (edge === 'start') onTrim({ start: round(Math.min(e0 - 0.3, Math.max(0, s0 + dt))) })
      else onTrim({ end: round(Math.max(s0 + 0.3, Math.min(asset?.duration || e0 + 60, e0 + dt))) })
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
  return (
    <div ref={setNodeRef} style={{ width: dur * pps, transform: CSS.Transform.toString(transform), transition }}
      className={clsx('group relative h-14 shrink-0 select-none overflow-hidden rounded-md border-2 bg-ink-2',
        selected ? 'z-10 border-brand' : 'border-white/10 hover:border-white/40', isDragging && 'opacity-70')}
      onPointerDown={() => onSelect()}>
      {asset && <img src={thumbUrl(asset.id, c.start + dur / 2, 240)} alt="" draggable={false} className="absolute inset-0 h-full w-full object-cover opacity-60" />}
      <div {...attributes} {...listeners} className="absolute inset-0 cursor-grab active:cursor-grabbing" aria-label={`Move ${c.name}`} />
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center gap-1 bg-gradient-to-b from-black/80 to-transparent px-1.5 pt-1 text-[11px] font-semibold text-white">
        <span className="rounded bg-black/50 px-1">{index + 1}</span>
        <span className="truncate">{c.name}</span>
        {c.needs_audio && <Mic size={10} className="shrink-0 text-red-300" />}
        {c.mute && <VolumeX size={10} className="shrink-0" />}
      </div>
      <span className="pointer-events-none absolute bottom-0.5 right-1.5 text-[10px] tabular-nums text-white/80">{dur.toFixed(1)}s</span>
      <div onPointerDown={startDrag('start')} className="absolute inset-y-0 left-0 w-2 cursor-ew-resize bg-white/0 hover:bg-brand/70" aria-label="Trim start" />
      <div onPointerDown={startDrag('end')} className="absolute inset-y-0 right-0 w-2 cursor-ew-resize bg-white/0 hover:bg-brand/70" aria-label="Trim end" />
    </div>
  )
}

function TrackLabel({ icon: Icon, label }) {
  return (
    <div className="sticky left-0 z-20 flex shrink-0 items-center gap-1.5 border-r border-white/10 bg-ink px-2 text-[11px] font-semibold text-white/60" style={{ width: HEAD }}>
      <Icon size={12} /> {label}
    </div>
  )
}

export default function TimelinePanel({ project, run, timeline, setTimeline, mix, setMix, assets, results, refresh }) {
  const [playhead, setPlayhead] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [selected, setSelected] = useState(null) // {type:'clip', id} | {type:'music'} | {type:'title'}
  const [pps, setPps] = useState(28)
  const [uploading, setUploading] = useState(false)
  const videoRef = useRef(null)
  const audioRef = useRef(null)
  const scrollRef = useRef(null)
  const musicInput = useRef(null)
  const state = useRef({ k: -1, raf: 0 })
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))

  const starts = useMemo(() => {
    let t = 0
    return timeline.map((c) => { const s = t; t += c.end - c.start; return s })
  }, [timeline])
  const total = timeline.reduce((s, c) => s + (c.end - c.start), 0)
  const musicAssets = project.assets.filter((a) => a.kind === 'music')
  const music = musicAssets.find((a) => a.id === mix.music_asset_id)
  const hasMusic = !!music
  const titleFrom = Math.max(0, total - mix.title_seconds)
  const showTitle = mix.title && playhead >= titleFrom

  const clipAt = useCallback((t) => {
    for (let k = 0; k < timeline.length; k++) if (t < starts[k] + (timeline[k].end - timeline[k].start) - 1e-3) return k
    return timeline.length - 1
  }, [timeline, starts])

  const applyLevels = useCallback((k) => {
    const c = timeline[k]
    if (videoRef.current && c) videoRef.current.volume = Math.min(1, clipVolume(c, hasMusic))
    if (audioRef.current) {
      const ducked = mix.duck && c?.needs_audio && !c?.mute
      audioRef.current.volume = Math.min(1, mix.music_volume * (ducked ? 0.2 : 1))
    }
  }, [timeline, hasMusic, mix.duck, mix.music_volume])

  /** Load clip k into the monitor at an offset (seconds into that clip). */
  const loadClip = useCallback((k, offset, autoplay) => {
    const v = videoRef.current, c = timeline[k]
    if (!v || !c) return
    const a = assets[c.file]
    const src = a ? streamUrl(a.id) : ''
    state.current.k = k
    const go = () => {
      v.currentTime = c.start + offset
      applyLevels(k)
      if (autoplay) v.play().catch(() => {})
    }
    if (!v.src.endsWith(src)) {
      v.src = src
      v.addEventListener('loadedmetadata', go, { once: true })
    } else go()
  }, [timeline, assets, applyLevels])

  const seek = useCallback((t) => {
    const tt = Math.max(0, Math.min(total - 0.01, t))
    setPlayhead(tt)
    if (!timeline.length) return
    const k = clipAt(tt)
    loadClip(k, tt - starts[k], playing)
    if (audioRef.current && hasMusic) {
      const d = audioRef.current.duration || 0
      const pos = mix.music_offset + tt
      audioRef.current.currentTime = d ? pos % d : pos
    }
  }, [total, timeline.length, clipAt, loadClip, starts, playing, hasMusic, mix.music_offset])

  // Playback clock: the video element drives time; jump to the next clip at each out-point.
  // A timer (not requestAnimationFrame) so playback keeps cutting correctly in a background tab.
  useEffect(() => {
    if (!playing) return
    const tick = () => {
      const v = videoRef.current, k = state.current.k, c = timeline[k]
      if (!v || !c || state.current.switching) return
      if (v.currentTime >= c.end - 0.04) {
        if (k + 1 < timeline.length) {
          state.current.switching = true
          loadClip(k + 1, 0, true)
          setTimeout(() => { state.current.switching = false }, 120)
        } else {
          setPlaying(false); v.pause(); audioRef.current?.pause(); setPlayhead(total)
        }
      } else {
        setPlayhead(starts[k] + Math.max(0, v.currentTime - c.start))
      }
    }
    const id = setInterval(tick, 40)
    return () => clearInterval(id)
  }, [playing, timeline, starts, loadClip, total])

  useEffect(() => { if (state.current.k >= 0) applyLevels(state.current.k) }, [applyLevels])
  useEffect(() => { seek(Math.min(playhead, Math.max(0, total - 0.01))) }, [timeline.length]) // eslint-disable-line

  function togglePlay() {
    if (!timeline.length) return
    if (playing) {
      setPlaying(false)
      videoRef.current?.pause()
      audioRef.current?.pause()
      return
    }
    const t = playhead >= total - 0.05 ? 0 : playhead
    setPlaying(true)
    const k = clipAt(t)
    setPlayhead(t)
    loadClip(k, t - starts[k], true)
    if (audioRef.current && hasMusic) {
      const d = audioRef.current.duration || 0
      audioRef.current.currentTime = d ? (mix.music_offset + t) % d : mix.music_offset + t
      audioRef.current.play().catch(() => {})
    }
  }

  // Keep the playhead visible while playing.
  useEffect(() => {
    const el = scrollRef.current
    if (!el || !playing) return
    const x = HEAD + playhead * pps
    if (x > el.scrollLeft + el.clientWidth - 40 || x < el.scrollLeft + HEAD) el.scrollLeft = x - HEAD - 40
  }, [playhead, pps, playing])

  const patchClip = (id, patch) => setTimeline((t) => t.map((c) => (c.shot_id === id ? { ...c, ...patch } : c)))
  const sel = selected?.type === 'clip' ? timeline.find((c) => c.shot_id === selected.id) : null
  const selResult = sel ? results[sel.shot_id] : null

  async function uploadMusic(file) {
    setUploading(true)
    try {
      const a = await api.uploadMusic(project.id, file)
      setMix((m) => ({ ...m, music_asset_id: a.id }))
      setSelected({ type: 'music' })
      toast.success('Music added to the timeline')
      refresh()
    } catch (e) { toast.error(e.message) }
    setUploading(false)
  }

  const trackWidth = Math.max(total, 1) * pps + 40

  return (
    <div className="space-y-4">
      {/* Monitor + inspector */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="overflow-hidden rounded-2xl bg-ink">
          <div className="relative mx-auto h-[min(48vh,400px)] max-w-full bg-black"
            style={{ aspectRatio: { '9:16': '9 / 16', '1:1': '1 / 1', '4:5': '4 / 5' }[project.aspect_ratio] || '16 / 9' }}>
            <video ref={videoRef} playsInline preload="auto" className="h-full w-full object-cover" onClick={togglePlay} />
            {showTitle && (
              <div className="pointer-events-none absolute inset-x-0 bottom-[18%] flex justify-center px-4">
                <span className="rounded bg-brand/90 px-3 py-1.5 font-display text-sm font-bold text-white shadow-lg sm:text-lg">{mix.title}</span>
              </div>
            )}
            {!timeline.length && <p className="absolute inset-0 grid place-items-center text-sm text-white/50">The cut is empty</p>}
          </div>
          {music && <audio ref={audioRef} src={api.musicUrl(music.id)} loop preload="auto" />}
          <div className="flex items-center gap-3 border-t border-white/10 px-3 py-2.5 text-white">
            <button onClick={() => seek(0)} aria-label="Back to start" className="grid h-9 w-9 place-items-center rounded-lg hover:bg-white/10"><SkipBack size={16} /></button>
            <button onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'} className="grid h-10 w-10 place-items-center rounded-full bg-brand hover:bg-brand-dark">
              {playing ? <Pause size={17} /> : <Play size={17} className="ml-0.5" />}
            </button>
            <span className="font-mono text-sm tabular-nums">{fmtTime(playhead)} <span className="text-white/40">/ {fmtTime(total)}</span></span>
            <span className="ml-auto hidden text-xs text-white/40 sm:inline">Preview · cuts shown as hard cuts</span>
          </div>
        </div>

        <div className="card space-y-4 p-4">
          {sel ? (
            <>
              <div>
                <p className="label mb-0">Clip {timeline.indexOf(sel) + 1}</p>
                <p className="font-display text-lg font-semibold">{sel.name}</p>
                <p className="truncate text-xs text-muted">{sel.file} · {fmtTime(sel.start)}–{fmtTime(sel.end)}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Trim label="In" value={sel.start} min={0} max={sel.end - 0.3} onChange={(v) => patchClip(sel.shot_id, { start: v })} />
                <Trim label="Out" value={sel.end} min={sel.start + 0.3} max={assets[sel.file]?.duration || 9999} onChange={(v) => patchClip(sel.shot_id, { end: v })} />
              </div>
              <div className="space-y-2 rounded-xl bg-stone-50 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-muted">Original sound</span>
                  <button className={clsx('chip border', sel.mute ? 'border-brand bg-brand-soft text-brand' : 'border-line bg-white text-muted')}
                    onClick={() => patchClip(sel.shot_id, { mute: !sel.mute })}>
                    {sel.mute ? <><VolumeX size={11} /> Muted</> : <><Volume2 size={11} /> On</>}
                  </button>
                </div>
                <Slider label={sel.volume == null ? 'Level (auto)' : 'Level'} value={clipVolume(sel, hasMusic)} max={1.5} disabled={sel.mute}
                  onChange={(v) => patchClip(sel.shot_id, { volume: v })} />
                {sel.volume != null && <button className="text-xs font-semibold text-brand" onClick={() => patchClip(sel.shot_id, { volume: null })}>Reset to auto</button>}
              </div>
              {selResult?.alternatives?.length > 0 && (
                <div>
                  <p className="label flex items-center gap-1"><Replace size={11} /> Other takes</p>
                  <div className="space-y-1.5">
                    {[selResult.best, ...selResult.alternatives].map((o, i) => (
                      <button key={i} onClick={() => patchClip(sel.shot_id, { file: o.file, start: o.start, end: o.end })}
                        className={clsx('flex w-full items-center gap-2 rounded-lg border p-1.5 text-left text-xs', o.file === sel.file && Math.abs(o.start - sel.start) < 0.05 ? 'border-brand bg-brand-soft' : 'border-line hover:border-ink/30')}>
                        {assets[o.file] && <img src={thumbUrl(assets[o.file].id, (o.start + o.end) / 2, 160)} alt="" className="h-8 w-14 rounded object-cover" />}
                        <span className="min-w-0"><b>{i === 0 ? 'AI pick' : `Option ${i + 1}`}</b> · {Math.round(o.confidence * 100)}%<span className="block truncate text-muted">{o.file} {fmtTime(o.start)}</span></span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <button className="btn-ghost btn-sm w-full text-brand" onClick={() => { setTimeline((t) => t.filter((c) => c.shot_id !== sel.shot_id)); setSelected(null) }}>
                <Trash2 size={13} /> Remove from cut
              </button>
            </>
          ) : selected?.type === 'music' ? (
            <>
              <div><p className="label mb-0">Music track</p><p className="font-display text-lg font-semibold">{music ? music.filename.replace(/^_music_/, '') : 'No music'}</p></div>
              <select className="input py-2" value={mix.music_asset_id || ''} onChange={(e) => setMix((m) => ({ ...m, music_asset_id: e.target.value || null }))}>
                <option value="">No music</option>
                {musicAssets.map((m) => <option key={m.id} value={m.id}>{m.filename.replace(/^_music_/, '')}</option>)}
              </select>
              <button className="btn-ghost btn-sm w-full" onClick={() => musicInput.current?.click()} disabled={uploading}>
                {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} Upload a track
              </button>
              {music && (
                <>
                  <Slider label="Music volume" value={mix.music_volume} max={1.5} onChange={(v) => setMix((m) => ({ ...m, music_volume: v }))} />
                  <label className="block">
                    <span className="text-xs font-semibold text-muted">Start the song at (seconds)</span>
                    <input type="number" min={0} step={0.5} className="input mt-1.5 py-2" value={mix.music_offset}
                      onChange={(e) => setMix((m) => ({ ...m, music_offset: Math.max(0, Number(e.target.value)) }))} />
                  </label>
                  <label className="flex items-start gap-2.5 rounded-xl bg-stone-50 p-3 text-xs">
                    <input type="checkbox" className="mt-0.5 accent-brand" checked={mix.duck} onChange={(e) => setMix((m) => ({ ...m, duck: e.target.checked }))} />
                    <span><b className="text-ink">Duck under dialogue</b><span className="block text-muted">Music drops to 20% on clips that need their own sound (e.g. the welcome line).</span></span>
                  </label>
                  <p className="text-xs text-muted">Loops if shorter than the cut · fades out over the last 1.5 s.</p>
                  <button className="btn-ghost btn-sm w-full text-brand" onClick={() => setMix((m) => ({ ...m, music_asset_id: null }))}><Trash2 size={13} /> Remove music</button>
                </>
              )}
            </>
          ) : selected?.type === 'title' ? (
            <>
              <div><p className="label mb-0">Title</p><p className="font-display text-lg font-semibold">End title</p></div>
              <input className="input" placeholder="e.g. Bean & Bloom · Now open" maxLength={60} value={mix.title} onChange={(e) => setMix((m) => ({ ...m, title: e.target.value }))} />
              <Slider label="Shown for the last" value={mix.title_seconds} min={1} max={Math.max(1, Math.min(10, Math.floor(total)))} step={0.5} fmt={(v) => `${v}s`}
                onChange={(v) => setMix((m) => ({ ...m, title_seconds: v }))} />
              {mix.title && <button className="btn-ghost btn-sm w-full text-brand" onClick={() => setMix((m) => ({ ...m, title: '' }))}><Trash2 size={13} /> Remove title</button>}
            </>
          ) : (
            <>
              <div><p className="label mb-0">Sequence</p><p className="font-display text-lg font-semibold">{timeline.length} clips · {total.toFixed(1)}s</p></div>
              <div>
                <span className="label">Transitions (in the export)</span>
                <Segmented value={mix.crossfade} onChange={(v) => setMix((m) => ({ ...m, crossfade: v }))}
                  options={[{ value: 0, label: 'Cuts' }, { value: 0.3, label: 'Quick fade' }, { value: 0.6, label: 'Soft fade' }]} />
              </div>
              <p className="text-xs leading-relaxed text-muted">Click a clip, the music track or the title track to edit it. Drag clips to reorder, drag their edges to trim. Click the ruler to move the playhead.</p>
            </>
          )}
        </div>
      </div>

      {/* Timeline */}
      <div className="overflow-hidden rounded-2xl bg-ink text-white">
        <div className="flex items-center gap-3 border-b border-white/10 px-3 py-2 text-xs">
          <span className="font-semibold text-white/80">Timeline</span>
          <span className="text-white/40">{timeline.length} clips · {total.toFixed(1)}s / target {project.target_seconds}s</span>
          <label className="ml-auto flex items-center gap-2 text-white/50"><ZoomIn size={13} />
            <input type="range" min={10} max={90} value={pps} onChange={(e) => setPps(Number(e.target.value))} className="w-24 accent-brand" aria-label="Zoom" />
          </label>
        </div>
        <div ref={scrollRef} className="relative overflow-x-auto">
          <div style={{ width: trackWidth + HEAD }} className="relative">
            <div className="flex">
              <div className="sticky left-0 z-20 shrink-0 bg-ink" style={{ width: HEAD }} />
              <Ruler total={Math.max(total, 1)} pps={pps} onSeek={seek} />
            </div>
            {/* V1 */}
            <div className="flex border-b border-white/5 py-1.5">
              <TrackLabel icon={Film} label="V1" />
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={({ active, over }) => {
                if (over && active.id !== over.id) setTimeline((t) => arrayMove(t, t.findIndex((x) => x.shot_id === active.id), t.findIndex((x) => x.shot_id === over.id)))
              }}>
                <SortableContext items={timeline.map((c) => c.shot_id)} strategy={horizontalListSortingStrategy}>
                  <div className="flex">
                    {timeline.map((c, i) => (
                      <ClipBlock key={c.shot_id} c={c} index={i} pps={pps} asset={assets[c.file]} selected={selected?.id === c.shot_id}
                        onSelect={() => { setSelected({ type: 'clip', id: c.shot_id }); if (!playing) seek(starts[i] + 0.01) }}
                        onTrim={(patch) => patchClip(c.shot_id, patch)} />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </div>
            {/* A1 music */}
            <div className="flex border-b border-white/5 py-1.5">
              <TrackLabel icon={Music} label="A1" />
              {music ? (
                <button onClick={() => setSelected({ type: 'music' })} style={{ width: total * pps }}
                  className={clsx('relative h-10 overflow-hidden rounded-md border-2 text-left', selected?.type === 'music' ? 'border-brand' : 'border-white/10 hover:border-white/40')}>
                  <div className="absolute inset-0 opacity-70" style={{ background: 'repeating-linear-gradient(90deg, #3987e5 0 2px, transparent 2px 5px)', maskImage: 'linear-gradient(transparent 20%, black 50%, transparent 80%)' }} />
                  {mix.duck && timeline.map((c, i) => c.needs_audio && !c.mute && (
                    <div key={c.shot_id} title="Ducked under dialogue" className="absolute inset-y-0 bg-black/55" style={{ left: starts[i] * pps, width: (c.end - c.start) * pps }} />
                  ))}
                  <span className="relative ml-2 text-[11px] font-semibold">{music.filename.replace(/^_music_/, '')} · {Math.round(mix.music_volume * 100)}%</span>
                </button>
              ) : (
                <button onClick={() => { setSelected({ type: 'music' }); musicInput.current?.click() }}
                  className="flex h-10 items-center gap-1.5 rounded-md border border-dashed border-white/20 px-3 text-xs text-white/60 hover:border-white/50 hover:text-white">
                  {uploading ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add music
                </button>
              )}
            </div>
            {/* T1 title */}
            <div className="flex py-1.5">
              <TrackLabel icon={Type} label="T1" />
              {mix.title ? (
                <div className="relative h-9" style={{ width: total * pps }}>
                  <button onClick={() => setSelected({ type: 'title' })}
                    className={clsx('absolute inset-y-0 truncate rounded-md border-2 bg-brand/80 px-2 text-left text-[11px] font-semibold', selected?.type === 'title' ? 'border-white' : 'border-transparent hover:border-white/50')}
                    style={{ left: titleFrom * pps, width: Math.min(total, mix.title_seconds) * pps }}>
                    {mix.title}
                  </button>
                </div>
              ) : (
                <button onClick={() => { setSelected({ type: 'title' }); setMix((m) => ({ ...m, title: project.name })) }}
                  className="flex h-9 items-center gap-1.5 rounded-md border border-dashed border-white/20 px-3 text-xs text-white/60 hover:border-white/50 hover:text-white">
                  <Plus size={13} /> Add title
                </button>
              )}
            </div>
            {/* Playhead */}
            <div className="pointer-events-none absolute inset-y-0 z-30 w-px bg-brand" style={{ left: HEAD + playhead * pps }}>
              <span className="absolute -left-1.5 top-0 h-3 w-3 rotate-45 bg-brand" />
            </div>
          </div>
        </div>
      </div>
      <input ref={musicInput} type="file" accept="audio/*" className="hidden" onChange={(e) => { e.target.files[0] && uploadMusic(e.target.files[0]); e.target.value = '' }} />
    </div>
  )
}
