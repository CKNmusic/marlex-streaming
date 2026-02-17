import { Card } from '../../components/ui/Card';
import { DeviceFormPage } from './devices/DeviceFormPage';
import { DevicesListPage } from './devices/DevicesListPage';
import { DeviceViewPage } from './devices/DeviceViewPage';
import type { DevicesPageProps } from './devices/types';

export const DevicesPage = ({
    isAdmin,
    devicesView,
    selectedDevice,
    places,
    cities,
    marks,
    devicesFiltered,
    deviceStatus,
    deviceForm,
    citySearch,
    placeSearch,
    deviceSearch,
    deviceActivityFilter,
    savingDevice,
    qrImageUrl,
    showQrCode,
    protocols,
    availableProtocols,
    scanUrl,
    onViewChange,
    onDeviceFormChange,
    onCitySearchChange,
    onPlaceSearchChange,
    onDeviceSearchChange,
    onDeviceActivityFilterChange,
    onSaveDevice,
    onOpenDeviceEdit,
    onOpenDeviceNew,
    onOpenDeviceView,
    onConfirmDeactivate,
    onConfirmDelete,
    onOpenPrintModal,
    onGenerateQrCode,
}: DevicesPageProps) => {
    if (!isAdmin) {
        return <Card title="Dispositivos"><p className="text-sm text-zinc-600">Somente master.</p></Card>;
    }

    if (devicesView === 'view' && selectedDevice) {
        return (
            <DeviceViewPage
                selectedDevice={selectedDevice}
                places={places}
                deviceStatus={deviceStatus}
                qrImageUrl={qrImageUrl}
                showQrCode={showQrCode}
                protocols={protocols}
                scanUrl={scanUrl}
                onViewBack={() => onViewChange('list')}
                onOpenPrintModal={onOpenPrintModal}
                onGenerateQrCode={onGenerateQrCode}
                onOpenDeviceEdit={onOpenDeviceEdit}
            />
        );
    }

    if (devicesView === 'edit' || devicesView === 'new') {
        return (
            <DeviceFormPage
                devicesView={devicesView}
                selectedDevice={selectedDevice}
                places={places}
                cities={cities}
                marks={marks}
                deviceForm={deviceForm}
                citySearch={citySearch}
                placeSearch={placeSearch}
                savingDevice={savingDevice}
                availableProtocols={availableProtocols}
                onViewBack={() => onViewChange('list')}
                onSaveDevice={onSaveDevice}
                onDeviceFormChange={onDeviceFormChange}
                onCitySearchChange={onCitySearchChange}
                onPlaceSearchChange={onPlaceSearchChange}
                onConfirmDeactivate={onConfirmDeactivate}
                onConfirmDelete={onConfirmDelete}
            />
        );
    }

    return (
        <DevicesListPage
            devicesFiltered={devicesFiltered}
            places={places}
            deviceStatus={deviceStatus}
            deviceSearch={deviceSearch}
            deviceActivityFilter={deviceActivityFilter}
            onDeviceSearchChange={onDeviceSearchChange}
            onDeviceActivityFilterChange={onDeviceActivityFilterChange}
            onOpenDeviceNew={onOpenDeviceNew}
            onOpenDeviceView={onOpenDeviceView}
        />
    );
};
