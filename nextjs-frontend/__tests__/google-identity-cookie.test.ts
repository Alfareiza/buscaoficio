import {
  encodeGoogleIdentity,
  decodeGoogleIdentity,
  setGoogleIdentityCookie,
  GOOGLE_IDENTITY_COOKIE,
} from "@/lib/google-identity-cookie";

describe("google-identity-cookie", () => {
  it("round-trips an identity through encode/decode", () => {
    const identity = {
      name: "Alfonso",
      email: "alfonso@example.com",
      picture: "https://lh3.googleusercontent.com/a/pic.jpg",
    };

    expect(decodeGoogleIdentity(encodeGoogleIdentity(identity))).toEqual(identity);
  });

  it("round-trips a null picture", () => {
    const identity = { name: "Alfonso", email: "a@example.com", picture: null };

    expect(decodeGoogleIdentity(encodeGoogleIdentity(identity))).toEqual(identity);
  });

  it("round-trips non-ASCII names (the reason the value is base64-encoded)", () => {
    const identity = {
      name: "José Muñoz Ríos",
      email: "jose@example.com",
      picture: null,
    };

    expect(decodeGoogleIdentity(encodeGoogleIdentity(identity))).toEqual(identity);
  });

  it("returns null for undefined, malformed, or wrong-shaped values", () => {
    expect(decodeGoogleIdentity(undefined)).toBeNull();
    expect(decodeGoogleIdentity("not base64 json")).toBeNull();
    expect(
      decodeGoogleIdentity(Buffer.from('{"name":"only"}').toString("base64")),
    ).toBeNull();
  });

  it("writes a long-lived httpOnly cookie under the expected name", () => {
    const set = jest.fn();

    setGoogleIdentityCookie(
      { set },
      { name: "Alfonso", email: "alfonso@example.com", picture: null },
    );

    expect(set).toHaveBeenCalledWith(
      GOOGLE_IDENTITY_COOKIE,
      expect.any(String),
      expect.objectContaining({
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        maxAge: 60 * 60 * 24 * 365,
      }),
    );
  });
});
