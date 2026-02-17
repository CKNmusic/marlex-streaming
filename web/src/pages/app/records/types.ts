import type { FormEvent } from 'react';
import type { Device, DeviceStatus, Procedure, Record as RecordApi, User } from '../../../lib/api/client';
import type { ActivityFilter, PlaceItem, RecordsView, UsersView } from '../types';

export type RecordFormState = {
    title: string;
    description: string;
    procedure_id: string;
    device_id: string;
};

export type RecordEditFormState = {
    title: string;
    description: string;
};

export type RecordsPageProps = {
    isAdmin: boolean;
    user: User | null;
    recordsView: RecordsView;
    records: RecordApi[];
    selectedRecord: RecordApi | null;
    procedures: Procedure[];
    users: User[];
    devices: Device[];
    deviceStatus: Record<number, DeviceStatus>;
    places: PlaceItem[];
    recordForm: RecordFormState;
    recordEditForm: RecordEditFormState;
    recordSearch: string;
    recordActivityFilter: ActivityFilter;
    boundDevice: Device | null;
    recordingBusy: boolean;
    savingRecord: boolean;
    currentOpenRecord: RecordApi | null;
    onRecordFormChange: (next: RecordFormState) => void;
    onRecordEditChange: (next: RecordEditFormState) => void;
    onRecordSearchChange: (value: string) => void;
    onRecordActivityFilterChange: (value: ActivityFilter) => void;
    onStartRecord: (event: FormEvent) => Promise<void> | void;
    onSaveRecordEdit: (event: FormEvent) => Promise<boolean> | boolean;
    onStopRecord: (recordId: number) => Promise<void> | void;
    onOpenRecordNew: () => void;
    onOpenRecordView: (record: RecordApi) => void;
    onCloseRecordsView: () => void;
    outputFormat: string;
    onOpenUserView: (user: User, view: UsersView) => void;
    onOpenDeviceView: (device: Device) => void;
};
