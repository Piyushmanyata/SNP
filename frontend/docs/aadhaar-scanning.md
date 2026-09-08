# Aadhaar scan lifecycle

The server owns Aadhaar parsing and returns `card` only for accepted identity data. Camera, upload, and USB/paste capture pass the QR text to `/aadhaar/decode`.

`useAadhaarDecode` exposes `cancelDecode` to invalidate pending recognition and responses. The scanner calls it when stopping, starting, or switching cameras and when using the fallback upload or USB/paste actions. A newer decode, upload, and unmount also invalidate older requests. An invalidated upload cannot start decoding after recognition finishes. An invalidated response cannot populate identity, display an error, or clear a newer request's busy state. Cancellation does not require the HTTP response to stop arriving.

The scanner component tests cover stopping during decoding, restarting before an older success or error arrives, and cancelling upload recognition during bitmap creation or native/WASM detection. Successful XML capture fixtures use the supported `PrintLetterBarcodeData` format and `secure_qr_xml` source.

Run focused scanner verification from `frontend` with `npm test -- --runInBand src/components/AadhaarScanner.test.js src/components/aadhaar/liveScan/liveScanEngine.test.js`.
