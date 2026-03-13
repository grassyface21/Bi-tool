'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import ArtifactPanel from '@/components/ArtifactPanel'
import ChatPanel from '@/components/ChatPanel'
import { sendQuery, uploadFiles, SessionExpiredError } from '@/lib/api'
import type { ArtifactPanelRef, DataFrameSchema, Message, QueryResponse } from '@/types'

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([])
  const [fileObjects, setFileObjects] = useState<File[]>([])
  const [schema, setSchema] = useState<Record<string, DataFrameSchema> | null>(null)
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [artifactOpen, setArtifactOpen] = useState(false)

  // Resizable split — chat panel width as a percentage (clamped 25 – 75)
  const [chatWidthPct, setChatWidthPct] = useState(50)
  const isDragging = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleDividerMouseDown = useCallback(() => {
    isDragging.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const pct = ((e.clientX - rect.left) / rect.width) * 100
      setChatWidthPct(Math.min(Math.max(pct, 25), 75))
    }
    const onMouseUp = () => {
      if (!isDragging.current) return
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
    return () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
  }, [])

  const artifactPanelRef = useRef<ArtifactPanelRef>(null)

  const doUpload = async (allFiles: File[]) => {
    setIsUploading(true)
    setSessionError(null)
    try {
      const response = await uploadFiles(allFiles)
      setFileObjects(allFiles)
      setSessionId(response.session_id)
      setUploadedFiles(response.files_processed)
      setSchema(response.schema_summary)
      setSuggestedQuestions(response.suggested_questions)
      setMessages([])
    } catch (e: unknown) {
      setSessionError(e instanceof Error ? e.message : 'Upload failed. Please try again.')
    } finally {
      setIsUploading(false)
    }
  }

  const handleFileUpload = async (newFiles: File[]) => {
    // Merge with already-uploaded files (deduplicate by name)
    const existingNames = new Set(fileObjects.map((f) => f.name))
    const merged = [...fileObjects, ...newFiles.filter((f) => !existingNames.has(f.name))]
    await doUpload(merged)
  }

  const handleRemoveFile = async (index: number) => {
    const remaining = fileObjects.filter((_, i) => i !== index)
    if (remaining.length === 0) {
      handleReset()
      return
    }
    await doUpload(remaining)
  }

  const handleSendQuery = async (query: string) => {
    if (isLoading) return

    const userMessage: Message = {
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, userMessage])

    if (!sessionId) {
      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: {
              output_type: 'text',
              render_mode: 'chat',
              sql_query: null,
              chat_message: 'Please attach a data file (CSV or XLSX) using the paperclip icon below before asking a question.',
              artifact: null,
              insight: '',
            },
            timestamp: new Date().toISOString(),
          },
        ])
      }, 500)
      return
    }

    setIsLoading(true)

    try {
      const response: QueryResponse = await sendQuery(sessionId, query)

      const assistantMessage: Message = {
        role: 'assistant',
        content: response,
        timestamp: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMessage])

      if (response.render_mode === 'artifact' && response.artifact?.content) {
        setArtifactOpen(true)
        artifactPanelRef.current?.openArtifact(response.artifact.content, query)
      }
    } catch (e: unknown) {
      if (e instanceof SessionExpiredError) {
        setSessionError('Your session has expired. Please re-attach your files.')
        setSessionId(null)
      } else {
        const errorMessage: Message = {
          role: 'assistant',
          content: {
            output_type: 'text',
            render_mode: 'chat',
            sql_query: null,
            chat_message: e instanceof Error ? e.message : 'Something went wrong. Please try again.',
            artifact: null,
            insight: '',
          },
          timestamp: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, errorMessage])
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleViewArtifact = (content: string, title: string) => {
    setArtifactOpen(true)
    artifactPanelRef.current?.openArtifact(content, title)
  }

  const handleReset = () => {
    setSessionId(null)
    setMessages([])
    setUploadedFiles([])
    setFileObjects([])
    setSchema(null)
    setSuggestedQuestions([])
    setSessionError(null)
    setArtifactOpen(false)
    artifactPanelRef.current?.close()
  }

  // The empty state without fixed top margins, ready to be flex-centered
  const emptyStateNode = (
    <div className="flex flex-col items-center justify-center animate-fade-in mb-8">
      <div className="w-16 h-16 bg-surface border border-border rounded-2xl flex items-center justify-center mb-6 shadow-sm">
         <span className="text-3xl">✨</span>
      </div>
      <h2 className="font-heading text-3xl md:text-4xl text-text mb-4 text-center">What data are we analysing today?</h2>
      <p className="text-muted text-sm md:text-base text-center max-w-md leading-relaxed">
        Attach your CSV or XLSX files using the <strong className="text-text font-medium">paperclip icon</strong> below and start asking questions in plain English.
      </p>
    </div>
  )

  return (
    <div className="flex flex-col h-screen bg-bg">
      <header className="flex items-center justify-between px-6 py-4 border-b border-border shadow-sm bg-surface shrink-0 z-10">
        <div className="flex items-center gap-3">
          <h1 className="font-heading text-2xl text-accent tracking-wider">BI TOOL</h1>
        </div>

        <div className="flex items-center gap-4">
          {sessionId && (
            <button onClick={handleReset} className="btn-ghost text-xs" title="Start new session">
              + New Session
            </button>
          )}
        </div>
      </header>

      {sessionError && (
        <div role="alert" className="flex items-center justify-center gap-2 bg-red-50 border-b border-red-200 px-6 py-3 text-sm text-red-600">
          <span>⚠</span>
          <span>{sessionError}</span>
        </div>
      )}

      <main ref={containerRef} className="flex flex-1 overflow-hidden">
        {/* Chat Side */}
        <div
          className="flex flex-col h-full bg-bg relative overflow-hidden"
          style={{ width: artifactOpen ? `${chatWidthPct}%` : '100%' }}
        >
          {/* Schema Summary Pill */}
          {schema && (
            <div className="px-4 py-2 border-b border-border bg-bg shrink-0 flex justify-center z-10">
              <div className="flex flex-wrap gap-x-4 gap-y-1 justify-center max-w-3xl w-full">
                {Object.entries(schema).map(([key, info]) => (
                  <span key={key} className="text-xs text-muted">
                    <span className="text-accent font-mono">{key}</span>
                    {' · '}<span>{info.rows.toLocaleString()} rows</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <ChatPanel
            messages={messages}
            sessionId={sessionId}
            suggestedQuestions={suggestedQuestions}
            isLoading={isLoading}
            isUploadingFiles={isUploading}
            uploadedFiles={uploadedFiles}
            onSendMessage={handleSendQuery}
            onFileUpload={handleFileUpload}
            onRemoveFile={handleRemoveFile}
            onViewArtifact={handleViewArtifact}
            emptyStateNode={emptyStateNode}
          />
        </div>

        {/* Draggable Divider */}
        {artifactOpen && (
          <div
            onMouseDown={handleDividerMouseDown}
            className="w-[5px] shrink-0 cursor-col-resize bg-border hover:bg-accent/40 active:bg-accent/60 transition-colors duration-150 relative group z-10"
            title="Drag to resize"
            role="separator"
            aria-orientation="vertical"
          >
            {/* Three-dot grip indicator */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col gap-[4px]">
              {[0, 1, 2].map((i) => (
                <div key={i} className="w-[3px] h-[3px] rounded-full bg-muted group-hover:bg-accent transition-colors duration-150" />
              ))}
            </div>
          </div>
        )}

        {/* Artifact Side */}
        {artifactOpen && (
          <div
            className="flex flex-col h-full overflow-hidden"
            style={{ width: `${100 - chatWidthPct}%` }}
          >
            <ArtifactPanel ref={artifactPanelRef} />
          </div>
        )}
      </main>
    </div>
  )
}