import { useCallback, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { authAPI, session, usersAPI, withAppBase } from '../lib/api/client';
import { StatusMsg } from '../components/ui/StatusMsg';

type StatusLevel = 'error' | 'warn' | 'info';
type StatusState = { level: StatusLevel; msg: string; time_sec?: number } | null;

export const Login = () => {
    const navigate = useNavigate();
    const location = useLocation();

    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [resetPassword, setResetPassword] = useState('');
    const [resetPasswordConfirm, setResetPasswordConfirm] = useState('');
    const [resetToken, setResetToken] = useState('');
    const [resetMode, setResetMode] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [status, setStatus] = useState<StatusState>(null);
    const [loading, setLoading] = useState(false);
    const clearStatus = useCallback(() => setStatus(null), []);

    const nextPath = new URLSearchParams(location.search).get('next') || '/app';

    const handleLogin = async (event: React.FormEvent) => {
        event.preventDefault();
        setStatus(null);
        setLoading(true);

        try {
            const loginResponse = await authAPI.login(username, password);
            if (loginResponse.data.reset_required) {
                setResetMode(true);
                setResetToken(loginResponse.data.reset_token || '');
                setPassword('');
                setResetPassword('');
                setResetPasswordConfirm('');
                return;
            }
            if (!loginResponse.data.access_token) {
                throw new Error('Token ausente.');
            }
            session.setToken(loginResponse.data.access_token);

            const meResponse = await usersAPI.getMe();
            session.setUser(meResponse.data);

            navigate(nextPath, { replace: true });
        } catch {
            setStatus({ level: 'error', msg: 'Credenciais inválidas.', time_sec: 3 });
            session.clear();
        } finally {
            setLoading(false);
        }
    };

    const handleResetPassword = async (event: React.FormEvent) => {
        event.preventDefault();
        setStatus(null);
        if (!resetPassword.trim()) {
            setStatus({ level: 'error', msg: 'Informe a nova senha.', time_sec: 3 });
            return;
        }
        if (resetPassword !== resetPasswordConfirm) {
            setStatus({ level: 'error', msg: 'As senhas não conferem.', time_sec: 3 });
            return;
        }
        if (!resetToken) {
            setStatus({ level: 'error', msg: 'Token de redefinição inválido.', time_sec: 3 });
            return;
        }
        setLoading(true);
        try {
            const resetResponse = await authAPI.resetPassword(resetToken, resetPassword);
            if (!resetResponse.data.access_token) {
                throw new Error('Token ausente.');
            }
            session.setToken(resetResponse.data.access_token);
            const meResponse = await usersAPI.getMe();
            session.setUser(meResponse.data);
            navigate(nextPath, { replace: true });
        } catch {
            setStatus({ level: 'error', msg: 'Não foi possível redefinir a senha.', time_sec: 3 });
            session.clear();
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
                            <ShieldCheck className="h-7 w-7 text-emerald-400" />
                        </div>
                        <h1 className="text-xl font-semibold text-zinc-900">Medical Streaming</h1>
                        <p className="mt-1 text-sm text-zinc-600">
                            {resetMode ? 'Defina sua nova senha para continuar' : 'Acesse com seu usuário'}
                        </p>
                    </div>

                    {resetMode ? (
                        <form onSubmit={handleResetPassword} className="space-y-4">
                            <div>
                                <label htmlFor="newPassword" className="mb-1 block text-sm text-zinc-700">Nova senha</label>
                                <div className="relative">
                                    <input
                                        id="newPassword"
                                        type={showPassword ? 'text' : 'password'}
                                        value={resetPassword}
                                        onChange={(event) => setResetPassword(event.target.value)}
                                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 pr-10 text-zinc-900 outline-none focus:border-emerald-500"
                                        placeholder="Nova senha"
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword((value) => !value)}
                                        className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-2 text-zinc-600 hover:text-zinc-900 active:text-zinc-900 min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-1 flex items-center justify-center"
                                    >
                                        {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label htmlFor="confirmPassword" className="mb-1 block text-sm text-zinc-700">Confirmar senha</label>
                                <input
                                    id="confirmPassword"
                                    type="password"
                                    value={resetPasswordConfirm}
                                    onChange={(event) => setResetPasswordConfirm(event.target.value)}
                                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-zinc-900 outline-none focus:border-emerald-500 min-h-[44px] sm:min-h-0"
                                    placeholder="Confirmar senha"
                                    required
                                />
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
                                {loading ? 'Salvando...' : 'Salvar e entrar'}
                            </button>
                        </form>
                    ) : (
                        <form onSubmit={handleLogin} className="space-y-4">
                            <div>
                                <label htmlFor="username" className="mb-1 block text-sm text-zinc-700">Usuário</label>
                                <input
                                    id="username"
                                    value={username}
                                    onChange={(event) => setUsername(event.target.value)}
                                    className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2.5 sm:py-2 text-zinc-900 outline-none focus:border-emerald-500 min-h-[44px] sm:min-h-0"
                                    placeholder="admin"
                                    required
                                />
                            </div>

                            <div>
                                <label htmlFor="password" className="mb-1 block text-sm text-zinc-700">Senha</label>
                                <div className="relative">
                                    <input
                                        id="password"
                                        type={showPassword ? 'text' : 'password'}
                                        value={password}
                                        onChange={(event) => setPassword(event.target.value)}
                                        className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 pr-10 text-zinc-900 outline-none focus:border-emerald-500"
                                        placeholder="123"
                                        required
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword((value) => !value)}
                                        className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-2 text-zinc-600 hover:text-zinc-900 active:text-zinc-900 min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 sm:p-1 flex items-center justify-center"
                                    >
                                        {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                                    </button>
                                </div>
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
                                {loading ? 'Entrando...' : 'Entrar'}
                            </button>

                            <p className="text-center text-xs text-zinc-500">
                                Tem um convite?{' '}
                                <button
                                    type="button"
                                    onClick={() => navigate('/register')}
                                    className="text-emerald-600 hover:underline"
                                >
                                    Criar conta
                                </button>
                            </p>
                        </form>
                    )}
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
