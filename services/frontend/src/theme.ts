import { createTheme, type MantineColorsTuple } from '@mantine/core'

/** Soft iris — primary actions, active nav, focus. */
const iris: MantineColorsTuple = [
  '#EEF1FF',
  '#D9DFFF',
  '#B3BEFF',
  '#8A99FF',
  '#6B7CFF',
  '#5B6CFF',
  '#3D4CD6',
  '#2F3BA8',
  '#242C7A',
  '#181C4F',
]

export const theme = createTheme({
  primaryColor: 'iris',
  primaryShade: 5,
  defaultRadius: 'lg',
  fontFamily: 'Heebo, Rubik, "Segoe UI", "Arial Hebrew", sans-serif',
  fontFamilyMonospace: '"IBM Plex Mono", ui-monospace, Consolas, monospace',
  headings: {
    fontFamily: 'Rubik, Heebo, "Segoe UI", sans-serif',
    fontWeight: '600',
  },
  colors: {
    iris,
  },
  cursorType: 'pointer',
  focusRing: 'auto',
})
