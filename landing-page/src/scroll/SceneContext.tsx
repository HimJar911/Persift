import { createContext, useContext } from "react"
import { type MotionValue } from "framer-motion"

/**
 * sceneProgress is a MotionValue (0 -> 1) representing the scroll progress
 * *within* a single scene's band. Children read it to drive their own
 * scroll-scrubbed animations without any prop drilling.
 */
export const SceneProgressContext = createContext<MotionValue<number> | null>(null)

export function useSceneProgress(): MotionValue<number> {
  const ctx = useContext(SceneProgressContext)
  if (!ctx) {
    throw new Error("useSceneProgress must be used within a <Scene>")
  }
  return ctx
}
