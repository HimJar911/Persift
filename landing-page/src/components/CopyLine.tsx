import { motion, useTransform } from "framer-motion"
import { useSceneProgress } from "../scroll/SceneContext"

/**
 * A line of copy that fades/rises in based on the current scene's progress.
 * Reads sceneProgress from context — driven purely by scroll, no state.
 */
export function CopyLine({
  children,
  from = 0.55,
  to = 0.8,
  italic = false,
  color = "var(--ink-soft)",
  size = 16,
}: {
  children: React.ReactNode
  from?: number
  to?: number
  italic?: boolean
  color?: string
  size?: number
}) {
  const p = useSceneProgress()
  const opacity = useTransform(p, [from, to], [0, 1])
  const y = useTransform(p, [from, to], [14, 0])

  return (
    <motion.p
      style={{
        opacity,
        y,
        margin: 0,
        textAlign: "center",
        fontFamily: "var(--font-sans)",
        fontStyle: italic ? "italic" : "normal",
        fontWeight: 400,
        fontSize: size,
        lineHeight: 1.5,
        letterSpacing: "0.01em",
        color,
      }}
    >
      {children}
    </motion.p>
  )
}
