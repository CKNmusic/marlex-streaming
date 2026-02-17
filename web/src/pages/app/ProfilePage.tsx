import { Card } from '../../components/ui/Card';
import { ProfilePhotoPanel } from './profiles/ProfilePhotoPanel';
import { ProfileSettingsForm } from './profiles/ProfileSettingsForm';
import type { ProfilePageProps } from './profiles/types';

export const ProfilePage = ({
    user,
    profilePhotoUrl,
    onClearPhoto,
    onPhotoClick,
    onRemovePhoto,
    settingsForm,
    onSettingsChange,
    onSaveSettings,
    onCancelSettings,
    savingSettings,
}: ProfilePageProps) => (
    <Card title="Perfil">
        <div className="flex flex-wrap gap-6">
            <ProfilePhotoPanel
                profilePhotoUrl={profilePhotoUrl}
                onClearPhoto={onClearPhoto}
                onPhotoClick={onPhotoClick}
                onRemovePhoto={onRemovePhoto}
            />
            <ProfileSettingsForm
                user={user}
                settingsForm={settingsForm}
                onSettingsChange={onSettingsChange}
                onSaveSettings={onSaveSettings}
                onCancelSettings={onCancelSettings}
                savingSettings={savingSettings}
            />
        </div>
    </Card>
);
