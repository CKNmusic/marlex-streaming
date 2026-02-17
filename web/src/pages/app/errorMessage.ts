export const extractApiErrorDetail = (error: unknown): string | null => {
    if (!error || typeof error !== 'object') return null;
    const response = (error as { response?: { data?: unknown } }).response;
    const data = response?.data;
    if (typeof data === 'string') return data.trim() || null;
    if (!data || typeof data !== 'object') return null;
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail.trim() || null;
    if (Array.isArray(detail)) {
        const first = detail[0];
        if (first && typeof first === 'object' && 'msg' in first) {
            const message = (first as { msg?: unknown }).msg;
            if (typeof message === 'string') return message.trim() || null;
        }
    }
    return null;
};

export const resolveApiErrorMessage = (error: unknown, fallback: string) => {
    const detail = extractApiErrorDetail(error);
    return detail || fallback;
};

