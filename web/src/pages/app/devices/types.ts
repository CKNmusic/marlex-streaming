import type { FormEvent } from 'react';
import type { CityApi, Device, DeviceStatus, MarkApi } from '../../../lib/api/client';
import type { DeviceActivityFilter, DevicesView, PlaceItem } from '../types';

export type DeviceFormState = {
    mark_id: string;
    model: string;
    sn: string;
    place_id: string;
    protocol: string;
};

export type DevicesPageProps = {
    isAdmin: boolean;
    devicesView: DevicesView;
    selectedDevice: Device | null;
    places: PlaceItem[];
    cities: CityApi[];
    marks: MarkApi[];
    devicesFiltered: Device[];
    deviceStatus: Record<number, DeviceStatus>;
    deviceForm: DeviceFormState;
    citySearch: string;
    placeSearch: string;
    deviceSearch: string;
    deviceActivityFilter: DeviceActivityFilter;
    savingDevice: boolean;
    qrImageUrl: string;
    showQrCode: boolean;
    protocols: Array<{ protocol: string; port: number; url: string; is_active: boolean }>;
    availableProtocols: Array<{ id: number; protocol: string; port: number; is_active: boolean }>;
    scanUrl: string;
    onViewChange: (view: DevicesView) => void;
    onDeviceFormChange: (next: DeviceFormState) => void;
    onCitySearchChange: (value: string) => void;
    onPlaceSearchChange: (value: string) => void;
    onDeviceSearchChange: (value: string) => void;
    onDeviceActivityFilterChange: (value: DeviceActivityFilter) => void;
    onSaveDevice: (event: FormEvent) => Promise<void> | void;
    onOpenDeviceEdit: (device: Device) => void;
    onOpenDeviceNew: () => void;
    onOpenDeviceView: (device: Device) => void;
    onConfirmDeactivate: (device: Device) => void;
    onConfirmDelete: (device: Device) => void;
    onOpenPrintModal: (open: boolean) => void;
    onGenerateQrCode: () => void;
};
