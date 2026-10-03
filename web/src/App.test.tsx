import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import App from './App'

it('renders the development shell without requesting backend data', () => {
  const fetch = vi.fn(() => { throw new Error('Unexpected network request') })
  vi.stubGlobal('fetch', fetch)
  try {
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Event Radar' })).toBeInTheDocument()
    expect(screen.getByText(/product is under development/i)).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  } finally {
    vi.unstubAllGlobals()
  }
})
