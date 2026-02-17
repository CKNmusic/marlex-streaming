import { useMemo } from 'react';
import type { FormEvent } from 'react';
import { Button } from '../../../components/ui/Button';
import type { User } from '../../../lib/api/client';
import { evaluatePasswordPolicy } from './passwordPolicy';
import type { ProfileSettingsFormState } from './types';

type ProfileSettingsFormProps = {
    user: User | null;
    settingsForm: ProfileSettingsFormState;
    onSettingsChange: (next: ProfileSettingsFormState) => void;
    onSaveSettings: (event: FormEvent) => Promise<void> | void;
    onCancelSettings: () => void;
    savingSettings: boolean;
};

export const ProfileSettingsForm = ({
    user,
    settingsForm,
    onSettingsChange,
    onSaveSettings,
    onCancelSettings,
    savingSettings,
}: ProfileSettingsFormProps) => {
    const shouldValidatePassword = settingsForm.password.length > 0 || settingsForm.password_confirm.length > 0;
    const policy = useMemo(
        () => evaluatePasswordPolicy(settingsForm.password, { username: user?.username, fullName: user?.full_name }),
        [settingsForm.password, user?.full_name, user?.username],
    );
    const confirmMismatch = shouldValidatePassword
        && settingsForm.password_confirm.length > 0
        && settingsForm.password !== settingsForm.password_confirm;

    const strengthClass = policy.level === 'forte'
        ? 'bg-emerald-600'
        : policy.level === 'media'
            ? 'bg-amber-500'
            : policy.level === 'fraca'
                ? 'bg-orange-500'
                : 'bg-red-500';

    return (
        <form onSubmit={onSaveSettings} className="flex-1 space-y-4">
            <div>
                <label className="mb-1 block text-sm text-zinc-700">Usuário</label>
                <input
                    value={user?.username || ''}
                    readOnly
                    className="w-full rounded-md border border-zinc-200 bg-zinc-100 px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                />
            </div>
            <div>
                <label className="mb-1 block text-sm text-zinc-700">Nome</label>
                <input
                    value={settingsForm.full_name}
                    onChange={(event) => onSettingsChange({ ...settingsForm, full_name: event.target.value })}
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                />
            </div>
            <div>
                <label className="mb-1 block text-sm text-zinc-700">Nova senha</label>
                <input
                    type="password"
                    value={settingsForm.password}
                    onChange={(event) => onSettingsChange({ ...settingsForm, password: event.target.value })}
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                    placeholder="Digite uma senha forte"
                    autoComplete="new-password"
                />
            </div>
            <div>
                <label className="mb-1 block text-sm text-zinc-700">Confirmar nova senha</label>
                <input
                    type="password"
                    value={settingsForm.password_confirm}
                    onChange={(event) => onSettingsChange({ ...settingsForm, password_confirm: event.target.value })}
                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-sm outline-none min-h-[44px] sm:min-h-0"
                    placeholder="Confirme a nova senha"
                    autoComplete="new-password"
                />
            </div>
            {shouldValidatePassword ? (
                <div className="space-y-2 rounded-md border border-zinc-200 bg-zinc-50 p-3">
                    <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="text-zinc-700">Nível de segurança</span>
                        <span className="font-medium text-zinc-800">
                            {policy.label} ({policy.score}%)
                        </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200">
                        <div
                            className={`h-full transition-all ${strengthClass}`}
                            style={{ width: `${policy.score}%` }}
                        />
                    </div>
                    <p className="text-xs text-zinc-600">
                        Use senha forte: 12+ caracteres, letras maiúsculas/minúsculas, número e símbolo.
                    </p>
                    <div className="grid gap-1 text-xs text-zinc-700 sm:grid-cols-2">
                        {policy.checks.map((check) => (
                            <p key={check.key} className={check.ok ? 'text-emerald-700' : 'text-zinc-600'}>
                                {check.ok ? 'OK' : '•'} {check.label}
                            </p>
                        ))}
                    </div>
                    {policy.warnings.map((warning) => (
                        <p key={warning} className="text-xs text-amber-700">{warning}</p>
                    ))}
                    {confirmMismatch ? (
                        <p className="text-xs text-red-700">A confirmação da senha não confere.</p>
                    ) : null}
                </div>
            ) : null}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <Button type="button" variant="ghost" onClick={onCancelSettings} disabled={savingSettings} className="w-full sm:w-auto">
                    Cancelar
                </Button>
                <Button type="submit" disabled={savingSettings} className="w-full sm:w-auto">{savingSettings ? 'Salvando...' : 'Salvar'}</Button>
            </div>
        </form>
    );
};
