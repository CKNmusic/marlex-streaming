import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '../../lib/utils';

export type SelectFieldOption = {
    value: string;
    label: string;
    disabled?: boolean;
};

type SelectFieldProps = {
    value: string;
    options: SelectFieldOption[];
    onValueChange: (value: string) => void;
    placeholder?: string;
    className?: string;
    triggerClassName?: string;
    menuClassName?: string;
    disabled?: boolean;
};

export const SelectField = ({
    value,
    options,
    onValueChange,
    placeholder = 'Selecione',
    className,
    triggerClassName,
    menuClassName,
    disabled = false,
}: SelectFieldProps) => {
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement | null>(null);
    const triggerRef = useRef<HTMLButtonElement | null>(null);

    const selectedOption = useMemo(
        () => options.find((option) => option.value === value) || null,
        [options, value],
    );

    useEffect(() => {
        const onDocumentMouseDown = (event: MouseEvent) => {
            if (!rootRef.current) return;
            if (!rootRef.current.contains(event.target as Node)) {
                setOpen(false);
            }
        };
        const onDocumentKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') {
                setOpen(false);
                triggerRef.current?.focus();
            }
        };
        document.addEventListener('mousedown', onDocumentMouseDown);
        document.addEventListener('keydown', onDocumentKeyDown);
        return () => {
            document.removeEventListener('mousedown', onDocumentMouseDown);
            document.removeEventListener('keydown', onDocumentKeyDown);
        };
    }, []);

    const handleChoose = (nextValue: string) => {
        onValueChange(nextValue);
        setOpen(false);
        triggerRef.current?.focus();
    };

    return (
        <div ref={rootRef} className={cn('relative', className)}>
            <button
                ref={triggerRef}
                type="button"
                disabled={disabled}
                aria-haspopup="listbox"
                aria-expanded={open}
                className={cn(
                    'inline-flex w-full items-center justify-between gap-2 rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-left text-sm text-zinc-900 outline-none transition focus:ring-2 focus:ring-emerald-200 disabled:cursor-not-allowed disabled:opacity-60 min-h-[44px] sm:min-h-0',
                    triggerClassName,
                )}
                onClick={() => {
                    if (disabled) return;
                    setOpen((state) => !state);
                }}
            >
                <span className={cn('truncate', selectedOption ? 'text-zinc-900' : 'text-zinc-500')}>
                    {selectedOption?.label || placeholder}
                </span>
                <ChevronDown className={cn('h-4 w-4 shrink-0 text-zinc-500 transition-transform', open && 'rotate-180')} />
            </button>

            {open ? (
                <div
                    role="listbox"
                    className={cn(
                        'absolute left-0 right-0 z-40 mt-1 max-h-48 sm:max-h-60 overflow-auto rounded-md border border-zinc-200 bg-white py-1 shadow-lg',
                        menuClassName,
                    )}
                >
                    {options.map((option) => {
                        const active = option.value === value;
                        return (
                            <button
                                key={option.value}
                                type="button"
                                role="option"
                                aria-selected={active}
                                disabled={option.disabled}
                                className={cn(
                                    'flex w-full items-center justify-between gap-2 px-3 py-2.5 sm:py-2 text-left text-sm transition min-h-[40px] sm:min-h-0',
                                    option.disabled
                                        ? 'cursor-not-allowed text-zinc-300'
                                        : active
                                            ? 'bg-emerald-50 text-emerald-700'
                                            : 'text-zinc-700 hover:bg-zinc-100',
                                )}
                                onClick={() => {
                                    if (option.disabled) return;
                                    handleChoose(option.value);
                                }}
                            >
                                <span className="truncate">{option.label}</span>
                                {active ? <Check className="h-4 w-4 shrink-0" /> : null}
                            </button>
                        );
                    })}
                </div>
            ) : null}
        </div>
    );
};

