// OfficeFurniture.jsx — pixel-art SVG furniture for the living office floor.
// Renders into its own <svg> so it paints on the HTML floor (a <g> inside a
// <div> is ignored by the browser). pointer-events none — agents stay clickable.
// # Ref: frontend-animator skill — transform/opacity only, crisp-edges.

import {
  FURNITURE_ITEMS, INTERIOR_WALLS, GRID_W, GRID_H, TILE_SIZE,
} from '../../lib/officeGrid'

const C = 3

function makeR() {
  let i = 0
  return function r(x, y, w, h, fill, opts = {}) {
    return (
      <rect
        key={i++}
        x={x * C}
        y={y * C}
        width={w * C}
        height={h * C}
        fill={fill}
        shapeRendering="crispEdges"
        {...opts}
      />
    )
  }
}

function Desk({ x, y, accent = '#475569' }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 64 32" width={64} height={32}>
        {r(1, 8, 20, 3, '#334155')}
        {r(1, 8, 20, 1, accent)}
        {r(1, 11, 2, 4, '#1e293b')}
        {r(19, 11, 2, 4, '#1e293b')}
        {r(7, 2, 8, 6, '#0b1120')}
        {r(8, 3, 6, 4, '#0e7c5e')}
        {r(9, 4, 4, 2, accent, { opacity: 0.7 })}
        {r(10, 8, 2, 1, '#475569')}
      </svg>
    </g>
  )
}

function Chair({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 32" width={32} height={32}>
        {r(4, 1, 8, 2, '#1e293b')}
        {r(3, 4, 10, 3, '#334155')}
        {r(4, 7, 1, 3, '#475569')}
        {r(11, 7, 1, 3, '#475569')}
        {r(3, 10, 1, 1, '#64748b')}
        {r(12, 10, 1, 1, '#64748b')}
      </svg>
    </g>
  )
}

function MeetingTable({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 192 32" width={192} height={32}>
        {r(0, 0, 64, 2, '#e2e8f0', { opacity: 0.55 })}
        {r(2, 0, 60, 1, '#94a3b8', { opacity: 0.4 })}
        {r(2, 6, 60, 8, '#334155')}
        {r(2, 6, 60, 1, '#64748b')}
        {r(2, 14, 3, 3, '#1e293b')}
        {r(59, 14, 3, 3, '#1e293b')}
        {r(8, 4, 4, 2, '#1e293b')}
        {r(24, 4, 4, 2, '#1e293b')}
        {r(40, 4, 4, 2, '#1e293b')}
        {r(52, 4, 4, 2, '#1e293b')}
      </svg>
    </g>
  )
}

function FilingCabinet({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 48" width={32} height={48}>
        {r(3, 2, 8, 14, '#475569')}
        {r(3, 2, 8, 1, '#64748b')}
        {r(4, 4, 6, 4, '#334155')}
        {r(4, 9, 6, 4, '#334155')}
        {r(6, 5, 2, 1, '#94a3b8')}
        {r(6, 10, 2, 1, '#94a3b8')}
      </svg>
    </g>
  )
}

function Printer({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 32" width={32} height={32}>
        {r(2, 5, 12, 8, '#475569')}
        {r(2, 5, 12, 1, '#64748b')}
        {r(4, 2, 8, 3, '#cbd5e1')}
        {r(5, 7, 6, 2, '#0b1120')}
        {r(6, 8, 2, 1, '#10b981', { opacity: 0.7 })}
        {r(9, 8, 1, 1, '#f59e0b')}
        {r(3, 13, 10, 2, '#334155')}
        {r(4, 14, 8, 1, '#e2e8f0', { opacity: 0.65 })}
      </svg>
    </g>
  )
}

function WaterCooler({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 32" width={32} height={32}>
        {r(5, 1, 6, 6, '#1e3a5f', { opacity: 0.75 })}
        {r(6, 2, 4, 4, '#38bdf8', { opacity: 0.55 })}
        {r(4, 7, 8, 7, '#475569')}
        {r(4, 7, 8, 1, '#64748b')}
        {r(5, 11, 1, 2, '#94a3b8')}
        {r(10, 11, 1, 2, '#94a3b8')}
        {r(4, 14, 8, 1, '#334155')}
      </svg>
    </g>
  )
}

function CoffeeMachine({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 32" width={32} height={32}>
        {r(4, 3, 8, 10, '#475569')}
        {r(4, 3, 8, 1, '#64748b')}
        {r(5, 5, 6, 3, '#0b1120')}
        {r(6, 6, 4, 1, '#f59e0b', { opacity: 0.7 })}
        {r(7, 10, 2, 2, '#334155')}
        {r(6, 13, 4, 2, '#e2e8f0', { opacity: 0.6 })}
      </svg>
    </g>
  )
}

function Plant({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 32" width={32} height={32}>
        {r(5, 8, 6, 4, '#92400e')}
        {r(5, 8, 6, 1, '#a16207')}
        {r(4, 4, 3, 4, '#10b981')}
        {r(8, 3, 3, 5, '#0e7c5e')}
        {r(6, 2, 2, 3, '#10b981')}
        {r(10, 5, 2, 3, '#0e7c5e')}
      </svg>
    </g>
  )
}

function ServerRack({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 48" width={32} height={48}>
        {r(3, 2, 8, 14, '#1e293b')}
        {r(3, 2, 8, 1, '#334155')}
        {r(4, 4, 6, 2, '#0b1120')}
        {r(5, 5, 1, 1, '#10b981', { className: 'animate-blink' })}
        {r(7, 5, 1, 1, '#f59e0b', { className: 'animate-blink', style: { animationDelay: '0.2s' } })}
        {r(4, 7, 6, 2, '#0b1120')}
        {r(5, 8, 1, 1, '#06b6d4', { className: 'animate-blink', style: { animationDelay: '0.4s' } })}
        {r(7, 8, 1, 1, '#10b981', { className: 'animate-blink', style: { animationDelay: '0.6s' } })}
        {r(4, 10, 6, 2, '#0b1120')}
        {r(5, 11, 1, 1, '#f43f5e', { className: 'animate-blink', style: { animationDelay: '0.8s' } })}
        {r(7, 11, 1, 1, '#10b981', { className: 'animate-blink', style: { animationDelay: '1s' } })}
      </svg>
    </g>
  )
}

function Bookshelf({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 48" width={32} height={48}>
        {r(2, 1, 10, 14, '#334155')}
        {r(3, 3, 8, 1, '#1e293b')}
        {r(3, 7, 8, 1, '#1e293b')}
        {r(3, 11, 8, 1, '#1e293b')}
        {r(3, 4, 2, 3, '#10b981')}
        {r(5, 4, 2, 3, '#f59e0b')}
        {r(7, 4, 2, 3, '#06b6d4')}
        {r(9, 4, 1, 3, '#f43f5e')}
        {r(3, 8, 2, 3, '#a78bfa')}
        {r(5, 8, 2, 3, '#0e7c5e')}
        {r(7, 8, 3, 3, '#f59e0b')}
        {r(3, 12, 2, 2, '#06b6d4')}
        {r(5, 12, 2, 2, '#10b981')}
        {r(7, 12, 3, 2, '#a78bfa')}
      </svg>
    </g>
  )
}

function StampDesk({ x, y }) {
  const r = makeR()
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 64 32" width={64} height={32}>
        {r(1, 8, 20, 3, '#334155')}
        {r(1, 11, 2, 4, '#1e293b')}
        {r(19, 11, 2, 4, '#1e293b')}
        {r(3, 4, 2, 4, '#f43f5e')}
        {r(6, 4, 2, 4, '#a78bfa')}
        {r(9, 4, 2, 4, '#f59e0b')}
        {r(12, 4, 2, 4, '#10b981')}
        {r(15, 6, 4, 2, '#1e293b')}
        {r(2, 2, 1, 5, '#475569')}
        {r(2, 1, 2, 1, '#f59e0b', { opacity: 0.55 })}
        {r(16, 3, 2, 2, '#334155')}
      </svg>
    </g>
  )
}

function WallTile({ x, y, door = false }) {
  const r = makeR()
  const fill = door ? '#3f2e1f' : '#1e293b'
  const top = door ? '#92400e' : '#334155'
  return (
    <g transform={`translate(${x * 32}, ${y * 32})`}>
      <svg viewBox="0 0 32 32" width={32} height={32}>
        {r(0, 0, 16, 16, fill)}
        {r(0, 0, 16, 2, top)}
      </svg>
    </g>
  )
}

const RENDERERS = {
  desk: Desk,
  chair: Chair,
  meetingTable: MeetingTable,
  filingCabinet: FilingCabinet,
  printer: Printer,
  waterCooler: WaterCooler,
  coffeeMachine: CoffeeMachine,
  plant: Plant,
  serverRack: ServerRack,
  bookshelf: Bookshelf,
  stampDesk: StampDesk,
}

function perimeterWalls() {
  const tiles = []
  for (let x = 0; x < GRID_W; x++) {
    tiles.push({ x, y: 0, door: x === 2 || x === 3 })
    tiles.push({ x, y: GRID_H - 1 })
  }
  for (let y = 1; y < GRID_H - 1; y++) {
    tiles.push({ x: 0, y })
    tiles.push({ x: GRID_W - 1, y })
  }
  return tiles
}

export default function OfficeFurniture() {
  return (
    <svg
      className="absolute inset-0 pointer-events-none pixelated"
      width={GRID_W * TILE_SIZE}
      height={GRID_H * TILE_SIZE}
      style={{ imageRendering: 'pixelated', pointerEvents: 'none', zIndex: 0 }}
    >
      {perimeterWalls().map((w) => (
        <WallTile key={`pw-${w.x}-${w.y}`} x={w.x} y={w.y} door={w.door} />
      ))}
      {INTERIOR_WALLS.map((w) => (
        <WallTile key={`iw-${w.x}-${w.y}`} x={w.x} y={w.y} />
      ))}
      {FURNITURE_ITEMS.map((item, i) => {
        const Renderer = RENDERERS[item.type]
        return Renderer ? <Renderer key={`f-${item.type}-${i}`} {...item} /> : null
      })}
    </svg>
  )
}
