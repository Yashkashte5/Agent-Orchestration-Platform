import { useChat } from './hooks/useChat'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import ChatInput from './components/ChatInput'
import styles from './App.module.css'

export default function App() {
  const {
    chats,
    activeId,
    activeChat,
    activeMessages,
    loading,
    createChat,
    renameChat,
    deleteChat,
    switchChat,
    sendMessage,
  } = useChat()

  return (
    <div className={styles.app}>
      <Sidebar
        chats={chats}
        activeId={activeId}
        onNew={createChat}
        onSwitch={switchChat}
        onRename={renameChat}
        onDelete={deleteChat}
      />
      <div className={styles.main}>
        <ChatWindow
          chat={activeChat}
          messages={activeMessages}
          loading={loading}
          onSend={sendMessage}
        />
        <ChatInput
          onSend={sendMessage}
          disabled={loading || !activeId}
        />
      </div>
    </div>
  )
}