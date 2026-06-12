import { type ReactNode } from "react"
import { motion, useTransform, type MotionValue } from "framer-motion"
import { SceneProgressContext } from "./SceneContext"

type SceneProps = {
  index: number
  total: number
  progress: MotionValue<number>
  children: ReactNode
  zIndex?: number
}

/**
 * A single scene on the sticky stage. Everything it renders is absolutely
 * positioned full-viewport. Its opacity / scale are derived directly from the
 * master scroll progress — no state, no timers, fully scrubbable both ways.
 *
 * Transition style B: incoming scales 0.95→1 while fading in,
 * outgoing scales 1→0.95 while fading out. No vertical slide.
 */
export function Scene({ index, total, progress, children, zIndex }: SceneProps) {
  const band = 1 / total
  const start = index * band
  const end = start + band

  const overlap = band * 0.5

  const isFirst = index === 0
  const isLast = index === total - 1

  const inStart = start - overlap * 0.5
  const inEnd = start + overlap * 0.5
  const outStart = end - overlap * 0.5
  const outEnd = end + overlap * 0.5

  // Fade: incoming 0→1, outgoing fades out gently
  const opacity = useTransform(
    progress,
    [inStart, inEnd, outStart, outEnd],
    [isFirst ? 1 : 0, 1, 1, isLast ? 1 : 0],
  )

  // Scale: incoming grows 0.95→1, outgoing stays at 1 (slide does the exit work)
  const scale = useTransform(
    progress,
    [inStart, inEnd, outStart, outEnd],
    [isFirst ? 1 : 0.95, 1, 1, 1],
  )

  // Slide: incoming rises from below, outgoing continues upward
  const y = useTransform(
    progress,
    [inStart, inEnd, outStart, outEnd],
    [isFirst ? 0 : 50, 0, 0, isLast ? 0 : -50],
  )

  // sceneProgress: 0 -> 1 within this scene's band, clamped
  const sceneProgress = useTransform(progress, [start, end], [0, 1], { clamp: true })

  return (
    <SceneProgressContext.Provider value={sceneProgress}>
      <motion.div
        aria-hidden={false}
        style={{
          position: "absolute",
          inset: 0,
          opacity,
          scale,
          y,
          zIndex: zIndex ?? index,
          pointerEvents: "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {children}
      </motion.div>
    </SceneProgressContext.Provider>
  )
}
