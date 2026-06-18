// Thread shell built on assistant-ui primitives. Tailwind 3 compatible.
// Trimmed down vs. the official starter: no attachments, no edit composer,
// no branch picker, no export-as-markdown. Keeps:
//   - Streaming markdown assistant messages
//   - User bubbles
//   - Send / Cancel composer with autosize, Enter / Shift+Enter
//   - Copy + Reload action bar on assistant messages
//   - Error block on failed runs
//   - Tool fallback collapsible
//   - LangGraphInterruptUI hooked into the viewport so it renders inline.
import {
  ActionBarPrimitive,
  AuiIf,
  ComposerPrimitive,
  ErrorPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  CheckIcon,
  CopyIcon,
  RefreshCwIcon,
  SendIcon,
  SquareIcon,
} from "lucide-react";
import type { FC } from "react";

import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import { LangGraphInterruptUI } from "@/components/assistant-ui/interrupt-ui";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const Thread: FC = () => (
  <ThreadPrimitive.Root className="flex h-full flex-col bg-background">
    <ThreadPrimitive.Viewport className="relative flex flex-1 flex-col overflow-y-auto scroll-smooth px-4 pt-4">
      <AuiIf condition={(s) => s.thread.isEmpty}>
        <ThreadWelcome />
      </AuiIf>
      <ThreadPrimitive.Messages
        components={{ UserMessage, AssistantMessage }}
      />
      <LangGraphInterruptUI />
      <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mx-auto mt-auto flex w-full max-w-3xl flex-col gap-2 bg-background pb-3 pt-2">
        <ThreadScrollToBottom />
        <Composer />
      </ThreadPrimitive.ViewportFooter>
    </ThreadPrimitive.Viewport>
  </ThreadPrimitive.Root>
);

const ThreadScrollToBottom: FC = () => (
  <ThreadPrimitive.ScrollToBottom asChild>
    <Button
      variant="outline"
      size="icon"
      className="absolute -top-12 left-1/2 z-10 h-9 w-9 -translate-x-1/2 rounded-full shadow-sm disabled:invisible"
      aria-label="Scroll to bottom"
    >
      <ArrowDownIcon className="h-4 w-4" />
    </Button>
  </ThreadPrimitive.ScrollToBottom>
);

const ThreadWelcome: FC = () => (
  <div className="mx-auto my-auto flex w-full max-w-3xl grow flex-col items-center justify-center px-4 text-center">
    <h1 className="text-xl font-semibold">Talk to the budget agent</h1>
    <p className="mt-1 text-sm text-muted-foreground">
      Record transactions, ask for summaries, list categories. Try{" "}
      <span className="font-mono">I spent $12.50 on coffee today</span> or{" "}
      <span className="font-mono">summarize expenses last month</span>.
    </p>
  </div>
);

const Composer: FC = () => (
  <ComposerPrimitive.Root className="relative flex w-full flex-col rounded-2xl border border-input bg-background px-1 pt-1 transition-shadow focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20">
    <ComposerPrimitive.Input
      placeholder="Ask the agent something… (Enter to send, Shift+Enter for newline)"
      className="max-h-40 min-h-12 w-full resize-none bg-transparent px-3 pb-2 pt-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-0"
      rows={1}
      autoFocus
      aria-label="Message input"
    />
    <ComposerActions />
  </ComposerPrimitive.Root>
);

const ComposerActions: FC = () => (
  <div className="mx-2 mb-2 flex items-center justify-end">
    <AuiIf condition={(s) => !s.thread.isRunning}>
      <ComposerPrimitive.Send asChild>
        <Button
          type="submit"
          size="icon"
          className="h-8 w-8 rounded-full"
          aria-label="Send message"
        >
          <SendIcon className="h-4 w-4" />
        </Button>
      </ComposerPrimitive.Send>
    </AuiIf>
    <AuiIf condition={(s) => s.thread.isRunning}>
      <ComposerPrimitive.Cancel asChild>
        <Button
          type="button"
          size="icon"
          className="h-8 w-8 rounded-full"
          aria-label="Stop generating"
        >
          <SquareIcon className="h-3 w-3 fill-current" />
        </Button>
      </ComposerPrimitive.Cancel>
    </AuiIf>
  </div>
);

const MessageError: FC = () => (
  <MessagePrimitive.Error>
    <ErrorPrimitive.Root className="mt-2 rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive dark:bg-destructive/5 dark:text-red-200">
      <ErrorPrimitive.Message />
    </ErrorPrimitive.Root>
  </MessagePrimitive.Error>
);

const AssistantMessage: FC = () => (
  <MessagePrimitive.Root
    className="relative mx-auto w-full max-w-3xl py-3"
    data-role="assistant"
  >
    <div className="break-words px-2 leading-relaxed text-foreground">
      <MessagePrimitive.Parts
        components={{
          Text: MarkdownText,
          tools: { Fallback: ToolFallback },
        }}
      />
      <MessageError />
    </div>
    <div className="mt-1 ml-2">
      <AssistantActionBar />
    </div>
  </MessagePrimitive.Root>
);

const AssistantActionBar: FC = () => (
  <ActionBarPrimitive.Root
    hideWhenRunning
    autohide="not-last"
    className="flex gap-1 text-muted-foreground"
  >
    <ActionBarPrimitive.Copy asChild>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Copy message">
        <AuiIf condition={(s) => s.message.isCopied}>
          <CheckIcon className="h-3.5 w-3.5" />
        </AuiIf>
        <AuiIf condition={(s) => !s.message.isCopied}>
          <CopyIcon className="h-3.5 w-3.5" />
        </AuiIf>
      </Button>
    </ActionBarPrimitive.Copy>
    <ActionBarPrimitive.Reload asChild>
      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label="Refresh response">
        <RefreshCwIcon className="h-3.5 w-3.5" />
      </Button>
    </ActionBarPrimitive.Reload>
  </ActionBarPrimitive.Root>
);

const UserMessage: FC = () => (
  <MessagePrimitive.Root
    className={cn(
      "mx-auto grid w-full max-w-3xl auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] content-start gap-y-2 px-2 py-3",
      "[&>*]:col-start-2",
    )}
    data-role="user"
  >
    <div className="relative col-start-2 min-w-0">
      <div className="break-words rounded-2xl bg-muted px-4 py-2.5 text-foreground">
        <MessagePrimitive.Parts />
      </div>
    </div>
  </MessagePrimitive.Root>
);
