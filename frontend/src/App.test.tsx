import { fireEvent, render, screen } from '@testing-library/react'
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

  it('explains missing input instead of submitting', async () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: /sign in|anmelden/i }))
    expect(await screen.findByText(/enter your email address|E-Mail-Adresse ein/i)).toBeInTheDocument()
    expect(screen.getByText(/enter your password|Passwort ein/i)).toBeInTheDocument()
  })
})
