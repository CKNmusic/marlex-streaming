import { Pencil, Trash2, User as UserIcon } from 'lucide-react';

const profilePhotoFallback = (
    <div className="flex h-full w-full items-center justify-center text-zinc-600">
        <UserIcon className="h-10 w-10" />
    </div>
);

type ProfilePhotoPanelProps = {
    profilePhotoUrl: string;
    onClearPhoto: () => void;
    onPhotoClick: () => void;
    onRemovePhoto: () => Promise<void> | void;
};

export const ProfilePhotoPanel = ({
    profilePhotoUrl,
    onClearPhoto,
    onPhotoClick,
    onRemovePhoto,
}: ProfilePhotoPanelProps) => (
    <div className="relative">
        <div className="h-28 w-28 overflow-hidden rounded-full border border-zinc-200 bg-white">
            {profilePhotoUrl ? (
                <img
                    src={profilePhotoUrl}
                    alt="Foto do perfil"
                    className="h-full w-full object-cover"
                    onError={onClearPhoto}
                />
            ) : profilePhotoFallback}
        </div>
        <button
            type="button"
            onClick={onPhotoClick}
            className="absolute -left-1 -bottom-1 rounded-full bg-emerald-600 p-3 sm:p-2 text-white min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center"
            title="Alterar foto"
        >
            <Pencil className="h-4 w-4" />
        </button>
        {profilePhotoUrl ? (
            <button
                type="button"
                onClick={() => void onRemovePhoto()}
                className="absolute -right-1 -bottom-1 rounded-full bg-zinc-100 p-3 sm:p-2 text-zinc-700 transition hover:bg-zinc-200 min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center"
                title="Remover foto"
            >
                <Trash2 className="h-4 w-4" />
            </button>
        ) : null}
    </div>
);
