// officeGrid.js — tile-based office layout for A* pathfinding.
// 20x12 grid, each tile = 32px. Agents sit on walkable chair tiles when IDLE,
// walk the aisles to workstations when WORKING, and return to their chairs.
// Furniture footprints and interior partitions are obstacles; chairs are not.
// # Ref: frontend-animator skill — animate transform/opacity only.

export const TILE_SIZE = 32
export const GRID_W = 20
export const GRID_H = 12

export const FLOOR = 0
export const WALL = 1
export const DESK = 2
export const WORKSTATION = 3
export const COFFEE = 4
export const MEETING = 5

// Sit tiles — walkable chairs in front of each desk / stamp station.
export const DESK_POSITIONS = {
  milo:  { x: 3,  y: 3 },
  rex:   { x: 9,  y: 3 },
  dana:  { x: 15, y: 3 },
  leo:   { x: 9,  y: 9 },
  clara: { x: 15, y: 9 },
}

export const WORKSTATION_POSITIONS = {
  milo:  { x: 6,  y: 4 },   // north of meeting table
  rex:   { x: 10, y: 5 },   // search station, east of table / north of cooler
  dana:  { x: 12, y: 8 },   // research station
  leo:   { x: 7,  y: 7 },   // beside the printer
  clara: { x: 13, y: 7 },   // audit station
}

// Dana → Rex (job leads), Leo → Dana (dossier), Clara → Leo (CV).
export const INTERACTION_POINTS = {
  milo:  [],
  rex:   [],
  dana:  [{ x: 9, y: 3 }],
  leo:   [{ x: 15, y: 3 }],
  clara: [{ x: 9, y: 9 }],
}

// Occupied tiles relative to each furniture origin. Chairs stay walkable.
export const OCCUPANCY = {
  desk: [[0, 0], [1, 0]],
  stampDesk: [[0, 0], [1, 0]],
  meetingTable: [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0], [5, 0]],
  filingCabinet: [[0, 0], [0, 1]],
  bookshelf: [[0, 0], [0, 1]],
  serverRack: [[0, 0], [0, 1]],
  printer: [[0, 0]],
  waterCooler: [[0, 0]],
  coffeeMachine: [[0, 0]],
  plant: [[0, 0]],
  chair: [],
}

// ASCII row 3 cubicle strip (aisles left at Milo / Rex) and row 9 west block.
export const INTERIOR_WALLS = [
  { x: 5, y: 3 }, { x: 6, y: 3 }, { x: 7, y: 3 },
  { x: 1, y: 9 }, { x: 2, y: 9 }, { x: 3, y: 9 },
  { x: 4, y: 9 }, { x: 5, y: 9 }, { x: 6, y: 9 },
]

// 11 types, 21 pieces — positions match the pixel-office floor plan.
export const FURNITURE_ITEMS = [
  { type: 'desk', x: 2, y: 2, accent: '#a78bfa' },
  { type: 'chair', x: 3, y: 3 },
  { type: 'desk', x: 8, y: 2, accent: '#10b981' },
  { type: 'chair', x: 9, y: 3 },
  { type: 'serverRack', x: 6, y: 1 },
  { type: 'desk', x: 14, y: 2, accent: '#06b6d4' },
  { type: 'chair', x: 15, y: 3 },
  { type: 'filingCabinet', x: 16, y: 1 },
  { type: 'bookshelf', x: 16, y: 4 },
  { type: 'meetingTable', x: 4, y: 5 },
  { type: 'chair', x: 3, y: 5 },
  { type: 'coffeeMachine', x: 3, y: 6 },
  { type: 'plant', x: 4, y: 6 },
  { type: 'waterCooler', x: 10, y: 6 },
  { type: 'plant', x: 13, y: 6 },
  { type: 'printer', x: 6, y: 7 },
  { type: 'desk', x: 8, y: 8, accent: '#f59e0b' },
  { type: 'chair', x: 9, y: 9 },
  { type: 'stampDesk', x: 14, y: 8 },
  { type: 'plant', x: 16, y: 9 },
  { type: 'plant', x: 1, y: 4 },
]

export function buildGrid() {
  const grid = Array.from({ length: GRID_H }, () => Array(GRID_W).fill(FLOOR))

  for (let x = 0; x < GRID_W; x++) {
    grid[0][x] = WALL
    grid[GRID_H - 1][x] = WALL
  }
  for (let y = 0; y < GRID_H; y++) {
    grid[y][0] = WALL
    grid[y][GRID_W - 1] = WALL
  }

  for (const w of INTERIOR_WALLS) {
    grid[w.y][w.x] = WALL
  }

  for (const item of FURNITURE_ITEMS) {
    const occ = OCCUPANCY[item.type] || [[0, 0]]
    for (const [dx, dy] of occ) {
      const x = item.x + dx
      const y = item.y + dy
      if (y >= 0 && y < GRID_H && x >= 0 && x < GRID_W) {
        grid[y][x] = WALL
      }
    }
  }

  return grid
}

export function isWalkable(grid, x, y) {
  if (x < 0 || x >= GRID_W || y < 0 || y >= GRID_H) return false
  return grid[y][x] !== WALL
}

export function gridToPx(pos) {
  return { x: pos.x * TILE_SIZE, y: pos.y * TILE_SIZE }
}

export function pxToGrid(px) {
  return { x: Math.floor(px.x / TILE_SIZE), y: Math.floor(px.y / TILE_SIZE) }
}
