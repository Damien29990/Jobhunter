// OfficeProps.jsx — ambient office decorations rendered as SVG <rect>
// primitives (no external assets). Purely decorative: a wall clock,
// a water cooler, and a potted plant. Drop this into the OfficeScene
// background (behind the agents) to make the office feel alive.
//
// All props are drawn on the same 16x16 grid as PixelAgent, at CELL=4 units.
// Render at a larger size since they're background scenery.

const CELL = 4
const GRID = 16

function px(x, y, w, h, fill, opts = {}) {
  return (
    <rect
      key={`amb-${x}-${y}-${w}-${h}-${fill}`}
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

export default function OfficeProps({ size = 96 }) {
  return (
    <svg
      viewBox={`0 0 ${GRID * CELL} ${GRID * CELL}`}
      width={size}
      height={size}
      className="pixelated select-none pointer-events-none"
      style={{ imageRendering: 'pixelated', opacity: 0.5 }}
    >
      {/* Wall clock — top-right of the office */}
      <g>
        {/* clock body */}
        {px(12, 1, 3, 3, '#1e293b')}
        {/* clock face */}
        {px(13, 2, 1, 1, '#0b1120')}
        {/* 12 marker */}
        {px(13, 2, 1, 1, '#cbd5e1')}
        {px(13, 4, 1, 1, '#cbd5e1')}
        {px(14, 3, 1, 1, '#cbd5e1')}
        {/* 3 marker */}
        {px(15, 2, 1, 1, '#cbd5e1')}
        {/* hands — tick (static decorative; the real time is in the header) */}
        {px(13, 3, 1, 3, '#94a3b8')}
        {px(14, 3, 1, 1, '#94a3b8')}
      </g>

      {/* Water cooler — bottom-left corner */}
      <g>
        {/* cooler body */}
        {px(1, 12, 2, 3, '#1e293b')}
        {/* water jug */}
        {px(1, 13, 2, 1, '#06b6d4')}
        {px(2, 13, 1, 1, '#06b6d4')}
        {/* two cups */}
        {px(1, 14, 1, 1, '#cbd5e1')}
        {px(2, 14, 1, 1, '#cbd5e1')}
        {/* water level */}
        {px(1, 13, 2, 1, '#0e6f86')}
      </g>

      {/* Potted plant — bottom-right corner */}
      <g>
        {/* pot */}
        {px(13, 12, 2, 3, '#7c3aed')}
        {px(13, 15, 2, 1, '#4a1d6b')}
        {/* soil */}
        {px(13, 14, 2, 1, '#3b2417')}
        {/* leaves */}
        {px(13, 11, 1, 1, '#10b981')}
        {px(14, 11, 1, 1, '#10b981')}
        {px(13, 12, 1, 1, '#10b981')}
      </g>
    </svg>
  )
}
