import { useCallback, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, UserPlus } from 'lucide-react';
import { authAPI, withAppBase } from '../lib/api/client';
import { StatusMsg } from '../components/ui/StatusMsg';
import { evaluatePasswordPolicy } from './app/profiles/passwordPolicy';

type StatusLevel = 'error' | 'warn' | 'info';
type StatusState = { level: StatusLevel; msg: string; time_sec?: number } | null;

const STRENGTH_COLORS: Record<string, string> = {
    muito_fraca: 'bg-red-500',
    fraca: 'bg-orange-500',
    media: 'bg-yellow-500',
    forte: 'bg-emerald-500',
};

export const RegisterPage = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const queryCode = new URLSearchParams(location.search).get('code') || '';

    const [inviteCode, setInviteCode] = useState(queryCode);
    const [username, setUsername] = useState('');
    const [fullName, setFullName] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [status, setStatus] = useState<StatusState>(null);
    const [loading, setLoading] = useState(false);
    const clearStatus = useCallback(() => setStatus(null), []);

    const policy = evaluatePasswordPolicy(password, { username, fullName });
    const strengthColor = STRENGTH_COLORS[policy.level] || 'bg-zinc-300';

    const handleSubmit = async (event: React.FormEvent) => {
        event.preventDefault();
        setStatus(null);

        if (!inviteCode.trim()) {
            setStatus({ level: 'error', msg: 'Informe o código de convite.', time_sec: 4 });
            return;
        }
        if (!username.trim()) {
            setStatus({ level: 'error', msg: 'Informe o nome de usuário.', time_sec: 4 });
            return;
        }
        if (!fullName.trim()) {
            setStatus({ level: 'error', msg: 'Informe o nome completo.', time_sec: 4 });
            return;
        }
        if (!password.trim()) {
            setStatus({ level: 'error', msg: 'Informe a senha.', time_sec: 4 });
            return;
        }
        if (password !== confirmPassword) {
            setStatus({ level: 'error', msg: 'As senhas não conferem.', time_sec: 4 });
            return;
        }

        const missingCheck = policy.checks.find((c) => !c.ok);
        if (missingCheck) {
            setStatus({ level: 'error', msg: `Senha inválida: ${missingCheck.label}.`, time_sec: 5 });
            return;
        }
        if (policy.score < 80) {
            setStatus({ level: 'error', msg: 'Senha fraca. Use combinação mais forte.', time_sec: 5 });
            return;
        }

        setLoading(true);
        try {
            await authAPI.register({
                invite_code: inviteCode.trim(),
                username: username.trim(),
                password,
                full_name: fullName.trim(),
            });
            setStatus({ level: 'info', msg: 'Conta criada com sucesso! Redirecionando...' });
            setTimeout(() => {
                navigate('/login', { replace: true });
            }, 2000);
        } catch (error) {
            const axiosError = error as { response?: { data?: { detail?: string }; status?: number } };
            const detail = axiosError.response?.data?.detail;
            if (axiosError.response?.status === 400 || axiosError.response?.status === 404) {
                setStatus({ level: 'error', msg: detail || 'Código de convite inválido ou expirado.', time_sec: 5 });
            } else if (axiosError.response?.status === 409) {
                setStatus({ level: 'error', msg: detail || 'Nome de usuário já está em uso.', time_sec: 5 });
            } else {
                setStatus({ level: 'error', msg: detail || 'Falha ao criar conta. Tente novamente.', time_sec: 5 });
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex min-h-screen flex-col bg-zinc-50 px-4">
            <div className="flex flex-1 items-center justify-center">
                <div className="w-full max-w-sm rounded-2xl border border-zinc-200 bg-white p-8 shadow-xl">
                    <div className="mb-6 flex flex-col items-center text-center">
                        <div className="mb-3 rounded-full bg-emerald-500/10 p-3 ring-1 ring-emerald-500/30">
                            <UserPlus className="h-7 w-7 text-emerald-400" />
                        </div>
                        <h1 className="text-xl font-semibold text-zinc-900">Criar conta</h1>
                        <p className="mt-1 text-sm text-zinc-600">
                            Informe o código de convite e seus dados
                        </p>
                    </div>

                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <label htmlFor="inviteCode" className="mb-1 block text-sm text-zinc-700">Código de convite</label>
                            <input
                                id="inviteCode"
                                value={inviteCode}
                                onChange={(e) => setInviteCode(e.target.value)}
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-zinc-900 outline-none focus:border-emerald-500 min-h-[44px] sm:min-h-0 font-mono tracking-wider"
                                placeholder="XXXX-XXXX"
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="regUsername" className="mb-1 block text-sm text-zinc-700">Nome de usuário</label>
                            <input
                                id="regUsername"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-zinc-900 outline-none focus:border-emerald-500 min-h-[44px] sm:min-h-0"
                                placeholder="medico01"
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="regFullName" className="mb-1 block text-sm text-zinc-700">Nome completo</label>
                            <input
                                id="regFullName"
                                value={fullName}
                                onChange={(e) => setFullName(e.target.value)}
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-zinc-900 outline-none focus:border-emerald-500 min-h-[44px] sm:min-h-0"
                                placeholder="Dr. João Silva"
                                required
                            />
                        </div>

                        <div>
                            <label htmlFor="regPassword" className="mb-1 block text-sm text-zinc-700">Senha</label>
                            <div className="relative">
                                <input
                                    id="regPassword"
                                    type={showPassword ? 'text' : 'password'}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 pr-10 text-zinc-900 outline-none focus:border-emerald-500"
                                    placeholder="Senha forte"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword((v) => !v)}
                                    className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-2 text-zinc-600 hover:text-zinc-900 min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-1 flex items-center justify-center"
                                >
                                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                            {password ? (
                                <div className="mt-2 space-y-1">
                                    <div className="flex items-center gap-2">
                                        <div className="h-1.5 flex-1 rounded-full bg-zinc-200">
                                            <div
                                                className={`h-full rounded-full transition-all ${strengthColor}`}
                                                style={{ width: `${policy.score}%` }}
                                            />
                                        </div>
                                        <span className="text-[11px] text-zinc-500">{policy.label}</span>
                                    </div>
                                    {policy.checks.filter((c) => !c.ok).length > 0 ? (
                                        <ul className="space-y-0.5 text-[11px] text-zinc-500">
                                            {policy.checks.filter((c) => !c.ok).map((c) => (
                                                <li key={c.key}>{c.label}</li>
                                            ))}
                                        </ul>
                                    ) : null}
                                    {policy.warnings.length > 0 ? (
                                        <ul className="space-y-0.5 text-[11px] text-amber-600">
                                            {policy.warnings.map((w, i) => (
                                                <li key={i}>{w}</li>
                                            ))}
                                        </ul>
                                    ) : null}
                                </div>
                            ) : null}
                        </div>

                        <div>
                            <label htmlFor="regConfirmPassword" className="mb-1 block text-sm text-zinc-700">Confirmar senha</label>
                            <input
                                id="regConfirmPassword"
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-zinc-900 outline-none focus:border-emerald-500 min-h-[44px] sm:min-h-0"
                                placeholder="Confirmar senha"
                                required
                            />
                            {confirmPassword && password !== confirmPassword ? (
                                <p className="mt-1 text-[11px] text-red-500">As senhas não conferem.</p>
                            ) : null}
                        </div>

                        {status ? (
                            <StatusMsg
                                level={status.level}
                                msg={status.msg}
                                time_sec={status.time_sec}
                                onClear={clearStatus}
                            />
                        ) : null}

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full rounded-md bg-emerald-600 px-4 py-3 sm:py-2 font-medium text-white transition hover:bg-emerald-500 active:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-70 min-h-[48px] sm:min-h-0"
                        >
                            {loading ? 'Criando conta...' : 'Criar conta'}
                        </button>

                        <p className="text-center text-xs text-zinc-500">
                            Já tem conta?{' '}
                            <button
                                type="button"
                                onClick={() => navigate('/login')}
                                className="text-emerald-600 hover:underline"
                            >
                                Entrar
                            </button>
                        </p>
                    </form>
                </div>
            </div>
            <footer className="pb-4">
                <div className="flex justify-center sm:justify-end">
                    <img
                        src={withAppBase('/marlex-logo.svg')}
                        alt="Marlex"
                        className="h-7 w-auto opacity-90"
                    />
                </div>
            </footer>
        </div>
    );
};
