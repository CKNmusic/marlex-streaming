import { useCallback } from 'react';
import { Eye, PlayCircle, Plus, StopCircle } from 'lucide-react';
import { Button } from '../../../../components/ui/Button';
import { IconActionButton } from '../../../../components/ui/IconActionButton';
import { SelectField } from '../../../../components/ui/SelectField';
import type { CityApi } from '../../../../lib/api/client';
import { SortableHeader } from '../../components/SortableHeader';
import { useSortableTable } from '../../hooks/useSortableTable';

type CitySortKey = 'name' | 'uf' | 'status';

type CityListPageProps = {
    citySearch: string;
    onCitySearchChange: (value: string) => void;
    showInactiveCities: boolean;
    onShowInactiveCitiesChange: (value: boolean) => void;
    filteredCities: CityApi[];
    totalCities: number;
    onOpenCreate: () => void;
    onViewCity: (city: CityApi) => void;
    onToggleCityActive: (cityId: number, nextActive: boolean, label: string) => void;
};

export const CityListPage = ({
    citySearch,
    onCitySearchChange,
    showInactiveCities,
    onShowInactiveCitiesChange,
    filteredCities,
    totalCities,
    onOpenCreate,
    onViewCity,
    onToggleCityActive,
}: CityListPageProps) => {
    const cityVisibilityOptions = [
        { value: 'all', label: 'Todos (ativos)' },
        { value: 'inactive', label: 'Somente desativados' },
    ];

    const getCitySortValue = useCallback((city: CityApi, key: CitySortKey): string => {
        if (key === 'name') return city.name || '';
        if (key === 'uf') return city.uf || '';
        if (key === 'status') return city.is_active !== false ? 'Ativa' : 'Desativada';
        return '';
    }, []);
    const { sorted: citiesSorted, sortKey, sortDir, onSort } = useSortableTable<CityApi, CitySortKey>(
        filteredCities, 'name', 'asc', getCitySortValue,
    );

    return (
        <div className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <input
                    value={citySearch}
                    onChange={(event) => onCitySearchChange(event.target.value)}
                    placeholder="Buscar cidade"
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none sm:flex-1"
                />
                <Button onClick={onOpenCreate} className="w-full sm:ml-2 sm:w-auto">
                    <Plus className="mr-1 h-4 w-4" />
                    Adicionar
                </Button>
            </div>

            <div className="flex flex-wrap items-center gap-3">
                <SelectField
                    value={showInactiveCities ? 'inactive' : 'all'}
                    options={cityVisibilityOptions}
                    onValueChange={(value) => onShowInactiveCitiesChange(value === 'inactive')}
                    className="w-full sm:w-[220px]"
                    triggerClassName="text-xs text-zinc-700"
                />
                <span className="text-xs text-zinc-500">{totalCities} cidade(s) cadastrada(s)</span>
            </div>

            <div className="table-scroll">
                <table className="w-full table-fixed text-left text-sm">
                    <colgroup>
                        <col />
                        <col className="hidden sm:table-column w-20" />
                        <col className="hidden sm:table-column w-28" />
                        <col className="w-[170px] sm:w-[190px]" />
                    </colgroup>
                    <thead className="text-zinc-600">
                        <tr className="border-b border-zinc-200">
                            <SortableHeader<CitySortKey> label="Cidade" sortKey="name" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                            <SortableHeader<CitySortKey> label="UF" sortKey="uf" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden sm:table-cell" />
                            <SortableHeader<CitySortKey> label="Status" sortKey="status" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden sm:table-cell" />
                            <th className="py-2 whitespace-nowrap">Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {citiesSorted.map((city) => {
                            const active = city.is_active !== false;
                            return (
                                <tr key={city.id} className="border-b border-zinc-200/70">
                                    <td className="py-2 min-w-[200px] sm:min-w-0">
                                        <span className="block whitespace-normal break-words sm:truncate">{city.name}</span>
                                        <span className="block truncate text-[11px] text-zinc-500 sm:hidden">
                                            {city.uf} {active ? '' : '(Desativada)'}
                                        </span>
                                    </td>
                                    <td className="hidden py-2 sm:table-cell">{city.uf}</td>
                                    <td className="hidden py-2 sm:table-cell">
                                        <span className={active ? 'text-emerald-600' : 'text-zinc-400'}>{active ? 'Ativa' : 'Desativada'}</span>
                                    </td>
                                    <td className="py-2">
                                        <div className="flex flex-nowrap gap-1 overflow-x-auto pb-1 sm:gap-2">
                                            <IconActionButton
                                                icon={active ? StopCircle : PlayCircle}
                                                title={active ? 'Desativar' : 'Ativar'}
                                                onClick={() => onToggleCityActive(city.id, !active, `${city.name}/${city.uf}`)}
                                            />
                                            <IconActionButton
                                                icon={Eye}
                                                title="Visualizar"
                                                onClick={() => onViewCity(city)}
                                            />
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                        {citiesSorted.length === 0 ? (
                            <tr>
                                <td colSpan={4} className="py-6 text-center text-zinc-500">Sem cidades.</td>
                            </tr>
                        ) : null}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
