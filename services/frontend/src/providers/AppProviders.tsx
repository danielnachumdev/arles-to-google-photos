import { DirectionProvider, MantineProvider, useDirection } from '@mantine/core'
import { useEffect, type ReactNode } from 'react'
import { useAppearance } from '../lib/appearance.ts'
import { APP_DIR, useLanguage } from '../lib/language.ts'
import { theme } from '../theme.ts'

function DirectionSync() {
  const { dir } = useLanguage()
  const { dir: mantineDir, setDirection } = useDirection()

  useEffect(() => {
    if (dir !== mantineDir) {
      setDirection(dir)
    }
  }, [dir, mantineDir, setDirection])

  return null
}

export function AppProviders({ children }: { children: ReactNode }) {
  const { colorScheme } = useAppearance()
  return (
    <DirectionProvider initialDirection={APP_DIR} detectDirection>
      <MantineProvider theme={theme} defaultColorScheme={colorScheme} forceColorScheme={colorScheme}>
        <DirectionSync />
        {children}
      </MantineProvider>
    </DirectionProvider>
  )
}
