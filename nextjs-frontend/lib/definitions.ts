import { z } from "zod";

import {
  isValidColombianMobile,
  sanitizeColombianMobileInput,
  toE164ColombianMobile,
} from "@/lib/colombian-mobile";

const passwordSchema = z
  .string()
  .min(8, "Password should be at least 8 characters.") // Minimum length validation
  .refine((password) => /[A-Z]/.test(password), {
    message: "Password should contain at least one uppercase letter.",
  }) // At least one uppercase letter
  .refine((password) => /[!@#$%^&*(),.?":{}|<>]/.test(password), {
    message: "Password should contain at least one special character.",
  });

export const passwordResetConfirmSchema = z
  .object({
    password: passwordSchema,
    passwordConfirm: z.string(),
    token: z.string({ required_error: "Token is required" }),
  })
  .refine((data) => data.password === data.passwordConfirm, {
    message: "Passwords must match.",
    path: ["passwordConfirm"],
  });

export const otpRequestSchema = z.object({
  email: z.string().email({ message: "Correo electrónico inválido" }),
});

export const otpVerifySchema = z.object({
  email: z.string().email({ message: "Correo electrónico inválido" }),
  code: z
    .string()
    .length(6, { message: "El código debe tener 6 dígitos" })
    .regex(/^\d+$/, { message: "El código solo debe contener números" }),
});

const whatsappSchema = z
  .string()
  .optional()
  .transform((val) => {
    if (!val) return undefined;
    const digits = sanitizeColombianMobileInput(val);
    return isValidColombianMobile(digits) ? toE164ColombianMobile(digits) : val;
  })
  .refine((val) => val === undefined || /^\+573\d{9}$/.test(val), {
    message: "Ingresa un número celular 10 dígitos",
  });

export const onboardingClienteSchema = z.object({
  registration_token: z.string().min(1),
  nombre_completo: z.string().min(1),
  whatsapp: whatsappSchema,
});

export const onboardingProfesionalSchema = z.object({
  registration_token: z.string().min(1),
  nombre_completo: z.string().min(1),
  whatsapp: whatsappSchema,
  documento_tipo: z
    .string()
    .min(1, { message: "El tipo de documento es requerido" }),
  documento_numero: z
    .string()
    .min(1, { message: "El número de documento es requerido" }),
});

export const itemSchema = z.object({
  name: z.string().min(1, { message: "Name is required" }),
  description: z.string().min(1, { message: "Description is required" }),
  quantity: z
    .string()
    .min(1, { message: "Quantity is required" })
    .transform((val) => parseInt(val, 10)) // Convert to integer
    .refine((val) => Number.isInteger(val) && val > 0, {
      message: "Quantity must be a positive integer",
    }),
});
