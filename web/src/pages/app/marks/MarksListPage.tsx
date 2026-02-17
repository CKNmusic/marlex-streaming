import { useCallback } from 'react';
import { Eye, PlayCircle, Plus, StopCircle } from 'lucide-react';
import { Button } from '../../../components/ui/Button';
import { IconActionButton } from '../../../components/ui/IconActionButton';
import { SelectField } from '../../../components/ui/SelectField';
import type { MarkApi } from '../../../lib/api/client';
import { SortableHeader } from '../components/SortableHeader';
import { useSortableTable } from '../hooks/useSortableTable';

type MarkSortKey = 'name' | 'status';

type MarksListPageProps = {
    markSearch: string;
    onMarkSearchChange: (value: string) => void;
    showInactiveMarks: boolean;
    onShowInactiveMarksChange: (value: boolean) => void;
    marks: MarkApi[];
    totalMarks: number;
    onOpenCreate: () => void;
    onOpenView: (mark: MarkApi) => void;
    onToggleMarkActive: (mark: MarkApi) => void;
};

export const MarksListPage = ({
    markSearch,
    onMarkSearchChange,
    showInactiveMarks,
    onShowInactiveMarksChange,
    marks,
    totalMarks,
    onOpenCreate,
    onOpenView,
    onToggleMarkActive,
}: MarksListPageProps) => {
    const visibilityOptions = [
        { value: 'all', label: 'Todos (ativos)' },
        { value: 'inactive', label: 'Somente desativados' },
    ];

    const getMarkSortValue = useCallback((mark: MarkApi, key: MarkSortKey): string => {
        if (key === 'name') return mark.name || '';
        if (key === 'status') return mark.is_active !== false ? 'Ativa' : 'Desativada';
        return '';
    }, []);
    const { sorted: marksSorted, sortKey, sortDir, onSort } = useSortableTable<MarkApi, MarkSortKey>(
        marks, 'name', 'asc', getMarkSortValue,
    );

    return (
        <div className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <input
                    value={markSearch}
                    onChange={(event) => onMarkSearchChange(event.target.value)}
                    placeholder="Buscar marca"
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none sm:flex-1"
                />
                <Button onClick={onOpenCreate} className="w-full sm:ml-2 sm:w-auto">
                    <Plus className="mr-1 h-4 w-4" />
                    Adicionar
                </Button>
            </div>

            <div className="flex flex-wrap items-center gap-3">
                <SelectField
                    value={showInactiveMarks ? 'inactive' : 'all'}
                    options={visibilityOptions}
                    onValueChange={(value) => onShowInactiveMarksChange(value === 'inactive')}
                    className="w-full sm:w-[220px]"
                    triggerClassName="text-xs text-zinc-700"
                />
                <span className="text-xs text-zinc-500">{totalMarks} marca(s) cadastrada(s)</span>
            </div>

            <div className="table-scroll">
                <table className="w-full table-fixed text-left text-sm">
                    <colgroup>
                        <col />
                        <col className="hidden sm:table-column" />
                        <col className="w-[190px] sm:w-[220px]" />
                    </colgroup>
                    <thead className="text-zinc-600">
                        <tr className="border-b border-zinc-200">
                            <SortableHeader<MarkSortKey> label="Marca" sortKey="name" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                            <SortableHeader<MarkSortKey> label="Status" sortKey="status" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden sm:table-cell" />
                            <th className="py-2 whitespace-nowrap">Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {marksSorted.map((mark) => {
                            const active = mark.is_active !== false;
                            return (
                                <tr key={mark.id} className="border-b border-zinc-200/70">
                                    <td className="py-2 min-w-[200px] sm:min-w-0">
                                        <span className="block whitespace-normal break-words sm:truncate">{mark.name}</span>
                                        <span className="block truncate text-[11px] text-zinc-500 sm:hidden">
                                            {active ? 'Ativa' : 'Desativada'}
                                        </span>
                                    </td>
                                    <td className="hidden py-2 sm:table-cell">{active ? 'Ativa' : 'Desativada'}</td>
                                    <td className="py-2">
                                        <div className="flex flex-nowrap gap-1 overflow-x-auto pb-1 sm:gap-2">
                                            <IconActionButton
                                                icon={active ? StopCircle : PlayCircle}
                                                title={active ? 'Desativar' : 'Ativar'}
                                                onClick={() => onToggleMarkActive(mark)}
                                            />
                                            <IconActionButton
                                                icon={Eye}
                                                title="Visualizar"
                                                onClick={() => onOpenView(mark)}
                                            />
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                        {marksSorted.length === 0 ? (
                            <tr>
                                <td colSpan={3} className="py-6 text-center text-zinc-500">Sem marcas.</td>
                            </tr>
                        ) : null}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

