import { useState, useEffect, useCallback, useRef } from 'react'

const API = ''

export function useChat() {
  const [chats, setChats] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState({})
  const [loading, setLoading] = useState(false)
  const initialized = useRef(false)

  useEffect(() => {
    if (!initialized.current) {
      initialized.current = true
      loadChats()
    }
  }, [])

  const loadChats = async () => {
    try {
      const res = await fetch(`${API}/chats`)
      const data = await res.json()
      if (data.length === 0) {
        // No chats exist — create a default one
        const createRes = await fetch(`${API}/chats`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: 'New Chat' })
        })
        const newChat = await createRes.json()
        setChats([newChat])
        setActiveId(newChat.id)
        setMessages({ [newChat.id]: [] })
      } else {
        setChats(data)
        const first = data[0]
        setActiveId(first.id)
        const histRes = await fetch(`${API}/chats/${first.id}/history`)
        const histData = await histRes.json()
        setMessages({ [first.id]: histData })
      }
    } catch (e) {
      console.error('Failed to load chats', e)
    }
  }

  const createChat = useCallback(async () => {
    try {
      const res = await fetch(`${API}/chats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'New Chat' })
      })
      const data = await res.json()
      // Set empty messages FIRST before switching activeId
      setMessages(prev => ({ ...prev, [data.id]: [] }))
      setChats(prev => [data, ...prev])
      setActiveId(data.id)
      return data.id
    } catch (e) {
      console.error('Failed to create chat', e)
    }
  }, [])

  const renameChat = useCallback(async (id, name) => {
    try {
      await fetch(`${API}/chats/${id}/rename`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      })
      setChats(prev => prev.map(c => c.id === id ? { ...c, name } : c))
    } catch (e) {
      console.error('Failed to rename', e)
    }
  }, [])

  const deleteChat = useCallback(async (id) => {
    try {
      await fetch(`${API}/chats/${id}`, { method: 'DELETE' })
      setChats(prev => {
        const remaining = prev.filter(c => c.id !== id)
        if (activeId === id) {
          const next = remaining[0] || null
          setActiveId(next?.id || null)
          if (next) {
            fetch(`${API}/chats/${next.id}/history`)
              .then(r => r.json())
              .then(data => setMessages(prev2 => ({ ...prev2, [next.id]: data })))
              .catch(() => {})
          }
        }
        return remaining
      })
      setMessages(prev => {
        const n = { ...prev }
        delete n[id]
        return n
      })
    } catch (e) {
      console.error('Failed to delete', e)
    }
  }, [activeId])

  const switchChat = useCallback(async (id) => {
    if (id === activeId) return
    setActiveId(id)
    // Always fetch fresh from server — never trust stale local state
    try {
      const res = await fetch(`${API}/chats/${id}/history`)
      const data = await res.json()
      setMessages(prev => ({ ...prev, [id]: data }))
    } catch (e) {
      setMessages(prev => ({ ...prev, [id]: [] }))
    }
  }, [activeId])

  const sendMessage = useCallback(async (prompt) => {
    if (!activeId || loading) return

    // Capture session ID at call time so async callbacks always write to the right session
    const sessionId = activeId
    const currentMsgs = messages[sessionId] || []

    // Auto-name only if still named "New Chat"
    const currentChat = chats.find(c => c.id === sessionId)
    if (currentMsgs.length === 0 && currentChat?.name === 'New Chat') {
      try {
        const res = await fetch(`${API}/name-chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, session_id: sessionId })
        })
        const data = await res.json()
        const name = data.name || prompt.slice(0, 28)
        setChats(prev => prev.map(c => c.id === sessionId ? { ...c, name } : c))
      } catch (_) {}
    }

    setMessages(prev => ({
      ...prev,
      [sessionId]: [...(prev[sessionId] || []), { role: 'user', content: prompt }]
    }))
    setLoading(true)

    try {
      const res = await fetch(`${API}/agent/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, session_id: sessionId })
      })
      const data = await res.json()
      setMessages(prev => ({
        ...prev,
        [sessionId]: [...(prev[sessionId] || []), { role: 'assistant', content: data.response || 'Something went wrong.' }]
      }))
    } catch (e) {
      setMessages(prev => ({
        ...prev,
        [sessionId]: [...(prev[sessionId] || []), { role: 'assistant', content: 'Could not reach agent. Is the server running?' }]
      }))
    } finally {
      setLoading(false)
    }
  }, [activeId, loading, messages])

  return {
    chats,
    activeId,
    activeChat: chats.find(c => c.id === activeId),
    activeMessages: messages[activeId] || [],
    loading,
    createChat,
    renameChat,
    deleteChat,
    switchChat,
    sendMessage,
    loadChats,
  }
}