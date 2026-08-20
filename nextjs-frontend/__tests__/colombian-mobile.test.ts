import {
  isValidColombianMobile,
  sanitizeColombianMobileInput,
  toE164ColombianMobile,
} from "@/lib/colombian-mobile";

describe("sanitizeColombianMobileInput", () => {
  it("strips a leading + and the 57 country code", () => {
    expect(sanitizeColombianMobileInput("+573001234567")).toBe("3001234567");
    expect(sanitizeColombianMobileInput("+57 300 123 4567")).toBe("3001234567");
    expect(sanitizeColombianMobileInput("573001234567")).toBe("3001234567");
  });

  it("strips a leading + without a country code", () => {
    expect(sanitizeColombianMobileInput("+3001234567")).toBe("3001234567");
  });

  it("keeps a local 10-digit mobile and drops separators", () => {
    expect(sanitizeColombianMobileInput("300-123-4567")).toBe("3001234567");
    expect(sanitizeColombianMobileInput("300 123 4567")).toBe("3001234567");
  });

  it("caps the value at 10 digits", () => {
    expect(sanitizeColombianMobileInput("300123456789")).toBe("3001234567");
  });

  it("does not strip a leading 57 until a mobile digit follows", () => {
    expect(sanitizeColombianMobileInput("57")).toBe("57");
    expect(sanitizeColombianMobileInput("573")).toBe("3");
  });
});

describe("isValidColombianMobile", () => {
  it("accepts a 10-digit mobile starting with 3", () => {
    expect(isValidColombianMobile("3001234567")).toBe(true);
    expect(isValidColombianMobile("3159876543")).toBe(true);
  });

  it("rejects incomplete, landline, or non-mobile numbers", () => {
    expect(isValidColombianMobile("")).toBe(false);
    expect(isValidColombianMobile("300123456")).toBe(false);
    expect(isValidColombianMobile("6012345678")).toBe(false);
    expect(isValidColombianMobile("2001234567")).toBe(false);
  });
});

describe("toE164ColombianMobile", () => {
  it("prefixes the national number with +57", () => {
    expect(toE164ColombianMobile("3001234567")).toBe("+573001234567");
  });
});
