// Renders the record_transaction interrupt as an editable confirm card and
// resumes the LangGraph run with either an edits dict (on confirm) or "no"
// (on cancel). The user can tweak any field — account / category dropdowns,
// amount, description, date, type, is_test — before approving.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useLangGraphInterruptState,
  useLangGraphSendCommand,
} from "@assistant-ui/react-langgraph";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

// Mirror of the payload tools.record_transaction passes to interrupt().
interface InterruptPreview {
  action?: string;
  transaction?: {
    date?: string;
    type?: string;
    amount?: string;
    description?: string;
    category?: string | null;
    account?: string | null;
    is_test?: boolean;
  };
  prompt?: string;
}

type TxType = "income" | "expense" | "transfer";

interface Cat {
  id: number;
  name: string;
  type: string;
}
interface Acct {
  id: number;
  nickname: string;
}

const NONE = "__none__";

export function LangGraphInterruptUI() {
  const interrupt = useLangGraphInterruptState();
  const sendCommand = useLangGraphSendCommand();
  if (!interrupt) return null;
  // Remount fresh per interrupt so the form's useState picks up the proposed
  // values. Without the inner-component split, useState would have been
  // initialized on the first render (when no interrupt was present yet).
  return (
    <InterruptCard
      value={(interrupt.value ?? {}) as InterruptPreview}
      sendCommand={sendCommand}
    />
  );
}

interface InterruptCardProps {
  value: InterruptPreview;
  sendCommand: ReturnType<typeof useLangGraphSendCommand>;
}

function InterruptCard({ value, sendCommand }: InterruptCardProps) {
  const [pending, setPending] = useState<"yes" | "no" | null>(null);
  const [resolved, setResolved] = useState<"yes" | "no" | null>(null);

  const isRecordTx =
    value.action === "record_transaction" && !!value.transaction;
  const proposed = value.transaction ?? {};

  // Local edit state, initialized from the proposed payload.
  const [type, setType] = useState<TxType>(
    (proposed.type as TxType) ?? "expense",
  );
  const [amount, setAmount] = useState<string>(proposed.amount ?? "");
  const [description, setDescription] = useState<string>(
    proposed.description ?? "",
  );
  const [date, setDate] = useState<string>(
    proposed.date ?? new Date().toISOString().slice(0, 10),
  );
  const [category, setCategory] = useState<string>(proposed.category ?? "");
  const [account, setAccount] = useState<string>(proposed.account ?? "");
  const [isTest, setIsTest] = useState<boolean>(!!proposed.is_test);

  const catsQ = useQuery({
    queryKey: ["cats"],
    queryFn: () => api<Cat[]>("/categories"),
    enabled: isRecordTx,
    staleTime: 60_000,
  });
  const acctsQ = useQuery({
    queryKey: ["accts"],
    queryFn: () => api<Acct[]>("/accounts"),
    enabled: isRecordTx,
    staleTime: 60_000,
  });

  const cats = catsQ.data ?? [];
  const accts = acctsQ.data ?? [];

  const filteredCats = useMemo(
    () => cats.filter((c) => c.type === type),
    [cats, type],
  );

  const proposedCatMissing =
    !!proposed.category &&
    cats.length > 0 &&
    !cats.some((c) => c.name === proposed.category && c.type === type);
  const proposedAcctMissing =
    !!proposed.account &&
    accts.length > 0 &&
    !accts.some((a) => a.nickname === proposed.account);

  const respond = async (answer: "yes" | "no") => {
    if (pending || resolved) return;
    setPending(answer);
    try {
      if (answer === "no") {
        await sendCommand({ resume: "no" });
      } else {
        // sendCommand's `resume` is typed as string, but the runtime
        // forwards arbitrary JSON to the LangGraph SDK. Cast through
        // unknown so the tool can receive an edits dict.
        const resume = {
          confirm: true,
          date,
          type,
          amount,
          description,
          category, // empty string => clear
          account, // empty string => clear
          is_test: isTest,
        };
        await sendCommand({
          resume: resume as unknown as string,
        });
      }
      setResolved(answer);
    } catch (e) {
      console.error("interrupt resume failed", e);
    } finally {
      setPending(null);
    }
  };

  if (!isRecordTx) {
    return (
      <div className="mx-auto mt-3 w-full max-w-3xl px-2">
        <Card className="space-y-3 border-primary/40 p-4">
          <div className="text-sm font-medium">Agent paused — needs input</div>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">
            {JSON.stringify(value, null, 2)}
          </pre>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => respond("yes")}
              disabled={!!pending || !!resolved}
            >
              Continue (yes)
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => respond("no")}
              disabled={!!pending || !!resolved}
            >
              Cancel (no)
            </Button>
          </div>
          {resolved && (
            <div
              className={cn(
                "text-xs font-mono",
                resolved === "yes"
                  ? "text-green-600 dark:text-green-400"
                  : "text-muted-foreground",
              )}
            >
              {resolved === "yes" ? "resumed" : "cancelled"}
            </div>
          )}
        </Card>
      </div>
    );
  }

  const disabled = !!pending || !!resolved;

  return (
    <div className="mx-auto mt-3 w-full max-w-3xl px-2">
      <Card className="space-y-4 border-primary/40 p-4">
        <div className="text-sm font-medium">Confirm transaction?</div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="space-y-1.5">
            <Label htmlFor="ix-date">Date</Label>
            <Input
              id="ix-date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Type</Label>
            <Select
              value={type}
              onValueChange={(v) => setType(v as TxType)}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="income">income</SelectItem>
                <SelectItem value="expense">expense</SelectItem>
                <SelectItem value="transfer">transfer</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ix-amount">Amount</Label>
            <Input
              id="ix-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ix-desc">Description</Label>
            <Input
              id="ix-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={disabled}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Category</Label>
            <Select
              value={category || NONE}
              onValueChange={(v) => setCategory(v === NONE ? "" : v)}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue placeholder="(none)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>(none)</SelectItem>
                {filteredCats.map((c) => (
                  <SelectItem key={c.id} value={c.name}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {proposedCatMissing && (
              <div className="text-xs text-muted-foreground">
                category &ldquo;{proposed.category}&rdquo; not found — pick one
              </div>
            )}
          </div>
          <div className="space-y-1.5">
            <Label>Account</Label>
            <Select
              value={account || NONE}
              onValueChange={(v) => setAccount(v === NONE ? "" : v)}
              disabled={disabled}
            >
              <SelectTrigger>
                <SelectValue placeholder="(none)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>(none)</SelectItem>
                {accts.map((a) => (
                  <SelectItem key={a.id} value={a.nickname}>
                    {a.nickname}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {proposedAcctMissing && (
              <div className="text-xs text-muted-foreground">
                account &ldquo;{proposed.account}&rdquo; not found — pick one
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="ix-test"
            checked={isTest}
            onCheckedChange={setIsTest}
            disabled={disabled}
          />
          <Label htmlFor="ix-test" className="cursor-pointer text-sm">
            Mark as test (excluded from summaries by default)
          </Label>
        </div>
        {resolved ? (
          <div
            className={cn(
              "font-mono text-sm",
              resolved === "yes"
                ? "text-green-600 dark:text-green-400"
                : "text-muted-foreground",
            )}
          >
            {resolved === "yes" ? "confirmed" : "cancelled"}
          </div>
        ) : (
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => respond("yes")}
              disabled={!!pending}
            >
              {pending === "yes" ? "Recording…" : "Confirm"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => respond("no")}
              disabled={!!pending}
            >
              {pending === "no" ? "Cancelling…" : "Cancel"}
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
