export const uiTheme = {
    surface: {
        panel: 'bg-white border-zinc-200',
        muted: 'bg-zinc-100',
    },
    text: {
        primary: 'text-zinc-900',
        secondary: 'text-zinc-700',
        muted: 'text-zinc-500',
    },
    focus: {
        ring: 'focus:ring-2 focus:ring-offset-2 focus:ring-offset-white',
    },
    button: {
        base: 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none disabled:opacity-50 disabled:pointer-events-none active:scale-[0.97]',
        variants: {
            primary: 'bg-blue-600 text-white hover:bg-blue-500 active:bg-blue-700 focus:ring-blue-500',
            secondary: 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 active:bg-zinc-300 focus:ring-zinc-300',
            danger: 'bg-red-600 text-white hover:bg-red-500 active:bg-red-700 focus:ring-red-500',
            ghost: 'bg-transparent text-zinc-700 hover:bg-zinc-100 active:bg-zinc-200 focus:ring-zinc-300',
        },
    },
    status: {
        error: 'border-red-500/30 bg-red-500/10 text-red-400',
        warn: 'border-amber-500/30 bg-amber-500/10 text-amber-600',
        info: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
    },
} as const;

