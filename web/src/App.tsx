import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Login } from './pages/Login';
import { RegisterPage } from './pages/RegisterPage';
import { AppPage } from './pages/app/AppPage';
import { ScanBindPage } from './pages/ScanBindPage';
import { APP_BASE_PATH, session } from './lib/api/client';

const RequireAuth = ({ children }: { children: React.ReactElement }) => {
    const location = useLocation();
    const token = session.getToken();

    if (!token) {
        const next = encodeURIComponent(`${location.pathname}${location.search}`);
        return <Navigate to={`/login?next=${next}`} replace />;
    }

    return children;
};

const RootRedirect = () => {
    const token = session.getToken();
    return token ? <Navigate to="/app" replace /> : <Navigate to="/login" replace />;
};

function App() {
    return (
        <BrowserRouter basename={APP_BASE_PATH === '/' ? undefined : APP_BASE_PATH}>
            <Routes>
                <Route path="/" element={<RootRedirect />} />
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<RegisterPage />} />
                <Route
                    path="/app"
                    element={
                        <RequireAuth>
                            <AppPage />
                        </RequireAuth>
                    }
                />
                <Route
                    path="/scan"
                    element={<ScanBindPage />}
                />
                <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
        </BrowserRouter>
    );
}

export default App;
