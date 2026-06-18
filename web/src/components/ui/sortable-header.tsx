import * as React from "react";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import type { SortState } from "@/lib/useTableSort";
import { cn } from "@/lib/utils";

export interface SortableHeaderProps<K extends string>
  extends Omit<React.ThHTMLAttributes<HTMLTableCellElement>, "onToggle"> {
  sortKey: K;
  sort: SortState<K> | null;
  onToggle: (key: K) => void;
  /** Align the icon to the right (use for right-aligned columns like amount). */
  align?: "left" | "right";
  children: React.ReactNode;
}

/**
 * A clickable, keyboard-accessible <th> that drives a column's sort state.
 *
 * Wraps shadcn's TableHead; renders the label plus a sort indicator
 * (ArrowUp/ArrowDown when active, neutral ChevronsUpDown when unsorted).
 */
export function SortableHeader<K extends string>({
  sortKey,
  sort,
  onToggle,
  align = "left",
  className,
  children,
  ...rest
}: SortableHeaderProps<K>) {
  const active = sort?.key === sortKey;
  const direction = active ? sort.direction : null;
  const Icon = direction === "asc" ? ArrowUp : direction === "desc" ? ArrowDown : ChevronsUpDown;
  const ariaSort = direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none";

  return (
    <TableHead
      className={cn("p-0", className)}
      aria-sort={ariaSort as React.AriaAttributes["aria-sort"]}
      {...rest}
    >
      <button
        type="button"
        onClick={() => onToggle(sortKey)}
        className={cn(
          "flex h-10 w-full items-center gap-1.5 px-4 text-xs font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-0",
          align === "right" && "justify-end",
          active && "text-foreground",
        )}
      >
        {align === "right" && (
          <Icon className={cn("h-3.5 w-3.5", !active && "opacity-40")} aria-hidden="true" />
        )}
        <span>{children}</span>
        {align !== "right" && (
          <Icon className={cn("h-3.5 w-3.5", !active && "opacity-40")} aria-hidden="true" />
        )}
      </button>
    </TableHead>
  );
}
