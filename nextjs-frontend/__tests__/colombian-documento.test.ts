import {
  isValidColombianDocumento,
  sanitizeDocumentoNumero,
} from "@/lib/colombian-documento";

describe("isValidColombianDocumento", () => {
  it("accepts a typical cédula", () => {
    expect(isValidColombianDocumento("CC", "123456789")).toBe(true);
  });

  it("rejects a cédula that is too short or has letters", () => {
    expect(isValidColombianDocumento("CC", "1234")).toBe(false);
    expect(isValidColombianDocumento("CC", "ABC123")).toBe(false);
  });

  it("validates extranjería, pasaporte, PEP and PPT with their own patterns", () => {
    expect(isValidColombianDocumento("CE", "1234567")).toBe(true);
    expect(isValidColombianDocumento("PA", "AB123456")).toBe(true);
    expect(isValidColombianDocumento("PE", "PEP12345678")).toBe(true);
    expect(isValidColombianDocumento("PT", "1234567")).toBe(true);
    expect(isValidColombianDocumento("CE", "12")).toBe(false);
    expect(isValidColombianDocumento("PA", "AB1")).toBe(false);
  });

  it("is false until a tipo is chosen", () => {
    expect(isValidColombianDocumento("", "123456789")).toBe(false);
  });
});

describe("sanitizeDocumentoNumero", () => {
  it("keeps digits for CC and strips letters", () => {
    expect(sanitizeDocumentoNumero("CC", "12a34")).toBe("1234");
  });

  it("uppercases passport characters and drops symbols", () => {
    expect(sanitizeDocumentoNumero("PA", "ab-12 34")).toBe("AB1234");
  });
});
