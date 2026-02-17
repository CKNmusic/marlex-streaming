import type { Dispatch, FormEvent, SetStateAction } from 'react';
import type { AppSettings, CityApi } from '../../lib/api/client';
import { appSettingsAPI } from '../../lib/api/client';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { SelectField } from '../../components/ui/SelectField';
import { CitiesSettingsSection } from './settings/cities/CitiesSettingsSection';
import { PlacesSettingsSection } from './settings/places/PlacesSettingsSection';
import { ProtocolsSettingsSection } from './settings/protocols/ProtocolsSettingsSection';
import type { ConfirmState, PlaceItem, SettingsTab, StatusLevel } from './types';

type SettingsPageProps = {
    settingsTab: SettingsTab;
    appSettingsForm: { name: string; description: string; recordings_dir: string; scan_start_in: number };
    setAppSettingsForm: (next: { name: string; description: string; recordings_dir: string; scan_start_in: number }) => void;
    setAppSettings: Dispatch<SetStateAction<AppSettings>>;
    setPublicHost: (value: string) => void;
    outputFormat: 'mp4' | 'mkv';
    onOutputFormatChange: (value: 'mp4' | 'mkv') => Promise<void> | void;
    protocols: Array<{ id: number; protocol: string; port: number; is_active: boolean }>;
    protocolSearch: string;
    setProtocolSearch: (value: string) => void;
    showInactiveProtocols: boolean;
    setShowInactiveProtocols: (value: boolean) => void;
    places: PlaceItem[];
    placeTabSearch: string;
    setPlaceTabSearch: (value: string) => void;
    showInactivePlaces: boolean;
    setShowInactivePlaces: (value: boolean) => void;
    cities: CityApi[];
    citySearch: string;
    setCitySearch: (value: string) => void;
    showInactiveCities: boolean;
    setShowInactiveCities: (value: boolean) => void;
    cptecApiOnline: boolean | null;
    fetchCptecCity: (cityName: string, uf?: string) => Promise<{ name: string; uf: string } | null>;
    searchCptecCities: (cityName: string) => Promise<Array<{ name: string; uf: string }>>;
    loadProtocols: () => Promise<void>;
    loadPlaces: () => Promise<void>;
    loadCities: () => Promise<void>;
    showStatus: (level: StatusLevel, msg: string) => void;
    setConfirm: Dispatch<SetStateAction<ConfirmState>>;
    onOpenCitiesSettings: () => void;
};

export const SettingsPage = ({
    settingsTab,
    appSettingsForm,
    setAppSettingsForm,
    setAppSettings,
    setPublicHost,
    outputFormat,
    onOutputFormatChange,
    protocols,
    protocolSearch,
    setProtocolSearch,
    showInactiveProtocols,
    setShowInactiveProtocols,
    places,
    placeTabSearch,
    setPlaceTabSearch,
    showInactivePlaces,
    setShowInactivePlaces,
    cities,
    citySearch,
    setCitySearch,
    showInactiveCities,
    setShowInactiveCities,
    cptecApiOnline,
    fetchCptecCity,
    searchCptecCities,
    loadProtocols,
    loadPlaces,
    loadCities,
    showStatus,
    setConfirm,
    onOpenCitiesSettings,
}: SettingsPageProps) => {
    const outputFormatOptions = [
        { value: 'mp4', label: 'MP4' },
        { value: 'mkv', label: 'MKV' },
    ];

    const handleSaveAppSettings = async (event: FormEvent) => {
        event.preventDefault();
        const name = appSettingsForm.name.trim();
        const description = appSettingsForm.description.trim();
        const scanStartIn = Number(appSettingsForm.scan_start_in || 60);
        if (!name || !description) {
            showStatus('error', 'Informe nome e descrição.');
            return;
        }
        if (!Number.isFinite(scanStartIn) || !Number.isInteger(scanStartIn) || scanStartIn < 5 || scanStartIn > 600) {
            showStatus('error', 'Tempo limite para iniciar a gravação deve ser inteiro entre 5 e 600 segundos.');
            return;
        }
        try {
            const response = await appSettingsAPI.update({
                name,
                description,
                scan_start_in: scanStartIn,
            });
            setAppSettings(response.data);
            setAppSettingsForm({
                name: response.data.name,
                description: response.data.description,
                recordings_dir: response.data.recordings_dir || '/recordings',
                scan_start_in: Number(response.data.scan_start_in || 60),
            });
            setPublicHost(response.data.host);
            showStatus('info', 'Configurações da aplicação salvas.');
        } catch {
            showStatus('error', 'Falha ao salvar configurações do app.');
        }
    };

    const renderTabContent = () => {
        if (settingsTab === 'app') {
            return (
                <Card title="Configurações > Aplicação">
                    <form onSubmit={handleSaveAppSettings} className="space-y-4">
                        <div>
                            <label className="mb-1 block text-sm text-zinc-700">Nome do app</label>
                            <input
                                value={appSettingsForm.name}
                                onChange={(event) => setAppSettingsForm({ ...appSettingsForm, name: event.target.value })}
                                placeholder="Nome do app"
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                            />
                        </div>
                        <div>
                            <label className="mb-1 block text-sm text-zinc-700">Descrição do app</label>
                            <input
                                value={appSettingsForm.description}
                                onChange={(event) => setAppSettingsForm({ ...appSettingsForm, description: event.target.value })}
                                placeholder="Descrição do app"
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                            />
                        </div>
                        <div>
                            <label className="mb-1 block text-sm text-zinc-700">Próximas gravações</label>
                            <SelectField
                                value={outputFormat}
                                options={outputFormatOptions}
                                onValueChange={(value) => {
                                    const next = value === 'mkv' ? 'mkv' : 'mp4';
                                    void onOutputFormatChange(next);
                                }}
                                className="w-full"
                            />
                            <p className="mt-1 text-xs text-zinc-500">Formato padrão para novos arquivos de gravação.</p>
                        </div>
                        <div>
                            <label className="mb-1 block text-sm text-zinc-700">Tempo limite para iniciar a gravação (segundos)</label>
                            <input
                                type="number"
                                min={5}
                                max={600}
                                step={1}
                                inputMode="numeric"
                                value={appSettingsForm.scan_start_in}
                                onChange={(event) => {
                                    const raw = event.target.value;
                                    if (!raw) {
                                        setAppSettingsForm({
                                            ...appSettingsForm,
                                            scan_start_in: 60,
                                        });
                                        return;
                                    }
                                    const parsed = Number(raw);
                                    if (!Number.isFinite(parsed) || !Number.isInteger(parsed)) return;
                                    setAppSettingsForm({
                                        ...appSettingsForm,
                                        scan_start_in: parsed,
                                    });
                                }}
                                placeholder="60"
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                            />
                            <p className="mt-1 text-xs text-zinc-500">Tempo para concluir o início da gravação após scan. Padrão: 60s.</p>
                        </div>
                        <div className="flex justify-end">
                            <Button type="submit" size="sm">Salvar</Button>
                        </div>
                    </form>
                </Card>
            );
        }

        if (settingsTab === 'protocols') {
            return (
                <Card title="Configurações > Protocolos">
                    <ProtocolsSettingsSection
                        protocols={protocols}
                        protocolSearch={protocolSearch}
                        setProtocolSearch={setProtocolSearch}
                        showInactiveProtocols={showInactiveProtocols}
                        setShowInactiveProtocols={setShowInactiveProtocols}
                        loadProtocols={loadProtocols}
                        showStatus={showStatus}
                        setConfirm={setConfirm}
                    />
                </Card>
            );
        }

        if (settingsTab === 'places') {
            return (
                <Card title="Configurações > Locais">
                    <PlacesSettingsSection
                        places={places}
                        placeTabSearch={placeTabSearch}
                        setPlaceTabSearch={setPlaceTabSearch}
                        showInactivePlaces={showInactivePlaces}
                        setShowInactivePlaces={setShowInactivePlaces}
                        cities={cities}
                        cptecApiOnline={cptecApiOnline}
                        fetchCptecCity={fetchCptecCity}
                        onOpenCityRegistration={onOpenCitiesSettings}
                        loadPlaces={loadPlaces}
                        loadCities={loadCities}
                        showStatus={showStatus}
                        setConfirm={setConfirm}
                    />
                </Card>
            );
        }

        if (settingsTab === 'cities') {
            return (
                <Card title="Configurações > Cidades">
                    <CitiesSettingsSection
                        cities={cities}
                        citySearch={citySearch}
                        setCitySearch={setCitySearch}
                        showInactiveCities={showInactiveCities}
                        setShowInactiveCities={setShowInactiveCities}
                        cptecApiOnline={cptecApiOnline}
                        searchCptecCities={searchCptecCities}
                        loadCities={loadCities}
                        showStatus={showStatus}
                        setConfirm={setConfirm}
                    />
                </Card>
            );
        }

        return null;
    };

    return (renderTabContent());
};
