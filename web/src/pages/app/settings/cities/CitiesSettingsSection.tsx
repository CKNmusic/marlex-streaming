import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { PlayCircle, StopCircle, Trash2 } from 'lucide-react';
import type { Dispatch, FormEvent, SetStateAction } from 'react';
import type { CityApi } from '../../../../lib/api/client';
import { citiesAPI } from '../../../../lib/api/client';
import { Button } from '../../../../components/ui/Button';
import { Modal } from '../../../../components/ui/Modal';
import { resolveApiErrorMessage } from '../../errorMessage';
import { CityCreatePage } from './CityCreatePage';
import { CityListPage } from './CityListPage';
import type { ConfirmState, StatusLevel } from '../../types';

type CityFormState = {
    name: string;
    uf: string;
};
const normalizeSearchText = (value: string) => value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();

type CitiesSettingsSectionProps = {
    cities: CityApi[];
    citySearch: string;
    setCitySearch: (value: string) => void;
    showInactiveCities: boolean;
    setShowInactiveCities: (value: boolean) => void;
    cptecApiOnline: boolean | null;
    searchCptecCities: (cityName: string) => Promise<Array<{ name: string; uf: string }>>;
    loadCities: () => Promise<void>;
    showStatus: (level: StatusLevel, msg: string) => void;
    setConfirm: Dispatch<SetStateAction<ConfirmState>>;
};

export const CitiesSettingsSection = ({
    cities,
    citySearch,
    setCitySearch,
    showInactiveCities,
    setShowInactiveCities,
    cptecApiOnline,
    searchCptecCities,
    loadCities,
    showStatus,
    setConfirm,
}: CitiesSettingsSectionProps) => {
    const [cityView, setCityView] = useState<'list' | 'create'>('list');
    const [viewingCity, setViewingCity] = useState<CityApi | null>(null);
    const [cityForm, setCityForm] = useState<CityFormState>({ name: '', uf: '' });
    const [cityApiSearch, setCityApiSearch] = useState('');
    const [cityApiOptions, setCityApiOptions] = useState<Array<{ value: string; label: string }>>([]);
    const [searchingCityApi, setSearchingCityApi] = useState(false);
    const cityApiSearchRequestId = useRef(0);

    const filteredCities = useMemo(
        () => cities.filter((city) => {
            if (showInactiveCities) return city.is_active === false;
            return city.is_active !== false;
        }).filter((city) => {
            const search = normalizeSearchText(citySearch.trim());
            if (!search) return true;
            return normalizeSearchText(city.name).includes(search) || normalizeSearchText(city.uf).includes(search);
        }),
        [cities, showInactiveCities, citySearch],
    );

    const createCity = async (name: string, uf: string) => {
        await citiesAPI.create({ name: name.trim(), uf: uf.trim().toUpperCase() });
        await loadCities();
        setCityForm({ name: '', uf: '' });
        setCityApiSearch('');
        setCityApiOptions([]);
        setCityView('list');
        showStatus('info', 'Cidade criada.');
    };

    const handleCreateCity = async (event: FormEvent) => {
        event.preventDefault();
        if (cptecApiOnline !== false) {
            return;
        }
        if (!cityForm.name.trim() || !cityForm.uf.trim()) {
            showStatus('error', 'Informe cidade e UF.');
            return;
        }
        try {
            await createCity(cityForm.name, cityForm.uf);
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao criar cidade.'));
        }
    };

    const runCityApiSearch = useCallback(async (
        rawQuery: string,
        options?: { notifyIfEmpty?: boolean },
    ) => {
        const query = rawQuery.trim();
        if (query.length < 3) {
            setCityApiOptions([]);
            return;
        }
        const currentRequestId = cityApiSearchRequestId.current + 1;
        cityApiSearchRequestId.current = currentRequestId;
        setSearchingCityApi(true);
        try {
            const found = await searchCptecCities(query);
            if (currentRequestId !== cityApiSearchRequestId.current) return;
            const normalizedQuery = normalizeSearchText(query);
            const filteredFound = found.filter((item) => normalizeSearchText(item.name).includes(normalizedQuery));
            const optionsFound = filteredFound.map((item) => ({
                value: `${item.name}/${item.uf.toUpperCase()}`,
                label: `${item.name}/${item.uf.toUpperCase()}`,
            }));
            setCityApiOptions(optionsFound);
            if (!optionsFound.length) {
                if (options?.notifyIfEmpty !== false) {
                    showStatus('warn', 'Nenhuma cidade encontrada na API.');
                }
                return;
            }
            if (options?.notifyIfEmpty !== false) {
                showStatus('info', `${optionsFound.length} cidade(s) encontrada(s) na API.`);
            }
        } catch {
            if (currentRequestId !== cityApiSearchRequestId.current) return;
            showStatus('error', 'Falha ao consultar API de cidades.');
        } finally {
            if (currentRequestId === cityApiSearchRequestId.current) {
                setSearchingCityApi(false);
            }
        }
    }, [searchCptecCities, showStatus]);

    useEffect(() => {
        if (cptecApiOnline === false) return;
        const query = cityApiSearch.trim();
        if (query.length < 3 || query.includes('/')) {
            return;
        }
        const timer = window.setTimeout(() => {
            void runCityApiSearch(query, { notifyIfEmpty: false });
        }, 350);
        return () => {
            window.clearTimeout(timer);
        };
    }, [cityApiSearch, cptecApiOnline, runCityApiSearch]);

    const handleSearchCityApi = async () => {
        const query = cityApiSearch.trim();
        if (query.length < 3) {
            showStatus('warn', 'Digite ao menos 3 caracteres para buscar cidade.');
            return;
        }
        await runCityApiSearch(query, { notifyIfEmpty: true });
    };

    const handleCityApiSearchChange = (value: string) => {
        setCityApiSearch(value.toLowerCase());
        if (value.trim().length < 3) {
            setCityApiOptions([]);
        }
    };

    const handleSelectCityApiOption = (value: string) => {
        setCityApiSearch(value);
        const [nameRaw, ufRaw] = value.split('/');
        const name = (nameRaw || '').trim();
        const uf = (ufRaw || '').trim().toUpperCase();
        if (!name || !uf) {
            showStatus('warn', 'Seleção inválida de cidade na API.');
            return;
        }
        setCityForm({ name, uf });
        setConfirm({
            open: true,
            title: 'Cadastrar cidade',
            description: `Inserir ${name}/${uf} na base de dados?`,
            confirmLabel: 'Inserir',
            errorFallback: 'Falha ao cadastrar cidade.',
            onConfirm: async () => {
                await createCity(name, uf);
            },
        });
    };

    const toggleCityActive = async (cityId: number, nextActive: boolean) => {
        try {
            await citiesAPI.update(cityId, { is_active: nextActive });
            await loadCities();
        } catch (error) {
            showStatus('error', resolveApiErrorMessage(error, 'Falha ao atualizar cidade.'));
        }
    };

    const confirmDeactivateCity = (cityId: number, label: string) => {
        setConfirm({
            open: true,
            title: 'Desativar cidade',
            description: `Desativar ${label}?`,
            confirmLabel: 'Desativar',
            errorFallback: 'Falha ao desativar cidade.',
            onConfirm: async () => {
                await citiesAPI.update(cityId, { is_active: false });
                await loadCities();
            },
        });
    };

    const confirmDeleteCity = (cityId: number, label: string) => {
        setConfirm({
            open: true,
            title: 'Excluir cidade',
            description: `Excluir ${label}?`,
            confirmLabel: 'Excluir',
            errorFallback: 'Falha ao excluir cidade.',
            onConfirm: async () => {
                await citiesAPI.delete(cityId);
                await loadCities();
            },
        });
    };

    const handleToggleCityActive = (cityId: number, nextActive: boolean, label: string) => {
        if (nextActive) {
            void toggleCityActive(cityId, true);
            return;
        }
        confirmDeactivateCity(cityId, label);
    };

    const handleOpenCreateCity = () => {
        setCityForm({ name: '', uf: '' });
        setCityApiSearch('');
        setCityApiOptions([]);
        setCityView('create');
    };

    const handleBackToCitiesList = () => {
        setCityForm({ name: '', uf: '' });
        setCityApiSearch('');
        setCityApiOptions([]);
        setCityView('list');
    };

    if (cityView === 'create') {
        return (
            <CityCreatePage
                cityForm={cityForm}
                onCityFormChange={setCityForm}
                cityApiSearch={cityApiSearch}
                onCityApiSearchChange={handleCityApiSearchChange}
                cityApiOptions={cityApiOptions}
                onSearchCityApi={handleSearchCityApi}
                onSelectCityApiOption={handleSelectCityApiOption}
                searchingCityApi={searchingCityApi}
                cptecApiOnline={cptecApiOnline}
                onSubmit={handleCreateCity}
                onBack={handleBackToCitiesList}
            />
        );
    }

    return (
        <>
            <CityListPage
                citySearch={citySearch}
                onCitySearchChange={setCitySearch}
                showInactiveCities={showInactiveCities}
                onShowInactiveCitiesChange={setShowInactiveCities}
                filteredCities={filteredCities}
                totalCities={cities.length}
                onOpenCreate={handleOpenCreateCity}
                onViewCity={setViewingCity}
                onToggleCityActive={handleToggleCityActive}
            />
            <Modal
                isOpen={!!viewingCity}
                onClose={() => setViewingCity(null)}
                title="Detalhe da cidade"
            >
                {viewingCity ? (
                    <div className="space-y-4 text-sm">
                        <div className="grid grid-cols-[120px,minmax(0,1fr)] gap-y-2">
                            <p className="text-zinc-600">ID</p>
                            <p>{viewingCity.id}</p>
                            <p className="text-zinc-600">Cidade</p>
                            <p>{viewingCity.name}</p>
                            <p className="text-zinc-600">UF</p>
                            <p>{viewingCity.uf}</p>
                            <p className="text-zinc-600">Status</p>
                            <p>{viewingCity.is_active ? 'Ativa' : 'Desativada'}</p>
                        </div>
                        <div className="flex flex-wrap justify-end gap-2">
                            <Button
                                size="sm"
                                variant="secondary"
                                onClick={() => {
                                    const label = `${viewingCity.name}/${viewingCity.uf}`;
                                    handleToggleCityActive(viewingCity.id, !viewingCity.is_active, label);
                                    setViewingCity(null);
                                }}
                            >
                                {viewingCity.is_active ? (
                                    <StopCircle className="mr-2 h-4 w-4" />
                                ) : (
                                    <PlayCircle className="mr-2 h-4 w-4" />
                                )}
                                {viewingCity.is_active ? 'Desativar' : 'Ativar'}
                            </Button>
                            <Button
                                size="sm"
                                variant="danger"
                                onClick={() => {
                                    const label = `${viewingCity.name}/${viewingCity.uf}`;
                                    confirmDeleteCity(viewingCity.id, label);
                                    setViewingCity(null);
                                }}
                            >
                                <Trash2 className="mr-2 h-4 w-4" />
                                Excluir
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setViewingCity(null)}>
                                Fechar
                            </Button>
                        </div>
                    </div>
                ) : null}
            </Modal>
        </>
    );
};
