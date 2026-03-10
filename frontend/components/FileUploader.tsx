'use client'

import { useCallback, useRef, useState } from 'react'
import { uploadFiles } from '@/lib/api'
import type { UploadResponse } from '@/types'

interface Props {
  onSuccess: (response: UploadResponse) => void
}

const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100MB
const ALLOWED_EXTENSIONS = ['.csv', '.xlsx']

export default function FileUploader({ onSuccess }: Props) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const validateFiles = (files: File[]): string | null => {
    for (const file of files) {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase()
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        return `"${file.name}" is not a valid file type. Only .csv and .xlsx are supported.`
      }
      if (file.size > MAX_FILE_SIZE) {
        const mb = (file.size / (1024 * 1024)).toFixed(1)
        return `"${file.name}" is too large (${mb}MB). Maximum size is 100MB.`
      }
    }
    return null
  }

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return
    const arr = Array.from(files)
    const validationError = validateFiles(arr)
    if (validationError) {
      setError(validationError)
      return
    }
    setError(null)
    setSelectedFiles(arr)
  }, [])

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return
    setIsUploading(true)
    setError(null)
    try {
      const response = await uploadFiles(selectedFiles)
      onSuccess(response)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed. Please try again.')
    } finally {
      setIsUploading(false)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const removeFile = (index: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index))
  }

  return (
    <div className="w-full max-w-xl mx-auto flex flex-col gap-4">
      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload CSV or XLSX files"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={[
          'relative flex flex-col items-center justify-center gap-4',
          'rounded-2xl border-2 border-dashed p-12 cursor-pointer',
          'transition-all duration-200 select-none',
          isDragging
            ? 'border-accent bg-accent/5 scale-[1.01]'
            : 'border-border hover:border-muted hover:bg-surface/50',
        ].join(' ')}
      >
        <div className="text-5xl">📂</div>
        <div className="text-center">
          <p className="font-medium text-text">
            Drop your files here, or{' '}
            <span className="text-accent underline underline-offset-2">browse</span>
          </p>
          <p className="text-muted text-sm mt-1">CSV and XLSX files · Max 100MB each</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".csv,.xlsx"
          className="sr-only"
          onChange={(e) => handleFiles(e.target.files)}
          aria-hidden="true"
        />
      </div>

      {/* Selected files */}
      {selectedFiles.length > 0 && (
        <ul className="card divide-y divide-border overflow-hidden">
          {selectedFiles.map((file, i) => (
            <li key={i} className="flex items-center gap-3 px-4 py-3">
              <span className="text-lg">{file.name.endsWith('.xlsx') ? '📗' : '📄'}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{file.name}</p>
                <p className="text-xs text-muted">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); removeFile(i) }}
                className="text-muted hover:text-text transition-colors p-1 rounded"
                aria-label={`Remove ${file.name}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Error message */}
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400"
        >
          <span className="shrink-0 mt-0.5">⚠</span>
          <span>{error}</span>
        </div>
      )}

      {/* Upload button */}
      {selectedFiles.length > 0 && (
        <button
          onClick={handleUpload}
          disabled={isUploading}
          className="btn-primary w-full py-3 flex items-center justify-center gap-2 text-base font-semibold"
        >
          {isUploading ? (
            <>
              <span className="inline-block w-4 h-4 border-2 border-bg/40 border-t-bg rounded-full animate-spin" />
              Uploading…
            </>
          ) : (
            <>
              Analyse {selectedFiles.length} file{selectedFiles.length !== 1 ? 's' : ''}
            </>
          )}
        </button>
      )}
    </div>
  )
}
