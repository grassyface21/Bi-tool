'use client'

import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'
import type { Message } from '@/types'

interface Props {
  messages: Message[]
  sessionId: string | null
  suggestedQuestions: string[]
  isLoading: boolean
  isUploadingFiles: boolean
  uploadedFiles: string[]
  onSendMessage: (query: string) => void
  onFileUpload: (files: File[]) => void
  onViewArtifact?: (content: string, title: string) => void
  emptyStateNode?: React.ReactNode
}

export default function ChatPanel({
  messages,
  sessionId,
  suggestedQuestions,
  isLoading,
  isUploadingFiles,
  uploadedFiles,
  onSendMessage,
  onFileUpload,
  onViewArtifact,
  emptyStateNode
}: Props) {
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault()
    const query = input.trim()
    if (!query || isLoading) return
    onSendMessage(query)
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const isInitialState = messages.length === 0

  return (
    <div className="flex flex-col h-full relative w-full">
      
      {/* Scrollable Message Area - Takes full width so messages align left/right */}
      {!isInitialState && (
        <div className="flex-1 w-full overflow-y-auto px-4 md:px-8 py-6 md:py-8 flex flex-col items-center">
          <div className="w-full max-w-7xl flex flex-col gap-6">
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} onViewArtifact={onViewArtifact} />
            ))}

            {isLoading && (
              <div className="flex justify-start animate-fade-in">
                <div className="card px-5 py-4 rounded-2xl rounded-tl-sm flex items-center gap-2">
                  <span className="w-2 h-2 bg-accent rounded-full animate-pulse" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-accent rounded-full animate-pulse" style={{ animationDelay: '200ms' }} />
                  <span className="w-2 h-2 bg-accent rounded-full animate-pulse" style={{ animationDelay: '400ms' }} />
                </div>
              </div>
            )}
            <div ref={bottomRef} className="h-4" />
          </div>
        </div>
      )}

      {/* Input Area & Empty State - Centered vertically if empty, pinned to bottom if not */}
      <div className={`w-full px-4 flex flex-col items-center transition-all duration-300 ${
        isInitialState 
          ? 'flex-1 justify-center pb-12' 
          : 'shrink-0 pb-6 md:pb-8 bg-gradient-to-t from-bg via-bg to-transparent pt-4'
      }`}>
        <div className="w-full max-w-3xl">
          
          {/* Central Welcome State */}
          {isInitialState && emptyStateNode}

          {/* Suggested Questions */}
          {isInitialState && sessionId && suggestedQuestions.length > 0 && (
            <div className="mb-6 flex flex-wrap gap-2 justify-center animate-fade-in">
              {suggestedQuestions.map((q, i) => (
                <button
                  key={i}
                  onClick={() => { onSendMessage(q) }}
                  disabled={isLoading}
                  className="text-xs px-4 py-2 rounded-full border border-border bg-surface/50
                             text-muted hover:text-text hover:border-accent/40
                             transition-all duration-200 disabled:opacity-50"
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          {/* Master Chat Input Box (Removed focus-within glow) */}
          <form 
            onSubmit={handleSubmit}
            className="relative flex flex-col bg-surface border border-border rounded-2xl p-3 transition-colors duration-200 shadow-lg shadow-black/20"
          >
            {/* Uploaded File Chips */}
            {(uploadedFiles.length > 0 || isUploadingFiles) && (
              <div className="flex flex-wrap gap-2 mb-2 px-1">
                {uploadedFiles.map((file, i) => (
                  <div key={i} className="flex items-center gap-2 bg-bg border border-border rounded-lg px-3 py-1.5 text-xs text-text animate-fade-in">
                    <span className="text-accent">📄</span>
                    <span className="truncate max-w-[150px] font-medium">{file}</span>
                  </div>
                ))}
                {isUploadingFiles && (
                  <div className="flex items-center gap-2 bg-bg border border-border rounded-lg px-3 py-1.5 text-xs text-muted animate-fade-in">
                    <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    <span>Uploading...</span>
                  </div>
                )}
              </div>
            )}

            <div className="flex items-end gap-2">
              {/* Hidden File Input */}
              <input
                type="file"
                ref={fileInputRef}
                hidden
                multiple
                accept=".csv,.xlsx"
                onChange={(e) => {
                  if (e.target.files?.length) {
                    onFileUpload(Array.from(e.target.files))
                    e.target.value = '' 
                  }
                }}
              />
              
              {/* Attachment Button */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading || isUploadingFiles}
                className="h-10 w-10 flex items-center justify-center rounded-xl shrink-0 text-muted hover:text-text hover:bg-bg transition-colors disabled:opacity-50 mb-0.5"
                title="Attach CSV or XLSX"
                aria-label="Attach data file"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                </svg>
              </button>

              {/* Text Area (Added focus:outline-none) */}
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={handleTextareaInput}
                onKeyDown={handleKeyDown}
                placeholder="Ask a question about your data..."
                disabled={isLoading}
                className="flex-1 bg-transparent border-none focus:outline-none focus:ring-0 text-text placeholder:text-muted resize-none overflow-hidden leading-relaxed py-2 pl-2 text-left"
                style={{ minHeight: '40px', maxHeight: '160px' }}
                aria-label="Query input"
              />
              
              <button
                type="submit"
                disabled={isLoading || !input.trim()}
                className={`h-10 w-10 flex items-center justify-center rounded-xl shrink-0 transition-all duration-200 mb-0.5 ${
                  input.trim() 
                    ? 'bg-accent text-bg hover:opacity-90' 
                    : 'bg-transparent text-muted'
                }`}
                aria-label="Send query"
              >
                {isLoading ? (
                  <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                )}
              </button>
            </div>
          </form>
          
          <p className="text-center text-[11px] text-muted mt-2 opacity-70">
            Press Enter to send · Shift+Enter for new line
          </p>
        </div>
      </div>
    </div>
  )
}