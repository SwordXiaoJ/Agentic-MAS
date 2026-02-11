import React, { useState, useCallback, useEffect } from 'react'
import { Upload, Image, Loader2, CheckCircle, AlertCircle, X, ChevronDown } from 'lucide-react'
import axios from 'axios'

interface SuggestedPrompt {
  id: string
  prompt: string
  description: string
  domain: string
}

interface ClassificationResult {
  task_id: string
  status: string
  label?: string
  confidence?: number
  top_k?: Array<{ label: string; confidence: number }>
  agent_name?: string
  error?: string
  latency_ms?: number
  mismatch_warning?: string
  // MCP enhancement fields
  mcp_enhanced?: boolean
  reasoning?: string
}

// Format raw agent ID to readable name
// e.g. "satellite-image-classifier---organization-b" → "Satellite Image Classifier (Organization B)"
function formatAgentName(raw: string): string {
  const parts = raw.split('---')
  const name = parts[0].split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
  const org = parts[1] ? ` (${parts[1].split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')})` : ''
  return name + org
}

// Get confidence color based on value
function getConfidenceColor(confidence: number): { text: string; bar: string } {
  if (confidence >= 0.8) return { text: 'text-green-600', bar: 'bg-green-500' }
  if (confidence >= 0.5) return { text: 'text-yellow-600', bar: 'bg-yellow-500' }
  return { text: 'text-red-600', bar: 'bg-red-500' }
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isPolling, setIsPolling] = useState(false)
  const [result, setResult] = useState<ClassificationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [prompt, setPrompt] = useState<string>('Classify this image and identify what it contains.')
  const [suggestedPrompts, setSuggestedPrompts] = useState<SuggestedPrompt[]>([])
  const [showPromptDropdown, setShowPromptDropdown] = useState(false)

  // Fetch suggested prompts on mount
  useEffect(() => {
    const fetchSuggestedPrompts = async () => {
      try {
        const response = await axios.get('/v1/suggested-prompts')
        setSuggestedPrompts(response.data)
      } catch (err) {
        console.error('Failed to fetch suggested prompts:', err)
      }
    }
    fetchSuggestedPrompts()
  }, [])

  const handleSelectPrompt = useCallback((selectedPrompt: SuggestedPrompt) => {
    setPrompt(selectedPrompt.prompt)
    setShowPromptDropdown(false)
  }, [])

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setResult(null)
      setError(null)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    const file = e.dataTransfer.files?.[0]
    if (file && file.type.startsWith('image/')) {
      setSelectedFile(file)
      setPreviewUrl(URL.createObjectURL(file))
      setResult(null)
      setError(null)
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
  }, [])

  const clearSelection = useCallback(() => {
    setSelectedFile(null)
    setPreviewUrl(null)
    setResult(null)
    setError(null)
  }, [])

  const pollForResult = async (taskId: string) => {
    setIsPolling(true)
    const maxAttempts = 60
    let attempts = 0

    while (attempts < maxAttempts) {
      try {
        const response = await axios.get(`/v1/classify/${taskId}`)
        const data = response.data

        if (data.status === 'COMPLETED' || data.status === 'COMPLETED_WITH_WARNING' || data.status === 'FAILED') {
          // Normalize the result format
          // data.result is planner response, data.result.result is actual classification
          const plannerResult = data.result || {}
          const classificationResult = plannerResult.result || {}

          const normalized: ClassificationResult = {
            task_id: taskId,
            status: data.status === 'FAILED' ? 'failed' : 'completed',
            label: classificationResult.label,
            confidence: classificationResult.confidence,
            top_k: classificationResult.top_k,
            agent_name: classificationResult.agent_id,
            error: data.error || plannerResult.error,
            mismatch_warning: plannerResult.mismatch_warning,
            // MCP enhancement fields
            mcp_enhanced: classificationResult.mcp_enhanced,
            reasoning: classificationResult.reasoning
          }
          setResult(normalized)
          setIsPolling(false)
          return
        }

        await new Promise(resolve => setTimeout(resolve, 1000))
        attempts++
      } catch (err) {
        console.error('Polling error:', err)
        attempts++
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }

    setError('Classification timed out. Please try again.')
    setIsPolling(false)
  }

  const handleSubmit = async () => {
    if (!selectedFile) return

    setIsUploading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('image', selectedFile)
      formData.append('prompt', prompt)

      const response = await axios.post('/v1/classify', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

      const { task_id } = response.data
      setIsUploading(false)

      // Start polling for results
      await pollForResult(task_id)
    } catch (err: any) {
      setIsUploading(false)
      setError(err.response?.data?.detail || err.message || 'Upload failed')
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-gray-800 mb-2">
            AGNTCY Image Classification
          </h1>
          <p className="text-gray-600">
            Upload an image and describe what you want to classify - we'll route to the right agent
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Upload Section */}
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <Upload className="w-5 h-5" />
              Upload Image
            </h2>

            {/* Prompt Input with Suggested Prompts */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-700">
                  Classification Prompt
                </label>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setShowPromptDropdown(!showPromptDropdown)}
                    className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800"
                  >
                    Suggested Prompts
                    <ChevronDown className={`w-4 h-4 transition-transform ${showPromptDropdown ? 'rotate-180' : ''}`} />
                  </button>
                  {showPromptDropdown && (
                    <div className="absolute right-0 top-full mt-1 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-20 max-h-64 overflow-y-auto">
                      {suggestedPrompts.map((sp) => (
                        <button
                          key={sp.id}
                          onClick={() => handleSelectPrompt(sp)}
                          className="w-full text-left px-4 py-3 hover:bg-blue-50 border-b border-gray-100 last:border-b-0"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                              sp.domain === 'medical' ? 'bg-red-100 text-red-700' :
                              sp.domain === 'satellite' ? 'bg-green-100 text-green-700' :
                              'bg-blue-100 text-blue-700'
                            }`}>
                              {sp.domain}
                            </span>
                            <span className="text-sm font-medium text-gray-700">{sp.description}</span>
                          </div>
                          <p className="text-xs text-gray-500 truncate">{sp.prompt}</p>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                placeholder="E.g., 'Analyze this X-ray image' for medical, 'Identify land use in this satellite image' for satellite, or general classification prompts..."
              />
            </div>

            {/* Drop Zone */}
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              className={`relative border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
                previewUrl
                  ? 'border-green-400 bg-green-50'
                  : 'border-gray-300 hover:border-blue-400 hover:bg-blue-50'
              }`}
            >
              {previewUrl ? (
                <div className="relative">
                  <button
                    onClick={clearSelection}
                    className="absolute -top-2 -right-2 p-1 bg-red-500 text-white rounded-full hover:bg-red-600 z-10"
                  >
                    <X className="w-4 h-4" />
                  </button>
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="max-h-48 mx-auto rounded-lg shadow-md"
                  />
                  <p className="mt-3 text-sm text-gray-600">{selectedFile?.name}</p>
                </div>
              ) : (
                <>
                  <Image className="w-12 h-12 mx-auto text-gray-400 mb-4" />
                  <p className="text-gray-600 mb-2">
                    Drag and drop an image here, or click to select
                  </p>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleFileSelect}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                  />
                </>
              )}
            </div>

            {/* Submit Button */}
            <button
              onClick={handleSubmit}
              disabled={!selectedFile || isUploading || isPolling}
              className={`w-full mt-4 py-3 px-4 rounded-xl font-semibold text-white transition-all ${
                !selectedFile || isUploading || isPolling
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 shadow-lg hover:shadow-xl'
              }`}
            >
              {isUploading ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Uploading...
                </span>
              ) : isPolling ? (
                <span className="flex items-center justify-center gap-2">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Classifying...
                </span>
              ) : (
                'Classify Image'
              )}
            </button>
          </div>

          {/* Results Section */}
          <div className="bg-white rounded-2xl shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-800 mb-4 flex items-center gap-2">
              <CheckCircle className="w-5 h-5" />
              Classification Result
            </h2>

            {error && (
              <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium text-red-800">Error</p>
                  <p className="text-red-600 text-sm">{error}</p>
                </div>
              </div>
            )}

            {!result && !error && (
              <div className="text-center py-12 text-gray-400">
                <Image className="w-16 h-16 mx-auto mb-4 opacity-50" />
                <p>Upload an image to see classification results</p>
              </div>
            )}

            {result && (
              <div className="space-y-4">
                {/* Status */}
                <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium ${
                  result.status === 'completed'
                    ? 'bg-green-100 text-green-800'
                    : result.status === 'failed'
                    ? 'bg-red-100 text-red-800'
                    : 'bg-yellow-100 text-yellow-800'
                }`}>
                  {result.status === 'completed' && <CheckCircle className="w-4 h-4" />}
                  {result.status === 'failed' && <AlertCircle className="w-4 h-4" />}
                  {result.status.toUpperCase()}
                </div>

                {/* Mismatch Warning */}
                {result.mismatch_warning && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3">
                    <AlertCircle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium text-amber-800">Image-Prompt Mismatch</p>
                      <p className="text-amber-700 text-sm mt-1">{result.mismatch_warning}</p>
                    </div>
                  </div>
                )}

                {/* MCP Enhancement Badge */}
                {result.mcp_enhanced && (
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm font-medium bg-purple-100 text-purple-800">
                    <span className="w-2 h-2 bg-purple-500 rounded-full animate-pulse"></span>
                    MCP Enhanced
                  </div>
                )}

                {/* Main Result */}
                {result.label && (
                  <div className={`rounded-xl p-6 ${result.mcp_enhanced ? 'bg-gradient-to-r from-purple-50 to-indigo-50' : 'bg-gradient-to-r from-blue-50 to-indigo-50'}`}>
                    <p className="text-sm text-gray-500 mb-1">Predicted Label</p>
                    <p className="text-3xl font-bold text-gray-800 capitalize">{result.label}</p>
                    {result.confidence !== undefined && (
                      <div className="mt-3">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-600">Confidence</span>
                          <span className={`font-semibold ${result.mcp_enhanced ? 'text-purple-600' : 'text-blue-600'}`}>
                            {(result.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full transition-all duration-500 ${result.mcp_enhanced ? 'bg-purple-600' : 'bg-blue-600'}`}
                            style={{ width: `${result.confidence * 100}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* MCP Reasoning */}
                {result.reasoning && (
                  <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
                    <p className="text-sm font-medium text-purple-800 mb-2">📚 Diagnostic Reasoning (MCP)</p>
                    <p className="text-sm text-purple-700">{result.reasoning}</p>
                  </div>
                )}

                {/* Top-K Results */}
                {result.top_k && result.top_k.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-2">Other Predictions</p>
                    <div className="space-y-2">
                      {result.top_k.slice(1).map((item, index) => (
                        <div
                          key={index}
                          className="flex items-center justify-between bg-gray-50 rounded-lg px-4 py-2"
                        >
                          <span className="text-gray-700 capitalize">{item.label}</span>
                          <span className="text-sm font-medium text-gray-500">
                            {(item.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Agent Info */}
                {result.agent_name && (
                  <div className="text-sm text-gray-500 pt-2 border-t">
                    Processed by: <span className="font-medium">{result.agent_name}</span>
                  </div>
                )}

                {/* Task ID */}
                <div className="text-xs text-gray-400">
                  Task ID: {result.task_id}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-gray-500 text-sm">
          Powered by AGNTCY A2A Network
        </div>
      </div>
    </div>
  )
}

export default App
