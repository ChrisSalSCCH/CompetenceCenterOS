import { render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it } from 'vitest'
import App from '@/App'

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false, media: query, onchange: null, addEventListener: () => undefined, removeEventListener: () => undefined,
      addListener: () => undefined, removeListener: () => undefined, dispatchEvent: () => false,
    }),
  })
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as unknown as typeof ResizeObserver
})

describe('App', () => {
  it('shows the sign-in screen for anonymous visitors', async () => {
    localStorage.clear()
    render(<App />)
    expect(await screen.findByRole('button', { name: /sign in|anmelden/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/email|e-mail/i)).toBeInTheDocument()
  })
})
