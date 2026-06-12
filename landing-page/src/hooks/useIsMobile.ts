import { useEffect, useState } from "react"

/**
 * Returns true when the viewport is at or below the given breakpoint (px).
 * Defaults to 640px — the line below which the cinematic scenes switch to
 * their stacked, single-column mobile layouts.
 */
export function useIsMobile(breakpoint = 640): boolean {
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${breakpoint}px)`)
    const update = () => setIsMobile(mql.matches)
    update()
    mql.addEventListener("change", update)
    return () => mql.removeEventListener("change", update)
  }, [breakpoint])

  return isMobile
}
