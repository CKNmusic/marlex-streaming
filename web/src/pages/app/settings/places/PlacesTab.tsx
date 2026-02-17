import { useCallback, type FormEvent } from 'react';
import { Cloud, CloudOff, Eye, PlayCircle, Plus, StopCircle } from 'lucide-react';
import { Button } from '../../../../components/ui/Button';
import { AutocompleteInput } from '../../../../components/ui/AutocompleteInput';
import { IconActionButton } from '../../../../components/ui/IconActionButton';
import { SelectField } from '../../../../components/ui/SelectField';
import type { CityApi } from '../../../../lib/api/client';
import { SortableHeader } from '../../components/SortableHeader';
import { useSortableTable } from '../../hooks/useSortableTable';
import type { PlaceItem } from '../../types';

type PlaceSortKey = 'name' | 'city' | 'status';

type PlacesTabProps = {
    placeTabSearch: string;
    onPlaceTabSearchChange: (value: string) => void;
    showInactivePlaces: boolean;
    onShowInactivePlacesChange: (value: boolean) => void;
    placeForm: { name: string; description: string; city_id: string };
    onPlaceFormChange: (next: { name: string; description: string; city_id: string }) => void;
    placeCitySearch: string;
    onPlaceCitySearchChange: (value: string) => void;
    editingPlaceCityLabel: string;
    placeCityNotFound: boolean;
    cities: CityApi[];
    cptecApiOnline: boolean | null;
    onOpenCityRegistration: () => void;
    editingPlaceId: number | null;
    showPlaceForm: boolean;
    filteredPlaces: PlaceItem[];
    totalPlaces: number;
    onOpenCreatePlace: () => void;
    onCreatePlace: (event: FormEvent) => Promise<void> | void;
    onCancelPlaceEdit: () => void;
    onViewPlace: (place: PlaceItem) => void;
    onTogglePlaceActive: (placeId: number, nextActive: boolean, label: string) => void;
};

export const PlacesTab = ({
    placeTabSearch,
    onPlaceTabSearchChange,
    showInactivePlaces,
    onShowInactivePlacesChange,
    placeForm,
    onPlaceFormChange,
    placeCitySearch,
    onPlaceCitySearchChange,
    editingPlaceCityLabel,
    placeCityNotFound,
    cities,
    cptecApiOnline,
    onOpenCityRegistration,
    editingPlaceId,
    showPlaceForm,
    filteredPlaces,
    totalPlaces,
    onOpenCreatePlace,
    onCreatePlace,
    onCancelPlaceEdit,
    onViewPlace,
    onTogglePlaceActive,
}: PlacesTabProps) => {
    const placeVisibilityOptions = [
        { value: 'all', label: 'Todos (ativos)' },
        { value: 'inactive', label: 'Somente desativados' },
    ];
    const cityOptions = cities.map((city) => ({
        value: `${city.name}/${city.uf}`,
        label: `${city.name}/${city.uf}`,
    }));

    const getPlaceSortValue = useCallback((place: PlaceItem, key: PlaceSortKey): string => {
        if (key === 'name') return place.name || '';
        if (key === 'city') return place.city !== '-' ? `${place.city}/${place.state}` : '';
        if (key === 'status') return place.is_active ? 'Ativo' : 'Desativado';
        return '';
    }, []);
    const { sorted: placesSorted, sortKey, sortDir, onSort } = useSortableTable<PlaceItem, PlaceSortKey>(
        filteredPlaces, 'name', 'asc', getPlaceSortValue,
    );

    return (
        <div className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <input
                    value={placeTabSearch}
                    onChange={(event) => onPlaceTabSearchChange(event.target.value)}
                    placeholder="Buscar local"
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none sm:flex-1"
                />
                <Button onClick={onOpenCreatePlace} className="w-full sm:ml-2 sm:w-auto">
                    <Plus className="mr-1 h-4 w-4" />
                    Adicionar
                </Button>
            </div>
            <div className="flex flex-wrap items-center gap-3">
                <SelectField
                    value={showInactivePlaces ? 'inactive' : 'all'}
                    options={placeVisibilityOptions}
                    onValueChange={(value) => onShowInactivePlacesChange(value === 'inactive')}
                    className="w-full sm:w-[220px]"
                    triggerClassName="text-xs text-zinc-700"
                />
                <span className="text-xs text-zinc-500">{totalPlaces} local(is) cadastrado(s)</span>
            </div>

            {showPlaceForm ? (
                <form onSubmit={onCreatePlace} className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
                    <div className="grid gap-2 md:grid-cols-2">
                        <input
                            value={placeForm.name}
                            onChange={(event) => onPlaceFormChange({ ...placeForm, name: event.target.value })}
                            placeholder="Nome"
                            className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                        />
                        <input
                            value={placeForm.description}
                            onChange={(event) => onPlaceFormChange({ ...placeForm, description: event.target.value })}
                            placeholder="Descrição"
                            className="rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none"
                        />
                        {editingPlaceId ? (
                            <div>
                                <label className="mb-1 block text-xs text-zinc-500">Cidade (fixa)</label>
                                <input
                                    value={editingPlaceCityLabel}
                                    readOnly
                                    className="w-full rounded-md border border-zinc-200 bg-zinc-100/60 px-3 py-2 text-sm outline-none"
                                />
                            </div>
                        ) : (
                            <>
                                <div className="flex items-center gap-2">
                                    <AutocompleteInput
                                        value={placeCitySearch}
                                        options={cityOptions}
                                        onValueChange={onPlaceCitySearchChange}
                                        placeholder="Cidade/UF"
                                        className="flex-1"
                                        emptyLabel="Cidade não encontrada na lista. Digite para validar na API; se indisponível, use Cidade/UF."
                                    />
                                    <button
                                        type="button"
                                        className="flex h-10 w-10 items-center justify-center rounded-md border border-zinc-200 bg-white transition hover:bg-zinc-50"
                                        title={cptecApiOnline === false ? 'Abrir cadastro de cidades (API indisponível)' : 'Abrir cadastro de cidades'}
                                        onClick={onOpenCityRegistration}
                                    >
                                        {cptecApiOnline === false ? (
                                            <CloudOff className="h-4 w-4 text-red-300" />
                                        ) : (
                                            <Cloud className="h-4 w-4 text-zinc-700" />
                                        )}
                                    </button>
                                </div>
                                {placeCityNotFound ? (
                                    <p className="text-xs text-zinc-500 md:col-span-2">Cidade não localizada.</p>
                                ) : null}
                            </>
                        )}
                        <div className="md:col-span-2 flex justify-end gap-2">
                            <Button type="submit" size="sm">
                                {editingPlaceId ? 'Salvar' : 'Adicionar'}
                            </Button>
                            <Button type="button" size="sm" variant="ghost" onClick={onCancelPlaceEdit}>
                                Cancelar
                            </Button>
                        </div>
                    </div>
                </form>
            ) : null}
            <div className="table-scroll">
                <table className="w-full table-fixed text-left text-sm">
                    <colgroup>
                        <col />
                        <col className="hidden sm:table-column" />
                        <col className="hidden md:table-column" />
                        <col className="hidden sm:table-column w-28" />
                        <col className="w-[170px] sm:w-[190px]" />
                    </colgroup>
                    <thead className="text-zinc-600">
                        <tr className="border-b border-zinc-200">
                            <SortableHeader<PlaceSortKey> label="Local" sortKey="name" currentKey={sortKey} currentDir={sortDir} onSort={onSort} />
                            <SortableHeader<PlaceSortKey> label="Cidade" sortKey="city" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden sm:table-cell" />
                            <th className="hidden py-2 md:table-cell">Descrição</th>
                            <SortableHeader<PlaceSortKey> label="Status" sortKey="status" currentKey={sortKey} currentDir={sortDir} onSort={onSort} className="hidden sm:table-cell" />
                            <th className="py-2 whitespace-nowrap">Ações</th>
                        </tr>
                    </thead>
                    <tbody>
                        {placesSorted.map((place) => {
                            const active = place.is_active !== false;
                            const placeLabel = place.city !== '-' ? `${place.name} - ${place.city}/${place.state}` : place.name;
                            return (
                                <tr key={place.id} className="border-b border-zinc-200/70">
                                    <td className="py-2 min-w-[210px] sm:min-w-0">
                                        <span className="block whitespace-normal break-words sm:truncate">{place.name}</span>
                                        <span className="block truncate text-[11px] text-zinc-500 sm:hidden">
                                            {place.city !== '-' ? `${place.city}/${place.state}` : '-'}
                                            {active ? '' : ' (Desativado)'}
                                        </span>
                                        <span className="block truncate text-[11px] text-zinc-500 md:hidden">
                                            {place.description || '-'}
                                        </span>
                                    </td>
                                    <td className="hidden py-2 sm:table-cell">{place.city !== '-' ? `${place.city}/${place.state}` : '-'}</td>
                                    <td className="hidden py-2 md:table-cell">{place.description || '-'}</td>
                                    <td className="hidden py-2 sm:table-cell">
                                        <span className={active ? 'text-emerald-600' : 'text-zinc-400'}>{active ? 'Ativo' : 'Desativado'}</span>
                                    </td>
                                    <td className="py-2">
                                        <div className="flex flex-nowrap gap-1 overflow-x-auto pb-1 sm:gap-2">
                                            <IconActionButton
                                                icon={active ? StopCircle : PlayCircle}
                                                title={active ? 'Desativar' : 'Ativar'}
                                                onClick={() => onTogglePlaceActive(place.id, !active, placeLabel)}
                                            />
                                            <IconActionButton
                                                icon={Eye}
                                                title="Visualizar"
                                                onClick={() => onViewPlace(place)}
                                            />
                                        </div>
                                    </td>
                                </tr>
                            );
                        })}
                        {placesSorted.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="py-6 text-center text-zinc-500">Sem locais.</td>
                            </tr>
                        ) : null}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
