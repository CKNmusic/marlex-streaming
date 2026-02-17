export const isBrowserQrScanSupported = () => {
    if (typeof window === 'undefined') return false;
    const hasBarcodeDetector = Boolean((window as unknown as { BarcodeDetector?: unknown }).BarcodeDetector);
    const hasCameraApi = Boolean(navigator.mediaDevices?.getUserMedia);
    return hasBarcodeDetector && hasCameraApi;
};
