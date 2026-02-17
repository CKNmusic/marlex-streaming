import { useMemo, useState } from 'react';
import { Pencil, PlayCircle, StopCircle, Trash2 } from 'lucide-react';
import type { Dispatch, FormEvent, SetStateAction } from 'react';
import type { CityApi } from '../../../../lib/api/client';
import { citiesAPI, placesAPI } from '../../../../lib/api/client';
import { Button } from '../../../../components/ui/Button';
import { Modal } from '../../../../components/ui/Modal';
import { resolveApiErrorMessage } from '../../errorMessage';
import { PlacesTab } from './PlacesTab';
import type { ConfirmState, PlaceItem, StatusLevel } from '../../types';

type PlaceFormState = {
    name: string;
    description: string;
    city_id: string;
};

type PlacesSettingsSectionProps = {
    places: PlaceItem[];
    placeTabSearch: string;
    setPlaceTabSearch: (value: string) => void;
    showInactivePlaces: boolean;
    setShowInactivePlaces: (value: boolean) => void;
    cities: CityApi[];
    cptecApiOnline: boolean | null;
    fetchCptecCity: (cityName: string, uf?: string) => Promise<{ name: string; uf: string } | null>;
    onOpenCityRegistration: () => void;
    loadPlaces: () => Promise<void>;
    loadCities: () => Promise<void>;
    showStatus: (level: StatusLevel, msg: string) => void;
    setConfirm: Dispatch<SetStateAction<ConfirmState>>;
};

export const PlacesSettingsSection = ({
    places,
    placeTabSearch,
    setPlaceTabSearch,
    showInactivePlaces,
    setShowInactivePlaces,
    cities,
    cptecApiOnline,
    fetchCptecCity,
    onOpenCityRegistration,
    loadPlaces,
    loadCities,
    showStatus,
    setConfirm,
}: PlacesSettingsSectionProps) => {
    const [viewingPlace, setViewingPlace] = useState<PlaceItem | null>(null);
    const [showPlaceForm, setShowPlaceForm] = useState(false);
    const [placeForm, setPlaceForm] = useState<PlaceFormState>({ name: '', description: '', city_id: '' });
    const [placeCitySearch, setPlaceCitySearch] = useState('');
    const [editingPlaceCityLabel, setEditingPlaceCityLabel] = useState('');
    const [placeCityNotFound, setPlaceCityNotFound] = useState(false);
    const [editingPlaceId, setEditingPlaceId] = useState<number | null>(null);
    const availableCities = useMemo(
        () => cities.filter((city) => city.is_active !== false),
        [cities],
    );

    const filteredPlaces = useMemo(
        () => places.filter((place) => {
            if (showInactivePlaces) return place.is_active === false;
            return place.is_active !== false;
        }).filter((place) => {
            const search = placeTabSearch.trim().toLowerCase();
            if (!search) return true;
            return (
                place.name.toLowerCase().includes(search)
                || place.city.toLowerCase().includes(search)
                || place.state.toLowerCase().includes(search)
                || place.description.toLowerCase().includes(search)
            );
        }),
        [places, showInactivePlaces, placeTabSearch],
    );

    const handleCreatePlace = async (event: FormEvent) => {
        event.preventDefault();
        setPlaceCityNotFound(false);
        if (!placeForm.name.trim()) {
            showStatus('error', 'Informe o nome do local.');
            return;
        }
        if (!editingPlaceId && !placeForm.city_id && !placeCitySearch.trim()) {
            showStatus('error', 'Informe a cidade.');
            return;
        }

        try {
            let resolvedCityId = placeForm.city_id ? Number(placeForm.city_id) : null;
            if (!editingPlaceId && !resolvedCityId && placeCitySearch.trim()) {
                const rawSearch = placeCitySearch.trim();
                const [namePartRaw, ufPartRaw] = rawSearch.split('/');
                const namePart = (namePartRaw || '').trim();
                const ufPart = (ufPartRaw || '').trim();
                const localMatch = availableCities.find((city) => {
                    const sameName = city.name.toLowerCase() === namePart.toLowerCase();
                    const sameUf = ufPart ? city.uf.toLowerCase() === ufPart.toLowerCase() : true;
                    return sameName && sameUf;
                });
                if (localMatch) {
                    resolvedCityId = localMatch.id;
                } else {
                    const apiCity = await fetchCptecCity(namePart || rawSearch, ufPart || undefined);
                    if (apiCity) {
                        const existingCity = availableCities.find((city) =>
                            city.name.toLowerCase() === apiCity.name.toLowerCase()
                            && city.uf.toLowerCase() === apiCity.uf.toLowerCase(),
                        );
                        if (existingCity) {
                            resolvedCityId = existingCity.id;
                        } else {
                            const createdCity = await citiesAPI.create({ name: apiCity.name, uf: apiCity.uf });
                            resolvedCityId = createdCity.data.id;
                            await loadCities();
                        }
                    } else if (cptecApiOnline === false && namePart && ufPart) {
                        const createdCity = await citiesAPI.create({
                            name: namePart,
                            uf: ufPart.toUpperCase(),
                        });
                        resolvedCityId = createdCity.data.id;
                        await loadCities();
                    }
                }
            }

            if (!editingPlaceId && !resolvedCityId) {
                if (cptecApiOnline === false) {
                    showStatus('warn', 'API de cidades indisponível. Informe cidade no formato Cidade/UF.');
                }
                setPlaceCityNotFound(true);
                return;
            }

            if (editingPlaceId) {
                await placesAPI.update(editingPlaceId, {
                    name: placeForm.name.trim(),
                    description: placeForm.description.trim() || undefined,
                });
            } else {
                const createCityId = Number(resolvedCityId);
                await placesAPI.create({
                    name: placeForm.name.trim(),
                    description: placeForm.description.trim() || undefined,
                    city_id: createCityId,
                });
            }
            await loadPlaces();
            setPlaceForm({ name: '', description: '', city_id: '' });
            setPlaceCitySearch('');
            setEditingPlaceCityLabel('');
            setEditingPlaceId(null);
            setShowPlaceForm(false);
            showStatus('info', editingPlaceId ? 'Local atualizado.' : 'Local criado.');
            setPlaceCityNotFound(false);
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, editingPlaceId ? 'Falha ao atualizar local.' : 'Falha ao criar local.'));
        }
    };

    const togglePlaceActive = async (placeId: number, nextActive: boolean) => {
        try {
            await placesAPI.update(placeId, { is_active: nextActive });
            await loadPlaces();
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao atualizar local.'));
        }
    };

    const confirmDeactivatePlace = (placeId: number, label: string) => {
        setConfirm({
            open: true,
            title: 'Desativar local',
            description: `Desativar ${label}?`,
            confirmLabel: 'Desativar',
            errorFallback: 'Falha ao desativar local.',
            onConfirm: async () => {
                await placesAPI.update(placeId, { is_active: false });
                await loadPlaces();
            },
        });
    };

    const confirmDeletePlace = (placeId: number, label: string) => {
        setConfirm({
            open: true,
            title: 'Excluir local',
            description: `Excluir ${label}?`,
            confirmLabel: 'Excluir',
            errorFallback: 'Falha ao excluir local.',
            onConfirm: async () => {
                await placesAPI.delete(placeId);
                await loadPlaces();
            },
        });
    };

    const handleTogglePlaceActive = (placeId: number, nextActive: boolean, label: string) => {
        if (nextActive) {
            void togglePlaceActive(placeId, true);
            return;
        }
        confirmDeactivatePlace(placeId, label);
    };

    const handlePlaceCitySearchChange = (value: string) => {
        setPlaceCitySearch(value);
        setPlaceCityNotFound(false);
        const match = availableCities.find((city) => `${city.name}/${city.uf}` === value);
        setPlaceForm({
            ...placeForm,
            city_id: match ? String(match.id) : '',
        });
    };

    const handleEditPlace = (place: PlaceItem) => {
        setEditingPlaceId(place.id);
        setPlaceForm({
            name: place.name,
            description: place.description,
            city_id: String(place.cityId),
        });
        setPlaceCitySearch(`${place.city}/${place.state}`);
        setEditingPlaceCityLabel(`${place.city}/${place.state}`);
        setPlaceCityNotFound(false);
        setShowPlaceForm(true);
    };

    const handleCancelPlaceEdit = () => {
        setEditingPlaceId(null);
        setPlaceForm({ name: '', description: '', city_id: '' });
        setPlaceCitySearch('');
        setEditingPlaceCityLabel('');
        setPlaceCityNotFound(false);
        setShowPlaceForm(false);
    };

    const handleOpenCreatePlace = () => {
        setEditingPlaceId(null);
        setPlaceForm({ name: '', description: '', city_id: '' });
        setPlaceCitySearch('');
        setEditingPlaceCityLabel('');
        setPlaceCityNotFound(false);
        setShowPlaceForm(true);
    };

    return (
        <>
            <PlacesTab
                placeTabSearch={placeTabSearch}
                onPlaceTabSearchChange={setPlaceTabSearch}
                showInactivePlaces={showInactivePlaces}
                onShowInactivePlacesChange={setShowInactivePlaces}
                placeForm={placeForm}
                onPlaceFormChange={setPlaceForm}
                placeCitySearch={placeCitySearch}
                onPlaceCitySearchChange={handlePlaceCitySearchChange}
                editingPlaceCityLabel={editingPlaceCityLabel}
                placeCityNotFound={placeCityNotFound}
                cities={availableCities}
                cptecApiOnline={cptecApiOnline}
                onOpenCityRegistration={onOpenCityRegistration}
                editingPlaceId={editingPlaceId}
                showPlaceForm={showPlaceForm}
                filteredPlaces={filteredPlaces}
                totalPlaces={places.length}
                onOpenCreatePlace={handleOpenCreatePlace}
                onCreatePlace={handleCreatePlace}
                onCancelPlaceEdit={handleCancelPlaceEdit}
                onViewPlace={setViewingPlace}
                onTogglePlaceActive={handleTogglePlaceActive}
            />
            <Modal
                isOpen={!!viewingPlace}
                onClose={() => setViewingPlace(null)}
                title="Detalhe do local"
            >
                {viewingPlace ? (
                    <div className="space-y-4 text-sm">
                        <div className="grid grid-cols-[120px,minmax(0,1fr)] gap-y-2">
                            <p className="text-zinc-600">ID</p>
                            <p>{viewingPlace.id}</p>
                            <p className="text-zinc-600">Nome</p>
                            <p>{viewingPlace.name}</p>
                            <p className="text-zinc-600">Cidade</p>
                            <p>{viewingPlace.city}/{viewingPlace.state}</p>
                            <p className="text-zinc-600">Descrição</p>
                            <p>{viewingPlace.description || '-'}</p>
                            <p className="text-zinc-600">Status</p>
                            <p>{viewingPlace.is_active ? 'Ativo' : 'Desativado'}</p>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                            <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                    handleEditPlace(viewingPlace);
                                    setViewingPlace(null);
                                }}
                            >
                                <Pencil className="mr-2 h-4 w-4" />
                                Editar
                            </Button>
                            <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => {
                                    const label = `${viewingPlace.name} - ${viewingPlace.city}/${viewingPlace.state}`;
                                    handleTogglePlaceActive(viewingPlace.id, !viewingPlace.is_active, label);
                                    setViewingPlace(null);
                                }}
                            >
                                {viewingPlace.is_active ? (
                                    <StopCircle className="mr-2 h-4 w-4" />
                                ) : (
                                    <PlayCircle className="mr-2 h-4 w-4" />
                                )}
                                {viewingPlace.is_active ? 'Desativar' : 'Ativar'}
                            </Button>
                            <Button
                                size="sm"
                                variant="danger"
                                onClick={() => {
                                    const label = `${viewingPlace.name} - ${viewingPlace.city}/${viewingPlace.state}`;
                                    confirmDeletePlace(viewingPlace.id, label);
                                    setViewingPlace(null);
                                }}
                            >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Excluir
                            </Button>
                        </div>
                    </div>
                ) : null}
            </Modal>
        </>
    );
};
