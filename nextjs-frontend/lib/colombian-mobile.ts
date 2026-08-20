const COLOMBIAN_MOBILE_LENGTH = 10;

export function sanitizeColombianMobileInput(raw: string): string {
  let digits = raw.replace(/\D/g, "");
  const hasCountryCode =
    digits.startsWith("57") &&
    digits.length > 2 &&
    (digits[2] === "3" || digits.length > COLOMBIAN_MOBILE_LENGTH);
  if (hasCountryCode) {
    digits = digits.slice(2);
  }
  return digits.slice(0, COLOMBIAN_MOBILE_LENGTH);
}

export function isValidColombianMobile(digits: string): boolean {
  return /^3\d{9}$/.test(digits);
}

export function toE164ColombianMobile(digits: string): string {
  return `+57${digits}`;
}
