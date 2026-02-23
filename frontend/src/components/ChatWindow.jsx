import { useEffect, useRef } from 'react'
import styles from './ChatWindow.module.css'

const SUGGESTIONS = [
  "What's on my plate today?",
  "Add a high priority todo",
  "Show my notes",
  "Set a reminder for tomorrow",
]

export default function ChatWindow({ chat, messages, loading, onSend }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  return (
    <div className={styles.window}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.chatName}>{chat?.name || 'Chat'}</div>
          <div className={styles.chatId}>{chat?.id?.slice(0, 8)}</div>
        </div>
      </div>

      {/* Messages */}
      <div className={styles.messages}>
        <div className={styles.messagesInner}>
        {messages.length === 0 && !loading ? (
          <div className={styles.empty}>
            <h2 className={styles.emptyTitle}>What can I help with?</h2>
            <p className={styles.emptySub}>Manage your todos, notes and reminders.</p>
            <div className={styles.chips}>
              {SUGGESTIONS.map(s => (
                <button key={s} className={styles.chip} onClick={() => onSend(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((msg, i) => (
              <div key={i} className={`${styles.msgWrap} ${styles[msg.role]}`}>
                <div className={styles.label}>
                  {msg.role === 'user' ? 'You' : 'Agent'}
                </div>
                <div className={`${styles.bubble} ${styles[`bubble_${msg.role}`]}`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {loading && (
              <div className={`${styles.msgWrap} ${styles.assistant}`}>
                <div className={styles.label}>Agent</div>
                <div className={styles.thinking}>
                  <span /><span /><span />
                </div>
              </div>
            )}
          </>
        )}
        <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}