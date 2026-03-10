'use client'

import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import type { ArtifactPanelRef } from '@/types'

interface ArtifactState {
  content: string
  title: string
}

const ArtifactPanel = forwardRef<ArtifactPanelRef>(function ArtifactPanel(_, ref) {
  const [artifact, setArtifact] = useState<ArtifactState | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  useImperativeHandle(ref, () => ({
    openArtifact(content: string, title: string) {
      setArtifact({ content, title })
    },
    close() {
      setArtifact(null)
    },
  }))

  const exportHTML = () => {
    if (!artifact) return
    const blob = new Blob([artifact.content], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `artifact-${Date.now()}.html`
    a.click()
    URL.revokeObjectURL(url)
  }

  const toggleFullscreen = () => setIsFullscreen((f) => !f)

  if (!artifact) return null

  return (
    <div
      className={[
        'flex flex-col bg-surface border-l border-border',
        'transition-all duration-300 ease-out',
        isFullscreen ? 'fixed inset-0 z-50' : 'relative h-full',
        isFullscreen ? 'w-full' : 'w-full md:w-1/2',
        'animate-slide-in',
      ].join(' ')}
      role="region"
      aria-label="Artifact panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-accent text-sm">◈</span>
          <h2
            className="text-sm font-medium truncate max-w-xs"
            title={artifact.title}
          >
            {artifact.title}
          </h2>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {/* Export */}
          <button
            onClick={exportHTML}
            className="btn-ghost flex items-center gap-1.5"
            title="Export as HTML"
            aria-label="Export artifact as HTML"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span className="hidden sm:inline">Export</span>
          </button>

          {/* Fullscreen toggle */}
          <button
            onClick={toggleFullscreen}
            className="btn-ghost"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="4 14 10 14 10 20" /><polyline points="20 10 14 10 14 4" />
                <line x1="10" y1="14" x2="3" y2="21" /><line x1="21" y1="3" x2="14" y2="10" />
              </svg>
            ) : (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 3 21 3 21 9" /><polyline points="9 21 3 21 3 15" />
                <line x1="21" y1="3" x2="14" y2="10" /><line x1="3" y1="21" x2="10" y2="14" />
              </svg>
            )}
          </button>

          {/* Close */}
          <button
            onClick={() => setArtifact(null)}
            className="btn-ghost"
            title="Close"
            aria-label="Close artifact panel"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      {/* iframe renderer */}
      <div className="flex-1 relative bg-bg overflow-hidden">
        <iframe
          ref={iframeRef}
          srcDoc={artifact.content}
          sandbox="allow-scripts"
          title="Artifact visualization"
          className="w-full h-full border-0"
          aria-label="Visualization artifact"
        />
      </div>
    </div>
  )
})

export default ArtifactPanel
