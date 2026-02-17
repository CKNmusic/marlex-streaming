import { useEffect, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { cn } from '../../lib/utils';

export type AutocompleteOption = {
    value: string;
    label?: string;
};

type AutocompleteInputProps = {
    value: string;
    options: AutocompleteOption[];
    onValueChange: (nextValue: string) => void;
    onSelectOption?: (option: AutocompleteOption) => void;
    placeholder?: string;
    className?: string;
    inputClassName?: string;
    menuClassName?: string;
    emptyLabel?: string;
    disabled?: boolean;
    required?: boolean;
};

export const AutocompleteInput = ({
    value,
    options,
    onValueChange,
    onSelectOption,
    placeholder,
    className,
    inputClassName,
    menuClassName,
    emptyLabel = 'Nenhuma opção encontrada.',
    disabled = false,
    required = false,
}: AutocompleteInputProps) => {
    const normalizeSearchText = (value: string) => value
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();
    const [open, setOpen] = useState(false);
    const rootRef = useRef<HTMLDivElement | null>(null);
    const inputRef = useRef<HTMLInputElement | null>(null);

    const normalizedValue = normalizeSearchText(value.trim());
    const filteredOptions = useMemo(() => {
        if (!normalizedValue) return options;
        return options.filter((option) => {
            const label = normalizeSearchText(option.label || option.value);
            const rawValue = normalizeSearchText(option.value);
            return label.includes(normalizedValue) || rawValue.includes(normalizedValue);
        });
    }, [options, normalizedValue]);

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
                inputRef.current?.blur();
            }
        };
        document.addEventListener('mousedown', onDocumentMouseDown);
        document.addEventListener('keydown', onDocumentKeyDown);
        return () => {
            document.removeEventListener('mousedown', onDocumentMouseDown);
            document.removeEventListener('keydown', onDocumentKeyDown);
        };
    }, []);

    const handleSelect = (option: AutocompleteOption) => {
        onValueChange(option.value);
        onSelectOption?.(option);
        setOpen(false);
    };

    return (
        <div ref={rootRef} className={cn('relative', className)}>
            <div className="relative">
                <input
                    ref={inputRef}
                    value={value}
                    disabled={disabled}
                    required={required}
                    placeholder={placeholder}
                    onFocus={() => setOpen(true)}
                    onChange={(event) => {
                        onValueChange(event.target.value);
                        setOpen(true);
                    }}
                    className={cn(
                        'w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 pr-9 text-sm outline-none transition focus:ring-2 focus:ring-emerald-200 disabled:cursor-not-allowed disabled:opacity-60 min-h-[44px] sm:min-h-0',
                        inputClassName,
                    )}
                />
                <ChevronDown className={cn('pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-500 transition-transform', open && 'rotate-180')} />
            </div>

            {open ? (
                <div
                    role="listbox"
                    className={cn(
                        'absolute left-0 right-0 z-40 mt-1 max-h-48 sm:max-h-60 overflow-auto rounded-md border border-zinc-200 bg-white py-1 shadow-lg',
                        menuClassName,
                    )}
                >
                    {filteredOptions.length ? (
                        filteredOptions.map((option) => {
                            const label = option.label || option.value;
                            const active = option.value === value;
                            return (
                                <button
                                    key={`${option.value}-${label}`}
                                    type="button"
                                    role="option"
                                    aria-selected={active}
                                    className={cn(
                                        'flex w-full items-center justify-between gap-2 px-3 py-2.5 sm:py-2 text-left text-sm transition min-h-[40px] sm:min-h-0',
                                        active ? 'bg-emerald-50 text-emerald-700' : 'text-zinc-700 hover:bg-zinc-100',
                                    )}
                                    onClick={() => handleSelect(option)}
                                >
                                    <span className="truncate">{label}</span>
                                    {active ? <Check className="h-4 w-4 shrink-0" /> : null}
                                </button>
                            );
                        })
                    ) : (
                        <p className="px-3 py-2 text-xs text-zinc-500">{emptyLabel}</p>
                    )}
                </div>
            ) : null}
        </div>
    );
};
