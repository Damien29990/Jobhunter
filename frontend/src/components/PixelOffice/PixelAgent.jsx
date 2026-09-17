// PixelAgent.jsx — 16-bit pixel-art agent rendered as SVG <rect> primitives.
// Offline-safe: pure SVG, no external sprites. Each agent has a themed palette
// and a desk prop (terminal / files / printer / stamps / reception).
//
// Card desks (`embedded`): WORKING walks in place (frames 0-5) then types.
// Living floor: parent passes `moving` from A*; no embedded desk (furniture
// already sits on the floor behind the sprite).

import { useEffect, useState } from 'react'

const CELL = 4
const GRID = 16
const TICK_MS = 180
const WALK_FRAMES = 6

function px(x, y, w, h, fill, opts = {}) {
  return (
    <rect
      key={`${x}-${y}-${w}-${h}-${fill}`}
      x={x * CELL}
      y={y * CELL}
      width={w * CELL}
      height={h * CELL}
      fill={fill}
      shapeRendering="crispEdges"
      {...opts}
    />
  )
}

function Body({ skin, hair, shirt, desk, accent, moving, frame, typing, embedded }) {
  const legOffset = moving ? (frame % 2 === 0 ? 0 : 1) : 0
  const handFrame = typing ? (frame % 2 === 0 ? 0 : 1) : 0
  return (
    <g>
      {px(6, 2, 4, 4, skin)}
      {px(6, 2, 4, 1, hair)}
      {px(5, 3, 1, 2, skin)}
      {px(10, 3, 1, 2, skin)}
      {px(7, 4, 1, 1, '#0b1120')}
      {px(9, 4, 1, 1, '#0b1120')}
      {px(5, 6, 6, 4, shirt)}
      {px(6, 6, 4, 1, accent)}
      {moving ? (
        <>
          {px(4, 7 - legOffset, 1, 3, shirt)}
          {px(11, 7 + legOffset, 1, 3, shirt)}
        </>
      ) : typing ? (
        <>
          {px(5, 8 - handFrame, 1, 1, skin)}
          {px(10, 8 + handFrame, 1, 1, skin)}
        </>
      ) : (
        <>
          {px(4, 7, 1, 3, shirt)}
          {px(11, 7, 1, 3, shirt)}
        </>
      )}
      {moving ? (
        <>
          {px(6, 10, 1, 2 + legOffset, '#334155')}
          {px(9, 10, 1, 2 - legOffset, '#334155')}
        </>
      ) : (
        <>
          {embedded && px(4, 10, 8, 1, '#1e293b')}
          {px(6, 10, 1, 3, '#334155')}
          {px(9, 10, 1, 3, '#334155')}
        </>
      )}
      {embedded && !moving && (
        <>
          {px(3, 13, 10, 1, desk)}
          {px(3, 14, 1, 2, '#475569')}
          {px(12, 14, 1, 2, '#475569')}
        </>
      )}
    </g>
  )
}

function Computer({ accent, working, frame }) {
  const screenOn = working ? (frame % 2 === 0) : false
  return (
    <g>
      {px(5, 9, 4, 1, '#1e293b')}
      {px(6, 10, 2, 1, screenOn ? '#0b1120' : '#0f172a')}
      {px(6, 10, 2, 1, screenOn ? accent : '#0e7c5e')}
      {screenOn && px(7, 10, 1, 1, accent, { className: 'animate-blink' })}
      {px(5, 12, 1, 1, '#475569')}
      {px(6, 12, 1, 1, '#334155')}
      {px(7, 12, 1, 1, '#475569')}
      {px(8, 12, 1, 1, '#334155')}
      {px(9, 12, 1, 1, '#475569')}
      {px(10, 12, 1, 1, '#334155')}
    </g>
  )
}

function DeskProp({ prop, accent, working, frame }) {
  if (prop === 'reception') {
    return (
      <g>
        {px(4, 13, 8, 1, '#1e293b')}
        {px(4, 14, 1, 2, '#475569')}
        {px(11, 14, 1, 2, '#475569')}
        {px(5, 11, 3, 1, '#e2e8f0')}
        {px(5, 11, 3, 1, accent)}
        {px(8, 11, 3, 1, '#cbd5e1')}
        {px(10, 10, 1, 1, '#10b981')}
        {px(10, 11, 1, 1, '#10b981')}
        {working && (
          <g className="animate-bob">
            {px(9, 9, 2, 1, '#a78bfa', { opacity: 0.7 })}
          </g>
        )}
      </g>
    )
  }
  if (prop === 'terminal') {
    return (
      <g>
        {px(5, 11, 6, 2, '#0b1120')}
        {px(6, 11, 4, 1, working ? '#10b981' : '#0e7c5e')}
        {working && px(7, 11, 1, 1, '#10b981', { className: 'animate-blink' })}
        {px(5, 12, 1, 1, '#475569')}
        {px(6, 12, 1, 1, '#334155')}
        {px(7, 12, 1, 1, '#475569')}
        {px(8, 12, 1, 1, '#334155')}
        {px(9, 12, 1, 1, '#475569')}
        {px(10, 12, 1, 1, '#334155')}
      </g>
    )
  }
  if (prop === 'files') {
    return (
      <g>
        {px(5, 11, 2, 2, '#e2e8f0')}
        {px(5, 11, 2, 1, accent)}
        {px(8, 11, 2, 2, '#cbd5e1')}
        {px(8, 11, 2, 1, '#94a3b8')}
        {working && (
          <g className="animate-bob">
            {px(11, 10, 2, 2, 'none', { stroke: accent, strokeWidth: 0.6, fill: 'none' })}
          </g>
        )}
        {working && <Computer accent={accent} working={working} frame={frame} />}
      </g>
    )
  }
  if (prop === 'printer') {
    return (
      <g>
        {px(5, 11, 6, 1, '#475569')}
        {px(5, 12, 6, 1, '#334155')}
        {working && px(6, 13, 4, 1, '#e2e8f0', { className: 'animate-bob' })}
        {working && <Computer accent={accent} working={working} frame={frame} />}
      </g>
    )
  }
  if (prop === 'stamps') {
    return (
      <g>
        {px(5, 11, 2, 2, '#e2e8f0')}
        {px(8, 11, 2, 2, '#cbd5e1')}
        {working && (
          <g className="animate-stamp" style={{ transformOrigin: '46px 50px' }}>
            {px(11, 10, 2, 2, accent)}
          </g>
        )}
        {working && <Computer accent={accent} working={working} frame={frame} />}
      </g>
    )
  }
  return null
}

const PALETTES = {
  milo:  { skin: '#e0b58e', hair: '#4a1d6b', shirt: '#7c3aed', desk: '#1e293b', accent: '#a78bfa', prop: 'reception' },
  rex:   { skin: '#f1c9a5', hair: '#3b2417', shirt: '#0e7c5e', desk: '#1e293b', accent: '#10b981', prop: 'terminal' },
  dana:  { skin: '#e8b58e', hair: '#5b3a29', shirt: '#0e6f86', desk: '#1e293b', accent: '#06b6d4', prop: 'files' },
  leo:   { skin: '#f1c9a5', hair: '#1e1e1e', shirt: '#9a6b12', desk: '#1e293b', accent: '#f59e0b', prop: 'printer' },
  clara: { skin: '#e8b58e', hair: '#7a1f3d', shirt: '#9a1f3d', desk: '#1e293b', accent: '#f43f5e', prop: 'stamps' },
}

export default function PixelAgent({
  agentKey,
  state = 'IDLE',
  size = 96,
  moving: movingProp,
  embedded = true,
}) {
  const p = PALETTES[agentKey] || PALETTES.rex
  const working = state === 'WORKING'
  const failed = state === 'FAILED'
  const driven = movingProp !== undefined

  const [frame, setFrame] = useState(0)
  useEffect(() => {
    const reduced = typeof window !== 'undefined'
      && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
    const active = driven ? (movingProp || working) : working
    if (!active || reduced) {
      setFrame(0)
      return undefined
    }
    let raf
    let last = 0
    const loop = (now) => {
      if (!last) last = now
      if (now - last >= TICK_MS) {
        setFrame((f) => (f + 1) % 24)
        last = now
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [working, driven, movingProp])

  const moving = driven ? !!movingProp : (working && frame < WALK_FRAMES)
  const typing = !moving && working
  const bodyClass = moving ? '' : (working ? 'animate-bob' : '')
  const ringColor = failed ? '#f43f5e' : working ? p.accent : '#334155'

  return (
    <svg
      viewBox={`0 0 ${GRID * CELL} ${GRID * CELL}`}
      width={size}
      height={size}
      className="pixelated select-none"
      style={{ imageRendering: 'pixelated' }}
    >
      <ellipse
        cx={GRID * CELL / 2}
        cy={(GRID - 1) * CELL + 2}
        rx={26}
        ry={5}
        fill={ringColor}
        opacity={working || failed ? 0.5 : 0.2}
      />
      <g className={bodyClass} style={{ transformOrigin: 'center' }}>
        <Body {...p} moving={moving} frame={frame} typing={typing} embedded={embedded} />
        {embedded && !moving && (
          <DeskProp prop={p.prop} accent={p.accent} working={working} frame={frame} />
        )}
      </g>
      {failed && (
        <g>
          {px(11, 0, 1, 1, '#f43f5e')}
          {px(13, 0, 1, 1, '#f43f5e')}
          {px(12, 1, 1, 1, '#f43f5e')}
        </g>
      )}
    </svg>
  )
}
