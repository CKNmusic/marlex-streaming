import { RecordCreatePage } from './records/RecordCreatePage';
import { RecordsListPage } from './records/RecordsListPage';
import { RecordViewPage } from './records/RecordViewPage';
import type { RecordsPageProps } from './records/types';

export const RecordsPage = ({
    isAdmin,
    user,
    recordsView,
    records,
    selectedRecord,
    procedures,
    users,
    devices,
    deviceStatus,
    places,
    recordForm,
    recordEditForm,
    recordSearch,
    recordActivityFilter,
    boundDevice,
    recordingBusy,
    savingRecord,
    currentOpenRecord,
    onRecordFormChange,
    onRecordEditChange,
    onRecordSearchChange,
    onRecordActivityFilterChange,
    onStartRecord,
    onSaveRecordEdit,
    onStopRecord,
    onOpenRecordNew,
    onOpenRecordView,
    onCloseRecordsView,
    outputFormat,
    onOpenUserView,
    onOpenDeviceView,
}: RecordsPageProps) => {
    if (recordsView === 'new') {
        return (
            <RecordCreatePage
                isAdmin={isAdmin}
                devices={devices}
                deviceStatus={deviceStatus}
                boundDevice={boundDevice}
                recordForm={recordForm}
                procedures={procedures}
                recordingBusy={recordingBusy}
                onRecordFormChange={onRecordFormChange}
                onStartRecord={onStartRecord}
                onCloseRecordsView={onCloseRecordsView}
            />
        );
    }

    if (recordsView === 'view' && selectedRecord) {
        return (
            <RecordViewPage
                isAdmin={isAdmin}
                selectedRecord={selectedRecord}
                users={users}
                devices={devices}
                places={places}
                deviceStatus={deviceStatus}
                recordEditForm={recordEditForm}
                savingRecord={savingRecord}
                onRecordEditChange={onRecordEditChange}
                onSaveRecordEdit={onSaveRecordEdit}
                onCloseRecordsView={onCloseRecordsView}
                outputFormat={outputFormat}
                onOpenUserView={onOpenUserView}
                onOpenDeviceView={onOpenDeviceView}
            />
        );
    }

    return (
        <RecordsListPage
            isAdmin={isAdmin}
            user={user}
            records={records}
            users={users}
            places={places}
            recordSearch={recordSearch}
            boundDevice={boundDevice}
            deviceStatus={deviceStatus}
            recordActivityFilter={recordActivityFilter}
            currentOpenRecord={currentOpenRecord}
            onRecordSearchChange={onRecordSearchChange}
            onRecordActivityFilterChange={onRecordActivityFilterChange}
            onStopRecord={onStopRecord}
            onOpenRecordNew={onOpenRecordNew}
            onOpenRecordView={onOpenRecordView}
        />
    );
};
