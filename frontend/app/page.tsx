'use client'

import { useRef, useState } from 'react'
import ArtifactPanel from '@/components/ArtifactPanel'
import ChatPanel from '@/components/ChatPanel'
import { sendQuery, uploadFiles, SessionExpiredError } from '@/lib/api'
import type { ArtifactPanelRef, DataFrameSchema, Message, QueryResponse } from '@/types'

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([])
  const [schema, setSchema] = useState<Record<string, DataFrameSchema> | null>(null)
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [sessionError, setSessionError] = useState<string | null>(null)
  const [artifactOpen, setArtifactOpen] = useState(false)

  const artifactPanelRef = useRef<ArtifactPanelRef>(null)

  const handleFileUpload = async (files: File[]) => {
    setIsUploading(true)
    setSessionError(null)
    try {
      const response = await uploadFiles(files)
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
              aggregation_code: null,
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
            aggregation_code: null,
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
    setSchema(null)
    setSuggestedQuestions([])
    setSessionError(null)
    setArtifactOpen(false)
    artifactPanelRef.current?.close()
  }

  // The empty state without fixed top margins, ready to be flex-centered
  const emptyStateNode = (
    <div className="flex flex-col items-center justify-center animate-fade-in mb-8">
      <div className="w-16 h-16 bg-surface border border-border rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-accent/5">
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
      <header className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
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
        <div role="alert" className="flex items-center justify-center gap-2 bg-red-500/10 border-b border-red-500/20 px-6 py-3 text-sm text-red-400">
          <span>⚠</span>
          <span>{sessionError}</span>
        </div>
      )}

      <main className="flex flex-1 overflow-hidden">
        {/* Chat Side */}
        <div className={[
          'flex flex-col h-full transition-all duration-300 ease-in-out bg-bg relative',
          artifactOpen ? 'w-full md:w-1/2 border-r border-border' : 'w-full',
        ].join(' ')}>
          
          {/* Schema Summary Pill */}
          {schema && (
            <div className="px-4 py-2 border-b border-border bg-surface/30 shrink-0 flex justify-center z-10">
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
            onViewArtifact={handleViewArtifact}
            emptyStateNode={emptyStateNode}
          />
        </div>

        {/* Artifact Side */}
        {artifactOpen && (
          <ArtifactPanel ref={artifactPanelRef} />
        )}
      </main>
    </div>
  )
}