# Animation Performance — 60fps, will-change, jank (2026)

The stability and smoothness reference. Goal: every frame under 16.6ms (60fps), no dropped frames, no GPU memory leaks.

## The rendering pipeline & why transform/opacity win

Every paint goes through **Layout → Paint → Composite**. Only two properties skip Layout and Paint and run on the **compositor thread (GPU)**:

| Property | Path | Cost |
|----------|------|------|
| `width/height/top/left/margin/font-size` | Layout → Paint → Composite | Highest |
| `color/background/box-shadow` | Paint → Composite | Medium |
| **`transform`** (translate/scale/rotate/skew), **`opacity`**, `filter` | Composite only | Lowest |

`transform: translateX(100px)` moves an already-painted layer on the GPU. `left: 100px` recalculates layout on the main thread every frame. The visual result is identical; the cost is not.

**Rule: animate `transform` and `opacity`. Use `translateX/Y` instead of `left/top`, `scale` instead of `width/height`.**

## will-change lifecycle — promote late, demote early

`will-change` is a **scheduling hint**, not a performance switch. It tells the browser to pre-promote an element to its own GPU layer during idle time, so the first animated frame doesn't stutter on promotion. Each promoted layer consumes **VRAM**, so overuse causes memory pressure that *itself* degrades performance.

```css
.modal { will-change: transform, opacity; }   /* only if about to animate */
```

```js
// Promote just before animating
el.style.willChange = 'transform'
// ...animation runs...
el.addEventListener('transitionend', () => {
  requestAnimationFrame(() => {            // wait one frame so compositor presents final frame
    el.style.willChange = 'auto'          // demote → release VRAM
  })
}, { once: true })
})
```

Discipline:
- **Don't** set `will-change` globally or on every element "just in case" — the browser already optimizes cheap properties.
- **Don't** set `will-change: all` — name the property.
- **Do** remove it after the animation ends. Leaving `will-change` set post-animation is the **single most common source of retained GPU buffers**.
- **Don't** demote mid-animation (`will-change: auto` mid-animation discards the layer and re-promotes next frame → visible hitch). Demote only after completion.
- For scroll-driven motion, scope promotion with `IntersectionObserver` + `rootMargin: 300px` so only near-viewport elements hold a layer.

## requestAnimationFrame, never setInterval

- `requestAnimationFrame` syncs to the display refresh and **pauses when the tab is hidden** (saves CPU/battery).
- `setInterval` does neither — it fires in the background, desyncs from repaints, and tears.
- For looping CSS animations, use CSS `animation` (compositor-driven), not a JS interval.

## Batch DOM reads and writes (avoid layout thrash)

Reading `offsetWidth`/`scrollTop`/`getBoundingClientRect` forces a **synchronous layout**. Interleaving reads and writes forces layout every access:

```js
// BAD: layout thrash — layout recalced N times
els.forEach((el) => { el.style.left = el.offsetLeft + 10 + 'px' })  // read+write each iter

// GOOD: read all, then write all — one layout
const positions = els.map((el) => el.offsetLeft + 10)
els.forEach((el, i) => { el.style.left = positions[i] + 'px' })
```

## prefers-reduced-motion — always honor it

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- In Motion: wrap the app in `<MotionConfig reducedMotion="user">`.
- In GSAP: `gsap.ticker.lagSmoothing(0)` and gate non-essential tweens behind a `matchMedia('(prefers-reduced-motion: no-preference)')` check.
- Keep **functional** motion (state changes needed to understand the UI, e.g. a panel opening) — disable only **decorative** motion.

## Jank debugging — the four-panel workflow (Chrome DevTools)

1. **Performance** → Record the interaction. Look for red frames and long **Layout**/**Paint**/**Recalculate Style** blocks. A frame > 16.6ms is a drop.
2. **Rendering** → enable **Paint flashing** (highlights repainted areas) and the **FPS meter**. If paint flashes cover the whole screen, you're repainting too much.
3. **Animations** → inspect the active transition/animation; check it animates only transform/opacity.
4. **Layers** → count promoted layers. Each holds VRAM ≈ `width × height × 4 bytes × (DPR)²`. Hundreds of layers = VRAM pressure. Cross-reference with `will-change` declarations; demote anything no longer animating.

Targets:
- 95th-percentile frame duration < 16.6ms.
- No Layout/Paint tasks during animation playback (only Composite).
- Zero GPU memory growth over a 10-minute soak.

## Common jank causes → fixes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| First-frame hitch | Layer promoted mid-animation | `will-change` before animating |
| Sustained jank | Animating layout properties | Switch to `transform`/`opacity` |
| Jank after scroll | `scroll` listener doing layout | CSS scroll-driven animations or `IntersectionObserver` |
| Growing memory | `will-change` never removed | Demote on `transitionend` |
| Slow on mobile, fine on desktop | Too many GPU layers | Reduce layers; test on mid-range device |
| 144Hz runs 2.4× faster | Frame-count motion | Delta-time (`dt`) |
| Background tab explodes CPU | `setInterval` loop | `requestAnimationFrame` |

## CSS scroll-driven animations (2026 native)

Prefer the native CSS scroll-driven API over JS scroll listeners — it runs off the main thread:

```css
@keyframes fade-in { from { opacity: 0 } to { opacity: 1 } }
.reveal {
  animation: fade-in both;
  animation-timeline: view();
  animation-range: entry 0% cover 40%;
}
```

No JS, no scroll listener, no main-thread work. Fallback to `IntersectionObserver` + a class toggle where unsupported.

## Web Animations API (WAAPI) — when you need JS control

Gives rAF-level control (play/pause/cancel/reverse/seek) with compositor-thread execution for transform/opacity:

```js
const anim = el.animate(
  [{ transform: 'translateX(0)' }, { transform: 'translateX(100px)' }],
  { duration: 400, easing: 'ease-out', fill: 'forwards' }
)
// anim.pause(); anim.reverse(); anim.cancel();
```

Good for reversible, sequenced, exit animations where CSS transitions are too rigid and a library is overkill.

## Bundle discipline

- Dynamic-import heavy libs (GSAP, Rive, Lottie) so they stay out of the initial bundle:
  ```js
  const Rive = lazy(() => import('@rive-app/react-webgl2'))
  ```
- For a single hover effect, plain CSS beats every library (zero JS):
  ```css
  .btn { transition: transform 150ms ease-out; }
  .btn:hover { transform: scale(1.04); }
  ```
