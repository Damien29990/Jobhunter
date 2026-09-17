// pathfinding.js — A* on the office tile grid.
// Pure function, no side effects. Returns a list of waypoints (goal exclusive of start).
// # Ref: frontend-animator skill — rAF-driven, time-based interpolation.

function inBounds(grid, x, y) {
  return y >= 0 && y < grid.length && x >= 0 && x < grid[0].length
}

export function isOpen(grid, x, y) {
  return inBounds(grid, x, y) && grid[y][x] !== 1
}

export function nearestWalkable(grid, pos) {
  if (!pos) return pos
  if (isOpen(grid, pos.x, pos.y)) return { x: pos.x, y: pos.y }
  const dirs = [
    [0, 1], [0, -1], [1, 0], [-1, 0],
    [1, 1], [-1, 1], [1, -1], [-1, -1],
    [0, 2], [0, -2], [2, 0], [-2, 0],
  ]
  for (const [dx, dy] of dirs) {
    const nx = pos.x + dx
    const ny = pos.y + dy
    if (isOpen(grid, nx, ny)) return { x: nx, y: ny }
  }
  return { x: pos.x, y: pos.y }
}

export function findPath(grid, start, goal) {
  const s = nearestWalkable(grid, start)
  const g = nearestWalkable(grid, goal)
  if (s.x === g.x && s.y === g.y) return []

  const openSet = [{ ...s, g: 0, h: heuristic(s, g), f: heuristic(s, g), parent: null }]
  const closedSet = new Set()

  while (openSet.length > 0) {
    openSet.sort((a, b) => a.f - b.f)
    const current = openSet.shift()

    if (current.x === g.x && current.y === g.y) {
      const path = []
      let n = current
      while (n.parent) {
        path.unshift({ x: n.x, y: n.y })
        n = n.parent
      }
      return path
    }

    closedSet.add(`${current.x},${current.y}`)

    const dirs = [[0, -1], [0, 1], [-1, 0], [1, 0]]
    for (const [dx, dy] of dirs) {
      const nx = current.x + dx
      const ny = current.y + dy
      if (!isOpen(grid, nx, ny)) continue
      if (closedSet.has(`${nx},${ny}`)) continue

      const gCost = current.g + 1
      const h = heuristic({ x: nx, y: ny }, g)
      const f = gCost + h
      const existingIdx = openSet.findIndex((n) => n.x === nx && n.y === ny)

      if (existingIdx === -1) {
        openSet.push({ x: nx, y: ny, g: gCost, h, f, parent: current })
      } else if (gCost < openSet[existingIdx].g) {
        openSet[existingIdx].g = gCost
        openSet[existingIdx].f = f
        openSet[existingIdx].parent = current
      }
    }
  }

  // No walkable path — stay put rather than clipping through walls.
  return []
}

function heuristic(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y)
}

export function buildInteractionPath(grid, agentKey, deskPositions, workstationPositions, interactionPoints) {
  const desk = deskPositions[agentKey]
  const workstation = workstationPositions[agentKey]
  const waypoints = interactionPoints[agentKey] || []

  const fullPath = []
  let current = desk

  for (const wp of waypoints) {
    const segment = findPath(grid, current, wp)
    fullPath.push(...segment)
    current = wp
  }

  fullPath.push(...findPath(grid, current, workstation))
  return fullPath
}
