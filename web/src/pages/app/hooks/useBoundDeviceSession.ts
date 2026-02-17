import { useCallback, useState } from 'react';
import type { Device } from '../../../lib/api/client';
import { session } from '../../../lib/api/client';

export const useBoundDeviceSession = () => {
    const [boundDevice, setBoundDevice] = useState<Device | null>(() => session.getBoundDevice());

    const invalidateScan = useCallback(() => {
        session.clearBoundDevice();
        setBoundDevice(null);
    }, []);

    return { boundDevice, setBoundDevice, invalidateScan };
};
