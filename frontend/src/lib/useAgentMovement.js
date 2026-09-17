// useAgentMovement.js — A* pathfinding for living-floor sprites.
// Pixel positions live in a ref and are written to DOM transform (not React
// state) every frame so the 2.5s status poll cannot snap agents back to desks.
// # Ref: frontend-animator skill — rAF, time-based, transform-only.

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DESK_POSITIONS, WORKSTATION_POSITIONS, INTERACTION_POINTS,
  buildGrid, gridToPx, TILE_SIZE,
} from './officeGrid'
import { buildInteractionPath, findPath, nearestWalkable } from './pathfinding'

const WALK_SPEED = 60 // px per second

function initialPositions() {
  const pos = {}
  for (const [key, desk] of Object.entries(DESK_POSITIONS)) {
    pos[key] = { ...gridToPx(desk), moving: false }
  }
  return pos
}

function initialMoving() {
  return Object.fromEntries(Object.keys(DESK_POSITIONS).map((k) => [k, false]))
}

export function useAgentMovement(agentStatus) {
  const gridRef = useRef(buildGrid())
  const posRef = useRef(initialPositions())
  const nodesRef = useRef({})
  const pathRef = useRef({})
  const pathIdxRef = useRef({})
  const prevStatesRef = useRef({})
  const rafRef = useRef(null)
  const lastTimeRef = useRef(0)
  const [movingMap, setMovingMap] = useState(initialMoving)

  const reducedMotion = typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches

  const applyTransform = useCallback((key) => {
    const node = nodesRef.current[key]
    const pos = posRef.current[key]
    if (!node || !pos) return
    node.style.transform = `translate(${pos.x}px, ${pos.y}px)`
  }, [])

  const bindersRef = useRef({})
  const bindAgent = useCallback((key) => {
    if (!bindersRef.current[key]) {
      bindersRef.current[key] = (el) => {
        nodesRef.current[key] = el
        if (el) applyTransform(key)
      }
    }
    return bindersRef.current[key]
  }, [applyTransform])

  const snapTo = useCallback((key, gridPos, moving) => {
    posRef.current[key] = { ...gridToPx(gridPos), moving }
    applyTransform(key)
  }, [applyTransform])

  const setMoving = useCallback((key, moving) => {
    const cur = posRef.current[key]
    if (cur) posRef.current[key] = { ...cur, moving }
    setMovingMap((prev) => (prev[key] === moving ? prev : { ...prev, [key]: moving }))
  }, [])

  const ensureLoop = useCallback(() => {
    if (rafRef.current) return

    const tick = (now) => {
      const dt = lastTimeRef.current ? (now - lastTimeRef.current) / 1000 : 0
      lastTimeRef.current = now
      const step = WALK_SPEED * Math.min(dt, 0.05)

      for (const [key, path] of Object.entries(pathRef.current)) {
        if (!path || path.length === 0) {
          delete pathRef.current[key]
          setMoving(key, false)
          continue
        }
        const idx = pathIdxRef.current[key] || 0
        if (idx >= path.length) {
          delete pathRef.current[key]
          const cur = posRef.current[key]
          if (cur) posRef.current[key] = { ...cur, moving: false }
          applyTransform(key)
          setMoving(key, false)
          continue
        }

        const target = gridToPx(path[idx])
        const curr = posRef.current[key]
        const dx = target.x - curr.x
        const dy = target.y - curr.y
        const dist = Math.sqrt(dx * dx + dy * dy)

        if (dist <= step || dist < 0.5) {
          posRef.current[key] = { ...target, moving: true }
          pathIdxRef.current[key] = idx + 1
        } else {
          posRef.current[key] = {
            x: curr.x + (dx / dist) * step,
            y: curr.y + (dy / dist) * step,
            moving: true,
          }
        }
        applyTransform(key)
      }

      const stillMoving = Object.values(pathRef.current).some((p) => p && p.length > 0)
      if (stillMoving) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        rafRef.current = null
        lastTimeRef.current = 0
      }
    }

    lastTimeRef.current = 0
    rafRef.current = requestAnimationFrame(tick)
  }, [applyTransform, setMoving])

  useEffect(() => {
    if (!agentStatus) return
    const grid = gridRef.current

    for (const key of Object.keys(DESK_POSITIONS)) {
      const s = agentStatus[key]
      const prevState = prevStatesRef.current[key]
      const currState = s?.state || 'IDLE'
      const desk = DESK_POSITIONS[key]
      const workstation = WORKSTATION_POSITIONS[key]
      if (!desk || !workstation) {
        prevStatesRef.current[key] = currState
        continue
      }

      const pathing = !!(pathRef.current[key] && pathRef.current[key].length > 0)
      const at = (gridPos) => {
        const p = posRef.current[key]
        if (!p) return false
        const t = gridToPx(gridPos)
        return Math.hypot(p.x - t.x, p.y - t.y) < TILE_SIZE * 0.6
      }

      if (currState === 'WORKING') {
        // Level-triggered: walk to the workstation whenever WORKING,
        // even if we missed the IDLE → WORKING edge (job drawer, pipeline, scheduler).
        if (!pathing && !at(workstation)) {
          const path = buildInteractionPath(
            grid, key,
            DESK_POSITIONS, WORKSTATION_POSITIONS, INTERACTION_POINTS,
          )
          if (reducedMotion || path.length === 0) {
            snapTo(key, workstation, false)
            setMoving(key, false)
          } else {
            pathRef.current[key] = path
            pathIdxRef.current[key] = 0
            setMoving(key, true)
            ensureLoop()
          }
        }
      } else if (prevState === 'WORKING' && currState !== 'WORKING') {
        const fromPx = posRef.current[key]
        const fromGrid = nearestWalkable(grid, {
          x: Math.round(fromPx.x / TILE_SIZE),
          y: Math.round(fromPx.y / TILE_SIZE),
        })
        const directPath = findPath(grid, fromGrid, desk)
        if (reducedMotion || directPath.length === 0) {
          snapTo(key, desk, false)
          setMoving(key, false)
        } else {
          pathRef.current[key] = directPath
          pathIdxRef.current[key] = 0
          setMoving(key, true)
          ensureLoop()
        }
      }

      prevStatesRef.current[key] = currState
    }
  }, [agentStatus, reducedMotion, ensureLoop, setMoving, snapTo])

  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
  }, [])

  return { bindAgent, movingMap, posRef }
}
