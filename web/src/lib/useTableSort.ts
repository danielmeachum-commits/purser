import { useCallback, useEffect, useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";
export type SortValueType = "string" | "number" | "date";

export interface SortState<K extends string = string> {
  key: K;
  direction: SortDirection;
}

export interface SortColumn<T> {
  /** Pull the raw value out of a row. May return null/undefined — those sort last. */
  accessor: (row: T) => unknown;
  /** Hint for how to compare. Defaults to "string". */
  type?: SortValueType;
}

export interface UseTableSortOptions<T, K extends string> {
  /** Column key -> accessor + type hint. */
  columns: Record<K, SortColumn<T>>;
  /** localStorage key for persisting `{ key, direction }`. */
  storageKey: string;
  /** Optional initial sort. Used when nothing is persisted yet. */
  initial?: SortState<K> | null;
}

export interface UseTableSortResult<T, K extends string> {
  /** Rows sorted per current state. Falls back to the input order when unsorted. */
  sorted: T[];
  /** Current sort state, or `null` when unsorted. */
  sort: SortState<K> | null;
  /** Cycle a column: asc -> desc -> unsorted (3-state). */
  toggle: (key: K) => void;
}

/**
 * Reusable client-side sort with localStorage persistence.
 *
 * Design notes:
 * - 3-state cycle (asc -> desc -> unsorted). Going back to "no sort" matters
 *   here because Transactions has a server-side default order (newest first)
 *   worth preserving.
 * - Null / undefined values always sort to the end, regardless of direction.
 * - Sort is stable via `[value, index]` tiebreaker.
 * - "number" type coerces numeric strings (e.g. `"12.50"`) with `Number()`.
 * - "date" type parses via `new Date(...)`; invalid dates sort last.
 */
export function useTableSort<T, K extends string>(
  rows: readonly T[],
  { columns, storageKey, initial = null }: UseTableSortOptions<T, K>,
): UseTableSortResult<T, K> {
  const [sort, setSort] = useState<SortState<K> | null>(() => readStored<K>(storageKey, initial));

  useEffect(() => {
    try {
      if (sort) localStorage.setItem(storageKey, JSON.stringify(sort));
      else localStorage.removeItem(storageKey);
    } catch {
      // ignore quota / privacy mode errors
    }
  }, [sort, storageKey]);

  const toggle = useCallback(
    (key: K) => {
      setSort((current) => {
        if (!current || current.key !== key) return { key, direction: "asc" };
        if (current.direction === "asc") return { key, direction: "desc" };
        return null;
      });
    },
    [],
  );

  const sorted = useMemo(() => {
    if (!sort) return rows.slice();
    const col = columns[sort.key];
    if (!col) return rows.slice();
    const dir = sort.direction === "asc" ? 1 : -1;
    const type = col.type ?? "string";

    const indexed = rows.map((row, i) => [row, i, col.accessor(row)] as const);
    indexed.sort((a, b) => {
      const av = a[2];
      const bv = b[2];
      const aNull = av === null || av === undefined || av === "";
      const bNull = bv === null || bv === undefined || bv === "";
      if (aNull && bNull) return a[1] - b[1];
      if (aNull) return 1; // nulls always last
      if (bNull) return -1;
      const cmp = compareValues(av, bv, type);
      if (cmp !== 0) return cmp * dir;
      return a[1] - b[1]; // stable tiebreak
    });
    return indexed.map((entry) => entry[0]);
  }, [rows, sort, columns]);

  return { sorted, sort, toggle };
}

function readStored<K extends string>(
  storageKey: string,
  fallback: SortState<K> | null,
): SortState<K> | null {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<SortState<K>>;
    if (
      parsed &&
      typeof parsed.key === "string" &&
      (parsed.direction === "asc" || parsed.direction === "desc")
    ) {
      return { key: parsed.key as K, direction: parsed.direction };
    }
  } catch {
    // ignore
  }
  return fallback;
}

function compareValues(a: unknown, b: unknown, type: SortValueType): number {
  if (type === "number") {
    const an = typeof a === "number" ? a : Number(a as string);
    const bn = typeof b === "number" ? b : Number(b as string);
    const aBad = !Number.isFinite(an);
    const bBad = !Number.isFinite(bn);
    if (aBad && bBad) return 0;
    if (aBad) return 1;
    if (bBad) return -1;
    return an - bn;
  }
  if (type === "date") {
    const at = a instanceof Date ? a.getTime() : new Date(a as string).getTime();
    const bt = b instanceof Date ? b.getTime() : new Date(b as string).getTime();
    const aBad = Number.isNaN(at);
    const bBad = Number.isNaN(bt);
    if (aBad && bBad) return 0;
    if (aBad) return 1;
    if (bBad) return -1;
    return at - bt;
  }
  // string compare (case-insensitive, numeric-aware for things like "abc 10")
  const as = String(a);
  const bs = String(b);
  return as.localeCompare(bs, undefined, { sensitivity: "base", numeric: true });
}
