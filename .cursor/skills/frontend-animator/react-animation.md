# React Animation — Patterns (2026)

Copy-in patterns for the four tools you'll actually use in React. All examples animate only `transform`/`opacity`. See [performance.md](performance.md) for why.

## 1. Motion (formerly Framer Motion) — the default

Package: `motion` (import from `motion/react`). Declarative, React-native, spring defaults. Use for ~80% of UI motion: enter/exit, layout shifts, gestures, hover/tap.

### Enter/exit with AnimatePresence

```tsx
import { motion, AnimatePresence } from 'motion/react'

function Toast({ show, children }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}      // transform + opacity only
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
```

`AnimatePresence` is required for `exit` to fire — without it, removed nodes vanish instantly.

### Layout animation (shared layout / reordering)

```tsx
import { motion, LayoutGroup } from 'motion/react'

// <motion.div layout> animates position/size when layout changes (sort/filter/reorder).
<motion.div layout className="card" />
```

`layout` animates `transform` under the hood (FLIP technique) — safe for 60fps. Use `LayoutGroup` to coordinate shared-element transitions across siblings.

### While-hover / while-tap micro-interactions

```tsx
<motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.97 }}>
  Click
</motion.button>
```

### Reduced motion (do this once globally)

```tsx
import { MotionConfig } from 'motion/react'

<MotionConfig reducedMotion="user">
  <App />
</MotionConfig>
```

`reducedMotion="user"` makes Motion automatically skip transform/opacity animation when the user has `prefers-reduced-motion: reduce`.

## 2. GSAP + useGSAP — scroll & timelines

Package: `gsap` + `@gsap/react` (provides `useGSAP` for cleanup). Use for scroll-driven storytelling, pinned sections, SVG morph, complex timelines. All plugins free since GSAP 3.13.

```tsx
import { useGSAP } from '@gsap/react'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
gsap.registerPlugin(ScrollTrigger)

function Hero() {
  const ref = useRef(null)
  useGSAP(
    () => {
      gsap.from('.hero-title', { y: 40, opacity: 0, duration: 0.8, ease: 'power3.out' })
      gsap.to('.hero-bg', {
        yPercent: 30,
        ease: 'none',
        scrollTrigger: { trigger: ref.current, start: 'top top', end: 'bottom top', scrub: true },
      })
    },
    { scope: ref } // scopes selectors; cleanup runs on unmount
  )
  return <div ref={ref}>...</div>
}
```

**Why `useGSAP`**: it handles `gsap.killTweensOf` + ScrollTrigger teardown on unmount. Without it, tweents leak across re-renders and ScrollTriggers pile up → jank + memory growth.

**Dynamic import** GSAP so it stays out of the initial bundle:

```tsx
const Hero = lazy(() => import('./Hero')) // Hero imports gsap
```

## 3. React Spring — physics & gestures

Package: `@react-spring/web`. Use for drag, gesture-driven, interruptible motion that should feel elastic. ~18KB.

```tsx
import { useSpring, animated } from '@react-spring/web'

function DragCard() {
  const [{ x, y }, api] = useSpring(() => ({ x: 0, y: 0 }))
  return (
    <animated.div
      style={{ x, y, touchAction: 'none' }}
      onPointerDown={() => api.start({ x: 0, y: 0 })}
    />
  )
}
```

Springs are **interruptible** — a new target mid-animation redirects smoothly, no janky cancel. Ideal for gesture-driven UI. Trade-off: steeper hooks mental model than Motion's props.

## 4. AutoAnimate — list reordering

Package: `@formkit/auto-animate`. One directive, animates add/remove/reorder of children via FLIP. Lowest bundle, zero config.

```tsx
import { useAutoAnimate } from '@formkit/auto-animate'

function KanbanColumn({ items }) {
  const [ref] = useAutoAnimate()
  return (
    <ul ref={ref}>
      {items.map((it) => <li key={it.id}>{it.label}</li>)}
    </ul>
  )
}
```

Great for Kanban columns, todo lists, filter results. Not for choreographed sequences.

## Choosing between them

| You want… | Use |
|-----------|-----|
| One-line enter/exit | Motion `AnimatePresence` |
| Reorder/filter animation | AutoAnimate (lists) or Motion `layout` (shared elements) |
| Scroll-pinned hero / parallax | GSAP `ScrollTrigger` |
| Multi-step timeline (intro sequence) | GSAP `timeline()` |
| Drag that feels physical | React Spring |
| Hover/tap scale | Motion `whileHover` or plain CSS `transition: transform` |
| Mascot that follows cursor | Rive (see below) or React Spring |

## Rive in React — interactive mascots

Package: `@rive-app/react-webgl2`. State machines that react to input/data via hooks. Tiny `.riv` files, GPU.

```tsx
import { useRive, useViewModelInstanceNumber } from '@rive-app/react-webgl2'

function Mascot() {
  const { rive, RiveComponent } = useRive({ src: '/mascot.riv', stateMachines: 'Mascot', autoBind: true })
  const vmi = rive?.viewModelInstance
  const { setValue: setLookX } = useViewModelInstanceNumber('lookX', vmi)
  return (
    <div onPointerMove={(e) => {
      const r = e.currentTarget.getBoundingClientRect()
      setLookX?.(((e.clientX - r.left) / r.width) * 2 - 1))
    }}>
      <RiveComponent />
    </div>
  )
}
```

Use `onRiveReady` (not `onLoad`) for pre-render data binding. Dynamic-import `@rive-app/react-webgl2` — it's heavy.

## Anti-patterns

- ❌ Storing per-frame `x/y` in `useState` → re-renders 60×/s. Use `useRef` + rAF, or a library's animated value.
- ❌ `useEffect(() => { setInterval(...) })` for motion → use `requestAnimationFrame` or a library.
- ❌ Inline `style={{ transition: 'all' }}` → animates `all` properties incl. layout-triggering ones. Name the property: `transition: transform`.
- ❌ Forgetting `AnimatePresence` around conditional children → no exit animation.
- ❌ Calling `gsap.to` in `useEffect` without `useGSAP` → leaked tweens across unmounts.
