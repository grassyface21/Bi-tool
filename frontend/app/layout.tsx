import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'BI Tool — AI-Powered Data Analysis',
  description: 'Upload your data and query it with natural language',
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>",
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full overflow-hidden">{children}</body>
    </html>
  )
}
