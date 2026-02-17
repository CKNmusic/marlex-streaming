export type PasswordPolicyResult = {
    score: number;
    level: 'muito_fraca' | 'fraca' | 'media' | 'forte';
    label: string;
    checks: Array<{ key: string; label: string; ok: boolean }>;
    warnings: string[];
};

const COMMON_WEAK_PATTERNS = [
    '123456',
    '12345678',
    '123456789',
    'password',
    'senha',
    'qwerty',
    'admin',
];

const normalize = (text: string) => text.toLowerCase().trim();

const hasThreeSequentialChars = (value: string) => {
    if (value.length < 3) return false;
    const chars = value.toLowerCase();
    for (let index = 0; index <= chars.length - 3; index += 1) {
        const first = chars.charCodeAt(index);
        const second = chars.charCodeAt(index + 1);
        const third = chars.charCodeAt(index + 2);
        if (second === first + 1 && third === second + 1) return true;
    }
    return false;
};

const hasRepeatedChunk = (value: string) => /(.{2,})\1+/i.test(value);

export const evaluatePasswordPolicy = (
    password: string,
    context?: { username?: string | null; fullName?: string | null },
): PasswordPolicyResult => {
    const raw = password || '';
    const normalizedPassword = normalize(raw);
    const username = normalize(context?.username || '');
    const fullName = normalize(context?.fullName || '');

    const checks = [
        { key: 'length', label: 'Mínimo de 12 caracteres', ok: raw.length >= 12 },
        { key: 'lower', label: 'Pelo menos 1 letra minúscula', ok: /[a-z]/.test(raw) },
        { key: 'upper', label: 'Pelo menos 1 letra maiúscula', ok: /[A-Z]/.test(raw) },
        { key: 'digit', label: 'Pelo menos 1 número', ok: /\d/.test(raw) },
        { key: 'symbol', label: 'Pelo menos 1 caractere especial', ok: /[^A-Za-z0-9]/.test(raw) },
        { key: 'space', label: 'Sem espaços em branco', ok: !/\s/.test(raw) },
    ];

    const warnings: string[] = [];
    if (username && normalizedPassword.includes(username)) {
        warnings.push('A senha não deve conter o nome de usuário.');
    }
    if (fullName) {
        const tokens = fullName
            .split(/\s+/)
            .map((token) => token.trim())
            .filter((token) => token.length >= 3);
        if (tokens.some((token) => normalizedPassword.includes(token))) {
            warnings.push('A senha não deve conter partes do nome completo.');
        }
    }
    if (COMMON_WEAK_PATTERNS.some((pattern) => normalizedPassword.includes(pattern))) {
        warnings.push('A senha contém padrão fraco conhecido.');
    }
    if (hasThreeSequentialChars(raw)) {
        warnings.push('Evite sequências óbvias como abc ou 123.');
    }
    if (hasRepeatedChunk(raw)) {
        warnings.push('Evite repetições diretas na senha.');
    }

    let score = 0;
    checks.forEach((check) => {
        if (check.ok) score += 14;
    });
    if (warnings.length === 0) {
        score += 16;
    }
    score = Math.max(0, Math.min(100, score));

    let level: PasswordPolicyResult['level'] = 'muito_fraca';
    let label = 'Muito fraca';
    if (score >= 80) {
        level = 'forte';
        label = 'Forte';
    } else if (score >= 60) {
        level = 'media';
        label = 'Média';
    } else if (score >= 40) {
        level = 'fraca';
        label = 'Fraca';
    }

    return {
        score,
        level,
        label,
        checks,
        warnings,
    };
};

export const validatePasswordForProfileSave = (
    password: string,
    confirmPassword: string,
    context?: { username?: string | null; fullName?: string | null },
): { valid: boolean; message?: string } => {
    const rawPassword = password || '';
    const rawConfirm = confirmPassword || '';
    if (!rawPassword.trim()) {
        return { valid: true };
    }
    if (rawPassword !== rawConfirm) {
        return { valid: false, message: 'A confirmação da senha não confere.' };
    }

    const policy = evaluatePasswordPolicy(rawPassword, context);
    const missingRequirement = policy.checks.find((check) => !check.ok);
    if (missingRequirement) {
        return { valid: false, message: `Senha inválida: ${missingRequirement.label}.` };
    }
    if (policy.warnings.length > 0 || policy.score < 80) {
        return {
            valid: false,
            message: 'Senha fraca. Use combinação forte (12+ chars, maiúsculas, minúsculas, número e símbolo, sem padrões).',
        };
    }
    return { valid: true };
};
