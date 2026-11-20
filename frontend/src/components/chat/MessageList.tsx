import { useEffect, useRef } from "react";
import MessageBubble, { type ChatMessage } from "./MessageBubble";

interface MessageListProps {
  messages: ChatMessage[];
}

export default function MessageList({ messages }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1 px-4 text-center">
        <p className="text-sm font-medium text-[#F5F5F5]">No messages yet</p>
        <p className="text-sm text-[#A3A3A3]">
          Describe what you want the agent to do. Search prompts only list jobs; apply prompts
          may open and submit applications.
        </p>
      </div>
    );
  }

  return (
    <div
      className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-2"
      role="log"
      aria-live="polite"
      aria-label="Conversation history"
    >
      <ul className="flex flex-col gap-4">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </ul>
      <div ref={endRef} />
    </div>
  );
}
