import { ChevronDown, ChevronUp } from 'lucide-react';

type SortableHeaderProps<K extends string> = {
    label: string;
    sortKey: K;
    currentKey: K;
    currentDir: 'asc' | 'desc';
    onSort: (key: K) => void;
    className?: string;
};

export const SortableHeader = <K extends string>({
    label,
    sortKey,
    currentKey,
    currentDir,
    onSort,
    className = '',
}: SortableHeaderProps<K>) => (
    <th
        className={`py-2 cursor-pointer select-none hover:text-zinc-900 ${className}`}
        onClick={() => onSort(sortKey)}
    >
        <span className="inline-flex items-center gap-0.5">
            {label}
            {currentKey === sortKey ? (
                currentDir === 'asc' ? (
                    <ChevronUp className="h-3 w-3" />
                ) : (
                    <ChevronDown className="h-3 w-3" />
                )
            ) : (
                <ChevronDown className="h-3 w-3 opacity-0" />
            )}
        </span>
    </th>
);
