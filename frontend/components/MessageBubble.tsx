'use client'

import { memo } from 'react'
import type { Message, QueryResponse } from '@/types'

interface Props {
  message: Message
  onViewArtifact?: (content: string, title: string) => void
}

function formatValue(value: unknown): string {
  if (typeof value === 'number') {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  }
  return String(value ?? '')
}

function AssistantContent({
  response,
  onViewArtifact,
}: {
  response: QueryResponse
  onViewArtifact?: (content: string, title: string) => void
}) {
  const isMetric = response.output_type === 'metric'
  const hasArtifact = response.render_mode === 'artifact' && response.artifact?.content

  return (
    <div className="flex flex-col gap-3 w-full">
      {/* Main message */}
      <p className={isMetric ? 'font-mono text-accent text-xl font-medium' : 'text-text leading-relaxed'}>
        {response.chat_message}
      </p>

      {/* Execution error */}
      {response.execution_error && (
        <p className="text-xs text-red-400 bg-red-500/10 rounded px-3 py-2">
          ⚠ Code execution error: {response.execution_error}
        </p>
      )}

      {/* View artifact button */}
      {hasArtifact && (
        <button
          onClick={() =>
            onViewArtifact?.(response.artifact!.content, response.chat_message)
          }
          className="self-start flex items-center gap-1.5 text-sm font-medium text-accent
                     hover:text-accent/80 transition-colors"
          aria-label="View artifact visualization"
        >
          <span>→</span>
          <span>View {response.output_type === 'dashboard' ? 'Dashboard' : 'Chart'}</span>
        </button>
      )}

      {/* Insight */}
      {response.insight && (
        <p className="text-sm text-muted italic border-l-2 border-accent/40 pl-3 leading-relaxed">
          {response.insight}
        </p>
      )}
    </div>
  )
}

const MessageBubble = memo(function MessageBubble({ message, onViewArtifact }: Props) {
  const isUser = message.role === 'user'
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  if (isUser) {
    return (
      <div className="flex justify-end animate-fade-in">
        <div className="max-w-[75%] flex flex-col items-end gap-1">
          <div className="bg-accent text-bg rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm font-medium">
            {typeof message.content === 'string' ? message.content : ''}
          </div>
          <span className="text-xs text-muted">{time}</span>
        </div>
      </div>
    )
  }

  // Assistant message
  const response = typeof message.content === 'string' ? null : (message.content as QueryResponse)

  return (
    <div className="flex justify-start animate-fade-in">
      <div className="max-w-[85%] flex flex-col gap-1">
        <div className="card px-4 py-3 rounded-2xl rounded-tl-sm text-sm">
          {response ? (
            <AssistantContent response={response} onViewArtifact={onViewArtifact} />
          ) : (
            <p className="text-text leading-relaxed">{message.content as string}</p>
          )}
        </div>
        <span className="text-xs text-muted ml-1">{time}</span>
      </div>
    </div>
  )
})

export default MessageBubble
