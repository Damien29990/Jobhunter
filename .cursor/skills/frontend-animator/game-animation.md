# Game Animation — Canvas, rAF, Sprites (2026)

Browser game animation fundamentals. The whole skill hinges on `requestAnimationFrame` + **delta-time** so motion is frame-rate-independent (identical on 60Hz and 144Hz). Works in Vanilla JS and inside React (via a ref + effect).

## The canonical rAF loop (delta-time)

```js
let last = performance.now()
function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.1) // seconds, capped to avoid jumps after tab switch
  last = now
  update(dt)   // advance state by dt
  render()     // draw current state
  requestAnimationFrame(frame)
}
requestAnimationFrame(frame)
```

Key points:
- `requestAnimationFrame` syncs to the display refresh and **pauses when the tab is hidden** (saves CPU/battery). Never `setInterval`.
- Cap `dt` (e.g. 0.1s). When a user returns to a backgrounded tab, the elapsed time is huge; without a cap, entities teleport.
- **Update by `dt`, not by frame count** — `x += speed * dt`, not `x += 2`. This is what makes 60Hz and 144Hz behave the same.

## Time-based sprite animation (frame-rate-independent)

A sprite sheet is a row of equal-size frames. Advance frames using a delta-time accumulator, not a counter:

```js
class AnimatedSprite {
  constructor(image, frameWidth, frameHeight, frameCount, fps = 10) {
    this.image = image
    this.frameWidth = frameWidth
    this.frameHeight = frameHeight
    this.frameCount = frameCount
    this.frameDuration = 1 / fps   // seconds per frame
    this.currentFrame = 0
    this.elapsed = 0
  }
  update(dt) {
    this.elapsed += dt
    while (this.elapsed >= this.frameDuration) {   // while-loop handles catch-up
      this.currentFrame = (this.currentFrame + 1) % this.frameCount
      this.elapsed -= this.frameDuration
    }
  }
  draw(ctx, x, y) {
    ctx.drawImage(
      this.image,
      this.currentFrame * this.frameWidth, 0,    // source x, y (clip from sheet)
      this.frameWidth, this.frameHeight,         // source w, h
      Math.round(x), Math.round(y),               // dest x, y (round to avoid blur)
      this.frameWidth, this.frameHeight            // dest w, h
    )
  }
}
```

- The **9-argument `drawImage`** clips one frame out of the sheet — one draw call per sprite.
- `while` (not `if`) so a long `dt` still advances the right number of frames.
- `Math.round` on dest coords keeps pixels aligned (no sub-pixel smear).

## Pixel-perfect setup

```js
const canvas = document.getElementById('game')
const ctx = canvas.getContext('2d')
const dpr = window.devicePixelRatio || 1
canvas.width = LOGICAL_W * dpr     // attributes, not CSS, to avoid blur
canvas.height = LOGICAL_H * dpr
canvas.style.width = LOGICAL_W + 'px'
canvas.style.height = LOGICAL_H + 'px'
ctx.imageSmoothingEnabled = false  // hard pixels for pixel art
```

- Size the canvas with its `width`/`height` **attributes** × `devicePixelRatio`; CSS sizes the element. Setting only CSS blurs the bitmap.
- `imageSmoothingEnabled = false` is **critical for pixel art**. Leave it `true` only for anti-aliased art.

## Sprite atlas (one draw call per sprite)

Pack all frames for all characters into one atlas image. This:
- Minimizes draw calls and GPU state changes (one texture, many clips).
- Lets you batch all `drawImage` calls in one `render()` pass.
- Tools: TexturePacker, Shoebox, or `spritesheet-js`. PixiJS/Phaser load atlases natively.

## Asset loading before the loop starts

Images load async; Canvas silently ignores `drawImage` with an unloaded image (no error, just nothing renders). Wait for them:

```js
function loadImg(src) {
  return new Promise((res, rej) => {
    const img = new Image()
    img.onload = () => res(img)
    img.onerror = rej
    img.src = src
  })
}
const [hero, enemy] = await Promise.all([loadImg('/hero.png'), loadImg('/enemy.png')])
requestAnimationFrame(frame) // start only after assets resolve
```

## Easing for game feel ("juice")

Linear motion feels dead. Apply easing to non-physical motion (UI tweens, camera, hit flashes):

```js
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)
const easeOutBack = (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2) }
// t in [0,1] — drive with a tween's elapsed/duration
```

For physics (jumping, projectiles), use real integration (`v += g * dt; y += v * dt`), not easing — easing lies about physics.

## When to move up the stack

| Moving elements | Use |
|-----------------|-----|
| < ~1,000 | SVG (easy to debug/style) |
| ~1,000–10,000 | Canvas 2D |
| 3D or tens of thousands | WebGL / WebGPU (React Three Fiber, PixiJS, Phaser, raw WebGL) |

For most 2D browser games, **Canvas 2D is the sweet spot** — that's why PixiJS and Phaser are built on it.

## In React

Don't put the loop in React state. Mount the canvas once, run the rAF loop in a `useEffect`, store mutable game state in a `ref`:

```tsx
function Game() {
  const canvasRef = useRef(null)
  const stateRef = useRef({ x: 0, y: 0, sprite: null })
  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d')
    let raf, last = performance.now()
    const loop = (now) => {
      const dt = Math.min((now - last) / 1000, 0.1); last = now
      const s = stateRef.current
      s.x += 30 * dt            // move right at 30px/s, frame-rate-independent
      s.sprite?.update(dt)
      ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height)
      s.sprite?.draw(ctx, s.x, s.y)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)   // cleanup on unmount
  }, [])
  return <canvas ref={canvasRef} />
}
```

- `stateRef` holds per-frame mutable state (no re-renders).
- `cancelAnimationFrame` in the effect cleanup so unmounting stops the loop.

## Anti-patterns

- ❌ `setInterval(loop, 16)` — doesn't sync to refresh, doesn't pause when hidden.
- ❌ `x += 2` per frame — runs 2.4× faster on a 144Hz monitor.
- ❌ Sizing canvas with CSS only — blurry bitmap.
- ❌ `imageSmoothingEnabled = true` for pixel art — smeared pixels.
- ❌ Starting the rAF loop before images load — silent blank screen.
- ❌ `if (elapsed >= frameDuration)` instead of `while` — animation slows when frames drop.
- ❌ Storing entity positions in React state — 60 re-renders/s.
