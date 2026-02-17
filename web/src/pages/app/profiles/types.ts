import type { FormEvent } from 'react';
import type { User } from '../../../lib/api/client';

export type ProfileSettingsFormState = {
    full_name: string;
    password: string;
    password_confirm: string;
};

export type ProfilePageProps = {
    user: User | null;
    profilePhotoUrl: string;
    onClearPhoto: () => void;
    onPhotoClick: () => void;
    onRemovePhoto: () => Promise<void> | void;
    settingsForm: ProfileSettingsFormState;
    onSettingsChange: (next: ProfileSettingsFormState) => void;
    onSaveSettings: (event: FormEvent) => Promise<void> | void;
    onCancelSettings: () => void;
    savingSettings: boolean;
};
