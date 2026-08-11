export const OCR_THRESHOLD_MIN_PERCENT = 0;
export const OCR_THRESHOLD_MAX_PERCENT = 100;
export function validateOcrThresholdPercent(rawValue) {
    const trimmed = rawValue.trim();
    if (!trimmed) {
        return {
            status: "empty",
            value: null,
            message: "Ingresa un umbral OCR entre 0 y 100.",
        };
    }
    const value = Number(trimmed);
    if (!Number.isFinite(value)) {
        return {
            status: "invalid_number",
            value: null,
            message: "El umbral OCR debe ser numerico.",
        };
    }
    if (value < OCR_THRESHOLD_MIN_PERCENT || value > OCR_THRESHOLD_MAX_PERCENT) {
        return {
            status: "out_of_range",
            value: null,
            message: "El umbral OCR debe estar entre 0 y 100.",
        };
    }
    return { status: "valid", value, message: "" };
}
