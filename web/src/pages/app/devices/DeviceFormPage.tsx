import type { FormEvent } from 'react';
import { StopCircle, Trash2 } from 'lucide-react';
import { AutocompleteInput } from '../../../components/ui/AutocompleteInput';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { SelectField } from '../../../components/ui/SelectField';
import type { CityApi, Device, MarkApi } from '../../../lib/api/client';
import type { PlaceItem } from '../types';
import type { DeviceFormState } from './types';

type DeviceFormPageProps = {
    devicesView: 'edit' | 'new';
    selectedDevice: Device | null;
    places: PlaceItem[];
    cities: CityApi[];
    marks: MarkApi[];
    deviceForm: DeviceFormState;
    citySearch: string;
    placeSearch: string;
    savingDevice: boolean;
    availableProtocols: Array<{ id: number; protocol: string; port: number; is_active: boolean }>;
    onViewBack: () => void;
    onSaveDevice: (event: FormEvent) => Promise<void> | void;
    onDeviceFormChange: (next: DeviceFormState) => void;
    onCitySearchChange: (value: string) => void;
    onPlaceSearchChange: (value: string) => void;
    onConfirmDeactivate: (device: Device) => void;
    onConfirmDelete: (device: Device) => void;
};

export const DeviceFormPage = ({
    devicesView,
    selectedDevice,
    places,
    cities,
    marks,
    deviceForm,
    citySearch,
    placeSearch,
    savingDevice,
    availableProtocols,
    onViewBack,
    onSaveDevice,
    onDeviceFormChange,
    onCitySearchChange,
    onPlaceSearchChange,
    onConfirmDeactivate,
    onConfirmDelete,
}: DeviceFormPageProps) => {
    const selectedPlaceId = Number(deviceForm.place_id || 0);
    const activeCities = cities.filter((city) => city.is_active !== false);
    const selectedPlace = places.find((item) => item.id === selectedPlaceId) || null;
    const selectedCityBySearch = activeCities.find((city) => `${city.name}/${city.uf}` === citySearch) || null;
    const selectedCityId = selectedCityBySearch?.id || selectedPlace?.cityId || null;
    const availablePlaces = places.filter((place) => (
        (place.is_active !== false || place.id === selectedPlaceId)
        && (!selectedCityId || place.cityId === selectedCityId || place.id === selectedPlaceId)
    ));
    const cityOptions = activeCities.map((city) => ({
        value: `${city.name}/${city.uf}`,
        label: `${city.name}/${city.uf}`,
    }));
    const placeOptions = availablePlaces.map((place) => ({
        value: `${place.name} - ${place.city}/${place.state}`,
        label: `${place.name} - ${place.city}/${place.state}`,
    }));
    const selectedPlaceCityLabel = selectedPlace ? `${selectedPlace.city}/${selectedPlace.state}` : '';
    const selectedCityValue = citySearch || selectedPlaceCityLabel;
    const selectedPlaceValue = deviceForm.place_id
        ? `${selectedPlace?.name || ''} - ${selectedPlace?.city || ''}/${selectedPlace?.state || ''}`
        : placeSearch;
    const selectedMarkId = Number(deviceForm.mark_id || 0);
    const sortedMarks = [...marks].sort((a, b) => a.name.localeCompare(b.name));
    const markOptions = sortedMarks
        .filter((mark) => mark.is_active !== false || mark.id === selectedMarkId)
        .map((mark) => ({
            value: String(mark.id),
            label: mark.name,
        }));
    if (selectedMarkId && !markOptions.some((item) => item.value === String(selectedMarkId))) {
        markOptions.push({
            value: String(selectedMarkId),
            label: String(selectedDevice?.mark_name || `Marca #${selectedMarkId}`),
        });
    }
    const selectedProtocol = (deviceForm.protocol || '').trim().toLowerCase();
    const normalizedProtocols = availableProtocols.map((item) => ({
        value: String(item.protocol || '').trim().toLowerCase(),
        label: String(item.protocol || '').trim().toUpperCase(),
        is_active: item.is_active !== false,
    })).filter((item) => item.value);
    const hasSelectedProtocol = normalizedProtocols.some((item) => item.value === selectedProtocol);
    const protocolOptions = normalizedProtocols
        .filter((item) => item.is_active || item.value === selectedProtocol)
        .map((item) => ({
            value: item.value,
            label: item.label,
        }));
    if (selectedProtocol && !hasSelectedProtocol) {
        protocolOptions.push({
            value: selectedProtocol,
            label: selectedProtocol.toUpperCase(),
        });
    }

    return (
        <Card title={devicesView === 'new' ? 'Novo dispositivo' : 'Editar dispositivo'} onBack={onViewBack}>
            {devicesView === 'new' ? (
                <p className="mb-4 text-sm text-zinc-600">Preencha os campos do dispositivo.</p>
            ) : null}
            <form onSubmit={onSaveDevice} className="space-y-4">
                <div>
                    <label className="mb-1 block text-sm text-zinc-700">Marca</label>
                    <SelectField
                        value={deviceForm.mark_id}
                        options={markOptions}
                        onValueChange={(value) => onDeviceFormChange({ ...deviceForm, mark_id: value })}
                        placeholder="Selecione a marca"
                    />
                </div>
                <div>
                    <label className="mb-1 block text-sm text-zinc-700">Modelo</label>
                    <input
                        value={deviceForm.model}
                        onChange={(event) => onDeviceFormChange({ ...deviceForm, model: event.target.value })}
                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 outline-none min-h-[44px] sm:min-h-0"
                        required
                    />
                </div>
                <div>
                    <label className="mb-1 block text-sm text-zinc-700">SN</label>
                    <input
                        value={deviceForm.sn}
                        onChange={(event) => onDeviceFormChange({ ...deviceForm, sn: event.target.value })}
                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 outline-none min-h-[44px] sm:min-h-0 disabled:opacity-70"
                        required
                        disabled={devicesView === 'edit'}
                    />
                </div>
                <div>
                    <label className="mb-1 block text-sm text-zinc-700">Protocolo ativo</label>
                    <SelectField
                        value={selectedProtocol}
                        options={protocolOptions}
                        onValueChange={(value) => onDeviceFormChange({ ...deviceForm, protocol: value })}
                        placeholder="Selecione o protocolo"
                    />
                </div>
                <div>
                    <label className="mb-1 block text-sm text-zinc-700">Cidade</label>
                    <AutocompleteInput
                        value={selectedCityValue}
                        options={cityOptions}
                        onValueChange={(value) => {
                            onCitySearchChange(value);
                            const match = activeCities.find((city) => `${city.name}/${city.uf}` === value);
                            if (!match) {
                                onPlaceSearchChange('');
                                onDeviceFormChange({ ...deviceForm, place_id: '' });
                                return;
                            }
                            if (selectedPlace && selectedPlace.cityId === match.id) {
                                return;
                            }
                            onPlaceSearchChange('');
                            onDeviceFormChange({ ...deviceForm, place_id: '' });
                        }}
                        placeholder="Buscar cidade/UF"
                        className="w-full"
                        emptyLabel={citySearch.trim() ? 'Nenhuma cidade ativa encontrada.' : 'Sem cidades ativas disponíveis.'}
                        required
                    />
                </div>
                <div>
                    <label className="mb-1 block text-sm text-zinc-700">Local</label>
                    <AutocompleteInput
                        value={selectedPlaceValue}
                        options={placeOptions}
                        onValueChange={(value) => {
                            onPlaceSearchChange(value);
                            const match = availablePlaces.find((item) => `${item.name} - ${item.city}/${item.state}` === value);
                            if (match) {
                                onCitySearchChange(`${match.city}/${match.state}`);
                            }
                            onDeviceFormChange({
                                ...deviceForm,
                                place_id: match ? String(match.id) : '',
                            });
                        }}
                        placeholder="Buscar local por nome"
                        className="w-full"
                        emptyLabel={placeSearch.trim() ? 'Nenhum local encontrado para este texto.' : 'Sem locais disponíveis.'}
                        required
                    />
                </div>
                {devicesView === 'edit' && selectedDevice ? (
                    <div>
                        <label className="mb-1 block text-sm text-zinc-700">KEY</label>
                        <input
                            value={selectedDevice.key || ''}
                            readOnly
                            className="w-full rounded-md border border-zinc-200 bg-zinc-100/60 px-3 py-2 text-sm font-mono outline-none"
                        />
                    </div>
                ) : null}
                <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:justify-between">
                    {devicesView === 'edit' && selectedDevice ? (
                        <div className="flex flex-col gap-2 sm:flex-row">
                            <Button type="button" variant="secondary" onClick={() => onConfirmDeactivate(selectedDevice)} className="w-full sm:w-auto">
                                <StopCircle className="mr-2 h-4 w-4" />
                                {selectedDevice.is_active ? 'Desativar' : 'Ativar'}
                            </Button>
                            <Button type="button" variant="danger" onClick={() => onConfirmDelete(selectedDevice)} className="w-full sm:w-auto">
                                <Trash2 className="mr-2 h-4 w-4" />
                                Excluir
                            </Button>
                        </div>
                    ) : <div />}
                    <div className="flex flex-col-reverse gap-2 sm:flex-row">
                        <Button type="button" variant="ghost" onClick={onViewBack} className="w-full sm:w-auto">Cancelar</Button>
                        <Button type="submit" disabled={savingDevice} className="w-full sm:w-auto">{savingDevice ? 'Salvando...' : 'Salvar'}</Button>
                    </div>
                </div>
            </form>
        </Card>
    );
};
