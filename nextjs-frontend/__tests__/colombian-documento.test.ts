import {
  isValidColombianDocumento,
  sanitizeDocumentoNumero,
} from "@/lib/colombian-documento";
import { onboardingProfesionalSchema } from "@/lib/definitions";

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

  it("is false for a tipo that has no pattern", () => {
    expect(isValidColombianDocumento("TI", "123456789")).toBe(false);
  });
});

describe("onboardingProfesionalSchema documento_tipo", () => {
  const base = {
    registration_token: "tok",
    nombre_completo: "Ana Pérez",
    documento_numero: "123456789",
    zona_ids: ["22222222-2222-4222-8222-222222222001"],
    categoria_ids: ["11111111-1111-4111-8111-111111110001"],
  };

  it("accepts a known tipo", () => {
    expect(
      onboardingProfesionalSchema.safeParse({
        ...base,
        documento_tipo: "CC",
      }).success,
    ).toBe(true);
  });

  it("rejects an unknown tipo without throwing", () => {
    expect(() =>
      onboardingProfesionalSchema.safeParse({
        ...base,
        documento_tipo: "TI",
      }),
    ).not.toThrow();
    expect(
      onboardingProfesionalSchema.safeParse({
        ...base,
        documento_tipo: "TI",
      }).success,
    ).toBe(false);
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

describe("onboardingProfesionalSchema documento_tipo", () => {
  const base = {
    registration_token: "tok",
    nombre_completo: "Ana Pérez",
    documento_numero: "123456789",
    zona_ids: ["22222222-2222-4222-8222-222222222001"],
    categoria_ids: ["11111111-1111-4111-8111-111111110001"],
  };

  it("accepts a known tipo", () => {
    expect(
      onboardingProfesionalSchema.safeParse({
        ...base,
        documento_tipo: "CC",
      }).success,
    ).toBe(true);
  });

  it("rejects an unknown tipo without throwing", () => {
    const parse = () =>
      onboardingProfesionalSchema.safeParse({
        ...base,
        documento_tipo: "TI",
      });
    expect(parse).not.toThrow();
    expect(parse().success).toBe(false);
  });
});
