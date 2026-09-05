/* The shape of a captured demo run.
 *
 * Produced by `scripts/demo_buy.py --capture`. Every field is a value the demo
 * actually printed, so a number on screen can always be traced back to a line
 * in the run it came from. Nothing here is illustrative.
 */

export type BeatKind =
  | "discovery"
  | "catalog"
  | "policy"
  | "quote"
  | "terms"
  | "statute"
  | "negotiate"
  | "injection"
  | "reserve"
  | "refusal"
  | "authorised"
  | "settled"
  | "declined"
  | "chain";

type Base = {
  n: number;
  id: string;
  kind: BeatKind;
  title: string;
  aside?: string;
};

export type Beat =
  | (Base & { kind: "discovery"; server: string; tools: string[] })
  | (Base & {
      kind: "catalog";
      products: {
        sku: string;
        price: string;
        unit: string;
        hsn: string;
        gst: string;
        stock: number;
      }[];
    })
  | (Base & {
      kind: "policy";
      volume_ladder: { min_qty: number; discount: string }[];
      ceiling: string;
      terms_default_days: number;
      terms_max_days: number;
      terms_ladder: { pay_within_days: number; discount: string }[];
    })
  | (Base & {
      kind: "quote";
      qty: number;
      sku: string;
      terms: string;
      list_unit: string;
      unit: string;
      discount: string;
      total: string;
      total_paise: number;
      cart_hash: string;
    })
  | (Base & {
      kind: "terms";
      line: string;
      rows: {
        label: string;
        unit: string;
        discount: string;
        total: string;
        cart_hash: string;
      }[];
    })
  | (Base & {
      kind: "statute";
      sides: {
        merchant: string;
        class: string;
        ceiling_days: number;
        statutory_cap: string;
        statutory_cap_days: number | null;
        outcome: string;
        detail: string;
      }[];
      reason: string;
      cite: string;
    })
  | (Base & {
      kind: "negotiate" | "injection";
      buyer: string;
      merchant: string;
      unit: string;
      discount: string;
      rounds?: number;
      used_fallback?: boolean;
      detection?: string;
      entitled_bp?: number;
      discretion_bp?: number;
      conceded_bp?: number;
      authority_note?: string;
    })
  | (Base & { kind: "reserve"; state: string; held_until_epoch: number })
  | (Base & {
      kind: "refusal";
      stamp: string;
      code: string;
      authorised: false;
      reason: string;
      cite?: string;
      cart_paise?: number;
      cap_paise?: number;
      over_paise?: number;
    })
  | (Base & {
      kind: "authorised";
      stamp: string;
      authorised: true;
      amount: string;
      cap: string;
      amount_paise: number;
      cap_paise: number;
      reason: string;
      mandate: string;
    })
  | (Base & {
      kind: "settled";
      stamp: string;
      payment_link: string;
      link_status: string;
      payment_id: string;
      payment_status: string;
      amount: string;
      method: string;
    })
  | (Base & {
      kind: "declined";
      stamp: string;
      payment_link: string;
      link_status: string;
      amount_paid: string;
    })
  | (Base & {
      kind: "chain";
      records: number;
      state: string;
      entries: { seq: number; actor: string; action: string }[];
    });

export type Run = {
  provenance: {
    source: string;
    payment_source: string;
    note: string;
    chain_records: number;
    chain_state: string;
  };
  merchants: Record<
    string,
    {
      name: string;
      class: string;
      credit_ceiling_days: number;
      statutory_cap_days: number | null;
      statutory_note: string;
    }
  >;
  beats: Beat[];
};

/* Served by Starlette at /api/theatre/run, and sitting next to the bundle as a
 * plain file so the built page still works opened directly from disk -- which
 * is the fallback if the server will not start in front of an audience. */
export async function loadRun(): Promise<Run> {
  const res = await fetch(`${import.meta.env.BASE_URL}run.json`, { cache: "no-store" });
  if (!res.ok) throw new Error(`run.json ${res.status}`);
  return res.json();
}
