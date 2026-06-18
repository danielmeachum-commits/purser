import type { ReactNode } from "react";
import { Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  title?: string;
  description?: ReactNode;
  icon?: ReactNode;
  className?: string;
}

export default function EmptyState({
  title = "Nothing here yet",
  description,
  icon,
  className,
}: Props) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-12 text-center",
        className,
      )}
    >
      <div className="rounded-full bg-muted p-3 text-muted-foreground">
        {icon ?? <Inbox className="h-5 w-5" />}
      </div>
      <div className="text-sm font-medium">{title}</div>
      {description && (
        <div className="max-w-sm text-xs text-muted-foreground">{description}</div>
      )}
    </div>
  );
}
