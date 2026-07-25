import { z } from "zod";

/**
 * Zod schemas are the single source of truth for API types — the TS types below
 * are inferred from them, and every response is parsed at the boundary. A schema
 * drift between backend and frontend surfaces here as a clear error instead of
 * an `undefined` deep inside a render.
 */

export const personSchema = z.object({
  id: z.number(),
  name: z.string(),
  is_owner: z.boolean(),
});

export const participantSchema = z.object({
  id: z.number(),
  person_id: z.number(),
  display_name: z.string(),
  is_owner: z.boolean(),
});

export const itemSchema = z.object({
  id: z.number(),
  name: z.string(),
  quantity: z.number(),
  unit_price_cents: z.number(),
  total_cents: z.number(),
  position: z.number(),
  participant_ids: z.array(z.number()),
});

export const billSchema = z.object({
  id: z.number(),
  label: z.string(),
  merchant: z.string().nullable(),
  bill_date: z.string().nullable(),
  position: z.number(),
  payer_id: z.number().nullable(),
  tax_cents: z.number(),
  tip_cents: z.number(),
  fee_cents: z.number(),
  discount_cents: z.number(),
  source_filename: z.string().nullable(),
  source_type: z.string(),
  extraction_status: z.string(),
  extraction_error: z.string().nullable(),
  extracted_total_cents: z.number().nullable(),
  items: z.array(itemSchema),
});

export const shareSchema = z.object({
  participant_id: z.number(),
  subtotal_cents: z.number(),
  tax_cents: z.number(),
  tip_cents: z.number(),
  fee_cents: z.number(),
  discount_cents: z.number(),
  total_cents: z.number(),
});

export const billBreakdownSchema = z.object({
  bill_id: z.number(),
  label: z.string(),
  items_total_cents: z.number(),
  grand_total_cents: z.number(),
  payer_id: z.number().nullable(),
  is_complete: z.boolean(),
  unassigned_item_ids: z.array(z.number()),
  shares: z.array(shareSchema),
  item_shares: z.record(z.string(), z.record(z.string(), z.number())),
});

export const debtSchema = z.object({
  from_participant_id: z.number(),
  to_participant_id: z.number(),
  amount_cents: z.number(),
});

export const totalsSchema = z.object({
  grand_total_cents: z.number(),
  is_complete: z.boolean(),
  totals_cents: z.record(z.string(), z.number()),
  paid_cents: z.record(z.string(), z.number()),
  net_cents: z.record(z.string(), z.number()),
  debts: z.array(debtSchema),
  bills: z.array(billBreakdownSchema),
});

export const eventSchema = z.object({
  id: z.number(),
  name: z.string(),
  notes: z.string().nullable(),
  created_at: z.string(),
  participants: z.array(participantSchema),
  bills: z.array(billSchema),
  totals: totalsSchema.nullable(),
});

export const eventSummarySchema = z.object({
  id: z.number(),
  name: z.string(),
  created_at: z.string(),
  bill_count: z.number(),
  participant_count: z.number(),
  grand_total_cents: z.number(),
});

export const configSchema = z.object({
  extraction_enabled: z.boolean(),
  max_upload_mb: z.number(),
  currency: z.string(),
});

export type Person = z.infer<typeof personSchema>;
export type Participant = z.infer<typeof participantSchema>;
export type Item = z.infer<typeof itemSchema>;
export type Bill = z.infer<typeof billSchema>;
export type Share = z.infer<typeof shareSchema>;
export type BillBreakdown = z.infer<typeof billBreakdownSchema>;
export type Debt = z.infer<typeof debtSchema>;
export type Totals = z.infer<typeof totalsSchema>;
export type EventDetail = z.infer<typeof eventSchema>;
export type EventSummary = z.infer<typeof eventSummarySchema>;
export type AppConfig = z.infer<typeof configSchema>;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let detail = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body?.detail)) {
      // FastAPI validation errors
      detail = body.detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "";
          return field ? `${field}: ${d.msg}` : d.msg;
        })
        .join("; ");
    }
  } catch {
    /* non-JSON body — keep the generic message */
  }
  return new ApiError(res.status, detail);
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init?.headers
        : { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return schema.parse(await res.json());
}

const json = (body: unknown) => JSON.stringify(body);

export const api = {
  config: () => request("/api/config", configSchema),

  listPeople: () => request("/api/people", z.array(personSchema)),
  createPerson: (name: string, isOwner = false) =>
    request("/api/people", personSchema, {
      method: "POST",
      body: json({ name, is_owner: isOwner }),
    }),
  getOwner: async (): Promise<Person | null> => {
    const res = await fetch("/api/people/owner");
    if (res.status === 404) return null;
    if (!res.ok) throw await toApiError(res);
    return personSchema.parse(await res.json());
  },

  listEvents: () => request("/api/events", z.array(eventSummarySchema)),
  createEvent: (name: string) =>
    request("/api/events", eventSchema, { method: "POST", body: json({ name }) }),
  getEvent: (id: number) => request(`/api/events/${id}`, eventSchema),
  renameEvent: (id: number, name: string) =>
    request(`/api/events/${id}`, eventSchema, { method: "PATCH", body: json({ name }) }),
  deleteEvent: (id: number) =>
    request(`/api/events/${id}`, z.undefined(), { method: "DELETE" }),

  addParticipant: (eventId: number, name: string) =>
    request(`/api/events/${eventId}/participants`, participantSchema, {
      method: "POST",
      body: json({ name }),
    }),
  renameParticipant: (eventId: number, participantId: number, displayName: string) =>
    request(`/api/events/${eventId}/participants/${participantId}`, participantSchema, {
      method: "PATCH",
      body: json({ display_name: displayName }),
    }),
  removeParticipant: (eventId: number, participantId: number) =>
    request(`/api/events/${eventId}/participants/${participantId}`, z.undefined(), {
      method: "DELETE",
    }),

  createBill: (eventId: number) =>
    request(`/api/events/${eventId}/bills`, billSchema, { method: "POST", body: json({}) }),
  uploadBill: (eventId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/api/events/${eventId}/bills/upload`, billSchema, {
      method: "POST",
      body: form,
    });
  },
  updateBill: (billId: number, patch: Record<string, unknown>) =>
    request(`/api/bills/${billId}`, billSchema, { method: "PATCH", body: json(patch) }),
  deleteBill: (billId: number) =>
    request(`/api/bills/${billId}`, z.undefined(), { method: "DELETE" }),
  assignAll: (billId: number, participantIds: number[], onlyUnassigned = false) =>
    request(`/api/bills/${billId}/assign`, billSchema, {
      method: "POST",
      body: json({ participant_ids: participantIds, only_unassigned: onlyUnassigned }),
    }),

  createItem: (billId: number, item: Record<string, unknown>) =>
    request(`/api/bills/${billId}/items`, itemSchema, { method: "POST", body: json(item) }),
  updateItem: (itemId: number, patch: Record<string, unknown>) =>
    request(`/api/items/${itemId}`, itemSchema, { method: "PATCH", body: json(patch) }),
  deleteItem: (itemId: number) =>
    request(`/api/items/${itemId}`, z.undefined(), { method: "DELETE" }),
  setAssignments: (itemId: number, participantIds: number[]) =>
    request(`/api/items/${itemId}/assignments`, itemSchema, {
      method: "PUT",
      body: json({ participant_ids: participantIds }),
    }),

  exportUrl: (eventId: number) => `/api/events/${eventId}/export.xlsx`,
  sourceUrl: (billId: number) => `/api/bills/${billId}/source`,
};
