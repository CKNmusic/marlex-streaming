import { useCallback, useMemo, useState } from 'react';

type SortDirection = 'asc' | 'desc';

export const useSortableTable = <T, K extends string>(
    data: T[],
    defaultKey: K,
    defaultDirection: SortDirection,
    getValueFn: (item: T, key: K) => string | number,
) => {
    const [sortKey, setSortKey] = useState<K>(defaultKey);
    const [sortDir, setSortDir] = useState<SortDirection>(defaultDirection);

    const sorted = useMemo(() => {
        return [...data].sort((a, b) => {
            const aValue = getValueFn(a, sortKey);
            const bValue = getValueFn(b, sortKey);
            if (typeof aValue === 'number' && typeof bValue === 'number') {
                return sortDir === 'asc' ? aValue - bValue : bValue - aValue;
            }
            const aStr = String(aValue).toLowerCase();
            const bStr = String(bValue).toLowerCase();
            return sortDir === 'asc' ? aStr.localeCompare(bStr) : bStr.localeCompare(aStr);
        });
    }, [data, sortKey, sortDir, getValueFn]);

    const onSort = useCallback((key: K) => {
        setSortKey((prev) => {
            if (prev === key) {
                setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
            } else {
                setSortDir('asc');
            }
            return key;
        });
    }, []);

    return { sorted, sortKey, sortDir, onSort };
};
