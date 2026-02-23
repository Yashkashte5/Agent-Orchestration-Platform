import { useState } from 'react'
import styles from './Sidebar.module.css'

export default function Sidebar({ chats, activeId, onNew, onSwitch, onRename, onDelete }) {
  const [search, setSearch] = useState('')
  const [renamingId, setRenamingId] = useState(null)
  const [renameVal, setRenameVal] = useState('')

  const filtered = chats.filter(c =>
    !search || c.name.toLowerCase().includes(search.toLowerCase())
  )

  const startRename = (e, chat) => {
    e.stopPropagation()
    setRenamingId(chat.id)
    setRenameVal(chat.name)
  }

  const submitRename = async (id) => {
    if (renameVal.trim()) await onRename(id, renameVal.trim())
    setRenamingId(null)
  }

  const handleDelete = (e, id) => {
    e.stopPropagation()
    onDelete(id)
  }

  return (
    <aside className={styles.sidebar}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.logo}>
          <div>
            <div className={styles.logoName}>Agent Orchestration Platform</div>
          </div>
        </div>
      </div>

      {/* New Chat */}
      <div className={styles.actions}>
        <button className={styles.newBtn} onClick={onNew}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          New chat
        </button>
      </div>

      {/* Search */}
      <div className={styles.searchWrap}>
        <svg className={styles.searchIcon} width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
        </svg>
        <input
          className={styles.search}
          type="text"
          placeholder="Search chats..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* Chat list */}
      <div className={styles.section}>
        <div className={styles.sectionLabel}>Recents</div>
        <div className={styles.list}>
          {filtered.length === 0 && (
            <div className={styles.empty}>No chats yet</div>
          )}
          {filtered.map(chat => (
            <div key={chat.id} className={styles.itemWrap}>
              {renamingId === chat.id ? (
                <div className={styles.renameRow}>
                  <input
                    className={styles.renameInput}
                    value={renameVal}
                    onChange={e => setRenameVal(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') submitRename(chat.id)
                      if (e.key === 'Escape') setRenamingId(null)
                    }}
                    autoFocus
                  />
                  <button className={styles.saveBtn} onClick={() => submitRename(chat.id)}>Save</button>
                  <button className={styles.cancelBtn} onClick={() => setRenamingId(null)}>✕</button>
                </div>
              ) : (
                <div
                  className={`${styles.item} ${chat.id === activeId ? styles.active : ''}`}
                  onClick={() => onSwitch(chat.id)}
                >
                  <span className={styles.itemName}>{chat.name}</span>
                  <div className={styles.itemActions}>
                    <button
                      className={styles.iconBtn}
                      onClick={e => startRename(e, chat)}
                      title="Rename"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                      </svg>
                    </button>
                    <button
                      className={`${styles.iconBtn} ${styles.deleteBtn}`}
                      onClick={e => handleDelete(e, chat.id)}
                      title="Delete"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
                        <path d="M10 11v6"/><path d="M14 11v6"/>
                      </svg>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </aside>
  )
}