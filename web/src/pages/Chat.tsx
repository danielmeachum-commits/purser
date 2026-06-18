import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Client } from "@langchain/langgraph-sdk";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import {
  type LangGraphStreamCallback,
  unstable_createLangGraphStream,
  useLangGraphRuntime,
} from "@assistant-ui/react-langgraph";
import { RotateCcw } from "lucide-react";

import PageHeader from "@/components/PageHeader";
import { Thread } from "@/components/assistant-ui/thread";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";

// Vite injects this at build time. Same-origin nginx proxy in production
// (/langgraph -> langgraph:2024). Dev defaults to the direct port.
const LANGGRAPH_BASE =
  (import.meta.env.VITE_LANGGRAPH_BASE as string | undefined) ??
  "http://localhost:2024";

// SDK accepts an apiUrl with or without a trailing slash; it strips one and
// concatenates request paths like /threads/<id>/runs/stream. For "/langgraph"
// we have to prepend the page origin so the SDK builds an absolute URL.
function resolveApiUrl(): string {
  if (LANGGRAPH_BASE.startsWith("http://") || LANGGRAPH_BASE.startsWith("https://")) {
    return LANGGRAPH_BASE;
  }
  if (typeof window === "undefined") return LANGGRAPH_BASE;
  return new URL(LANGGRAPH_BASE, window.location.origin).href;
}

const ASSISTANT_ID = "agent";
const MODEL_STORAGE_KEY = "budget.chat.model";

interface ModelEntry {
  id: string;
  label: string;
  service: string;
}
interface ModelsCatalog {
  default: string;
  models: ModelEntry[];
}

export default function Chat() {
  const modelsQ = useQuery({
    queryKey: ["models"],
    queryFn: () => api<ModelsCatalog>("/models"),
    staleTime: Infinity,
  });

  const [selectedModel, setSelectedModel] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(MODEL_STORAGE_KEY);
  });

  useEffect(() => {
    if (!modelsQ.data) return;
    const known = new Set(modelsQ.data.models.map((m) => m.id));
    if (selectedModel && known.has(selectedModel)) return;
    setSelectedModel(modelsQ.data.default);
  }, [modelsQ.data, selectedModel]);

  const onModelChange = (value: string) => {
    setSelectedModel(value);
    try {
      window.localStorage.setItem(MODEL_STORAGE_KEY, value);
    } catch {
      /* ignore */
    }
  };

  // Force-remount the runtime when we want a fresh thread: keying on this
  // counter throws away the runtime's internal LangGraph thread id and
  // message buffer. (useLangGraphRuntime doesn't expose a "new thread"
  // imperative — calling `create()` again starts a thread but the runtime
  // keeps the old messages.)
  const [threadEpoch, setThreadEpoch] = useState(0);
  const reset = () => setThreadEpoch((n) => n + 1);

  return (
    <div className="space-y-4 max-w-4xl">
      <PageHeader
        title="Chat"
        description="Talk to the budget agent: record transactions, ask for summaries, list categories."
        actions={
          <div className="flex items-center gap-2">
            <Select
              value={selectedModel ?? undefined}
              onValueChange={onModelChange}
              disabled={!modelsQ.data}
            >
              <SelectTrigger className="h-9 w-[220px]">
                <SelectValue
                  placeholder={modelsQ.isLoading ? "Loading models…" : "Select model"}
                />
              </SelectTrigger>
              <SelectContent>
                {(modelsQ.data?.models ?? []).map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={reset}>
              <RotateCcw className="h-4 w-4 mr-2" /> New thread
            </Button>
          </div>
        }
      />
      <Card className="flex flex-col h-[calc(100vh-220px)] min-h-[480px] overflow-hidden">
        <ChatRuntime
          key={threadEpoch}
          selectedModel={selectedModel}
        />
      </Card>
    </div>
  );
}

interface ChatRuntimeProps {
  selectedModel: string | null;
}

function ChatRuntime({ selectedModel }: ChatRuntimeProps) {
  // Keep the latest model in a ref so the stream callback (a closure
  // captured by the runtime on mount) always reads the current value.
  // Without this, switching models mid-thread wouldn't take effect.
  const modelRef = useRef(selectedModel);
  modelRef.current = selectedModel;

  const baseStream = useMemo<LangGraphStreamCallback<any>>(() => {
    const client = new Client({ apiUrl: resolveApiUrl() });
    return unstable_createLangGraphStream({
      client,
      assistantId: ASSISTANT_ID,
      streamMode: ["messages", "updates"],
    });
  }, []);

  // Wrap the SDK stream so we can inject runConfig.configurable.model.
  // useLangGraphRuntime sources runConfig from msg.runConfig on the user
  // message; since our composer doesn't set one, it arrives as undefined.
  const stream = useMemo<LangGraphStreamCallback<any>>(
    () =>
      (messages, config) => {
        const model = modelRef.current;
        const merged = {
          ...config,
          runConfig: model
            ? {
                ...(typeof config.runConfig === "object" && config.runConfig
                  ? (config.runConfig as Record<string, unknown>)
                  : {}),
                configurable: {
                  ...(typeof config.runConfig === "object" &&
                  config.runConfig &&
                  "configurable" in (config.runConfig as Record<string, unknown>) &&
                  typeof (config.runConfig as Record<string, unknown>).configurable === "object"
                    ? ((config.runConfig as Record<string, any>).configurable as Record<
                        string,
                        unknown
                      >)
                    : {}),
                  model,
                },
              }
            : config.runConfig,
        };
        return baseStream(messages, merged);
      },
    [baseStream],
  );

  const runtime = useLangGraphRuntime({
    stream,
    create: async () => {
      const client = new Client({ apiUrl: resolveApiUrl() });
      const thread = await client.threads.create();
      return { externalId: thread.thread_id };
    },
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}
