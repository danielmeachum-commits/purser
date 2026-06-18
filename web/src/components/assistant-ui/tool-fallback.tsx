// Headless collapsible tool-call display. Uses native <details> to avoid
// pulling in @radix-ui/react-collapsible — the existing UI primitives don't
// ship it. record_transaction has its own dedicated UI (interrupt-ui), so
// this catch-all is fine for the other tools (list_*, summarize_*, add_*).
import type { ToolCallMessagePartComponent } from "@assistant-ui/react";
import { memo } from "react";
import { AlertCircleIcon, CheckIcon, ChevronRightIcon, LoaderIcon, XCircleIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const ToolFallbackImpl: ToolCallMessagePartComponent = ({
  toolName,
  argsText,
  result,
  status,
}) => {
  const statusType = status?.type ?? "complete";
  const isCancelled = status?.type === "incomplete" && status.reason === "cancelled";
  const isRunning = statusType === "running";

  const Icon =
    statusType === "running"
      ? LoaderIcon
      : statusType === "complete"
        ? CheckIcon
        : statusType === "requires-action"
          ? AlertCircleIcon
          : XCircleIcon;

  const errorText =
    status?.type === "incomplete" && status.error
      ? typeof status.error === "string"
        ? status.error
        : JSON.stringify(status.error)
      : null;

  return (
    <details
      className={cn(
        "group my-2 w-full rounded-md border bg-card text-card-foreground",
        isCancelled && "border-muted-foreground/30 bg-muted/30",
      )}
    >
      <summary className="flex w-full cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm">
        <Icon
          className={cn(
            "h-4 w-4 shrink-0",
            isCancelled && "text-muted-foreground",
            isRunning && "animate-spin",
          )}
        />
        <span
          className={cn(
            "flex-1 text-left",
            isCancelled && "text-muted-foreground line-through",
          )}
        >
          {isCancelled ? "Cancelled tool" : "Used tool"}: <b>{toolName}</b>
        </span>
        <ChevronRightIcon className="h-4 w-4 transition-transform group-open:rotate-90" />
      </summary>
      <div className="space-y-2 border-t px-3 py-2 text-xs">
        {errorText && (
          <div>
            <p className="font-semibold text-muted-foreground">
              {status?.type === "incomplete" && status.reason === "cancelled" ? "Cancelled:" : "Error:"}
            </p>
            <p className="text-muted-foreground">{errorText}</p>
          </div>
        )}
        {argsText && (
          <div>
            <p className="font-semibold text-muted-foreground">Args</p>
            <pre className="whitespace-pre-wrap font-mono">{argsText}</pre>
          </div>
        )}
        {!isCancelled && result !== undefined && (
          <div>
            <p className="font-semibold text-muted-foreground">Result</p>
            <pre className="whitespace-pre-wrap font-mono">
              {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </details>
  );
};

export const ToolFallback = memo(ToolFallbackImpl);
