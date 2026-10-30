import { cn } from '@/lib/utils'

export function KernelMark({ className }: Readonly<{ className?: string }>) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden focusable="false">
      <g stroke="#ffffff" strokeWidth="1.1" strokeLinecap="round" fill="none" opacity="0.85">
        <path d="M6 22 L16 8 L26 19" />
        <path d="M16 8 L16 17" />
        <path d="M6 22 L16 17 L26 19" />
      </g>
      <circle cx="6" cy="22" r="2" fill="#ffffff" />
      <circle cx="26" cy="19" r="2" fill="#ffffff" />
      <circle cx="16" cy="17" r="1.8" fill="#ffffff" />
      <circle cx="16" cy="8" r="2.8" fill="#01F000" />
    </svg>
  )
}

export function KernelWordmark({ className, markClassName }: Readonly<{ className?: string; markClassName?: string }>) {
  return (
    <span className="inline-flex items-center gap-2.5 text-white">
      <KernelMark className={cn('h-8 w-8', markClassName)} />
      <span className={cn('text-2xl font-semibold tracking-tight', className)}>
        scch/kernel
      </span>
    </span>
  )
}
