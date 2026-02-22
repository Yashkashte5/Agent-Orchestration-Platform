import streamlit as st
import requests
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory import get_chats, create_chat, rename_chat, delete_chat, get_history, init_db

API_URL = "http://localhost:8000/agent/run"

st.set_page_config(
    page_title="Agent",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────
# RULES:
# 1. Never target stAppViewContainer (it wraps sidebar too, paints over it)
# 2. Target stApp, stMain, stMainBlockContainer for main bg separately
# 3. Target section[data-testid="stSidebar"] for sidebar bg
# 4. Buttons are stBaseButton-secondary (confirmed via DevTools)
# 5. No st.columns in sidebar chat list — single button per row only

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Main area background (NOT stAppViewContainer) ── */
.stApp { background-color: #0f1117 !important; }
[data-testid="stMain"] { background-color: #0f1117 !important; }
[data-testid="stMainBlockContainer"] { background-color: #0f1117 !important; }
[data-testid="stAppScrollToBottomContainer"] { background-color: #0f1117 !important; }
[data-testid="stBottomBlockContainer"] { background-color: #0f1117 !important; }
body { background-color: #0f1117 !important; color: #e2e8f0 !important; }

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stAppDeployButton"] { display: none !important; }

/* ── SAFE SIDEBAR STYLE ── */
section[data-testid="stSidebar"] {
    background-color: #161922 !important;
    border-right: 1px solid #2a2f45 !important;
}
            
/* ── Sidebar buttons (confirmed: stBaseButton-secondary) ── */
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
    background-color: transparent !important;
    color: #64748b !important;
    border: none !important;
    border-radius: 6px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 400 !important;
    text-align: left !important;
    justify-content: flex-start !important;
    padding: 0.45rem 0.65rem !important;
    width: 100% !important;
    box-shadow: none !important;
    transition: background-color 0.1s, color 0.1s !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    line-height: 1.5 !important;
    height: auto !important;
    min-height: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
    background-color: #252836 !important;
    color: #cbd5e1 !important;
    border: none !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:focus {
    box-shadow: none !important;
    outline: none !important;
    border: none !important;
}

/* ── Search input ── */
[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] {
    background-color: #252836 !important;
    border: 1px solid #2d3148 !important;
    border-radius: 7px !important;
}
[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] input {
    background-color: transparent !important;
    border: none !important;
    color: #94a3b8 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    box-shadow: none !important;
    padding: 0.4rem 0.6rem !important;
}
[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] input::placeholder {
    color: #3d4466 !important;
}
[data-testid="stSidebar"] [data-testid="stTextInputRootElement"] input:focus {
    box-shadow: none !important;
    outline: none !important;
    color: #cbd5e1 !important;
}
[data-testid="stSidebar"] [data-testid="stTextInputRootElement"]:focus-within {
    border-color: #4f5b8a !important;
    box-shadow: none !important;
}
[data-testid="stWidgetLabel"] { display: none !important; }

/* ── Main block container ── */
.main .block-container {
    max-width: 760px !important;
    padding: 0 2rem 6rem !important;
    margin: 0 auto !important;
}

/* ── Top bar ── */
.top-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem 0 1rem;
    border-bottom: 1px solid #1e2235;
    margin-bottom: 1.75rem;
}
.top-bar-title {
    font-family: 'Inter', sans-serif;
    font-size: 0.875rem;
    font-weight: 500;
    color: #e2e8f0;
}
.top-bar-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: #2d3148;
}

/* ── Messages ── */
.msg-wrap {
    display: flex;
    flex-direction: column;
    margin-bottom: 1.5rem;
}
.msg-label {
    font-family: 'Inter', sans-serif;
    font-size: 0.65rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
    color: #3d4466;
}
.msg-label.you { text-align: right; }
.msg-label.agent { color: #4f6bbd; }

.msg-user {
    font-family: 'Inter', sans-serif;
    font-size: 0.88rem;
    color: #e2e8f0;
    background: #1e2235;
    border: 1px solid #2d3148;
    border-radius: 12px 12px 2px 12px;
    padding: 0.7rem 0.95rem;
    max-width: 70%;
    align-self: flex-end;
    line-height: 1.6;
}
.msg-agent {
    font-family: 'Inter', sans-serif;
    font-size: 0.88rem;
    color: #94a3b8;
    border-left: 2px solid #4f6bbd;
    padding: 0.35rem 0 0.35rem 0.9rem;
    max-width: 100%;
    align-self: flex-start;
    line-height: 1.8;
}

/* ── Thinking ── */
.thinking {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0 0.35rem 0.9rem;
    border-left: 2px solid #2d3148;
    margin-bottom: 1.5rem;
}
.dots { display: flex; gap: 4px; }
.dots span {
    width: 4px; height: 4px;
    border-radius: 50%;
    background: #4f6bbd;
    opacity: 0.2;
    animation: pulse 1.4s ease-in-out infinite;
}
.dots span:nth-child(2) { animation-delay: 0.2s; }
.dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes pulse {
    0%, 100% { opacity: 0.15; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1); }
}
.thinking-text {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    color: #2d3148;
    letter-spacing: 0.1em;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 4rem 2rem 2rem;
}
.empty-icon {
    font-size: 1.8rem;
    margin-bottom: 1.25rem;
    opacity: 0.5;
}
.empty-state h2 {
    font-family: 'Inter', sans-serif;
    font-size: 1.1rem;
    font-weight: 500;
    color: #e2e8f0;
    margin-bottom: 0.4rem;
}
.empty-state p {
    font-family: 'Inter', sans-serif;
    font-size: 0.8rem;
    color: #3d4466;
    margin-bottom: 2rem;
}

/* ── Suggestion chips — in main area only ── */
[data-testid="stMainBlockContainer"] [data-testid="stBaseButton-secondary"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.78rem !important;
    color: #4f5b8a !important;
    background-color: #1a1d27 !important;
    border: 1px solid #2d3148 !important;
    border-radius: 8px !important;
    padding: 0.5rem 0.75rem !important;
    transition: all 0.15s !important;
    justify-content: center !important;
}
[data-testid="stMainBlockContainer"] [data-testid="stBaseButton-secondary"]:hover {
    border-color: #4f6bbd !important;
    color: #818cf8 !important;
    background-color: #1e2235 !important;
}

/* ── Chat input ── */
[data-testid="stChatInputTextArea"] {
    background-color: #1a1d27 !important;
    border: 1px solid #2d3148 !important;
    border-radius: 10px !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.875rem !important;
    caret-color: #818cf8 !important;
    box-shadow: none !important;
}
[data-testid="stChatInputTextArea"]:focus {
    border-color: #4f5b8a !important;
    box-shadow: none !important;
    outline: none !important;
}
[data-testid="stChatInputTextArea"]::placeholder { color: #2d3148 !important; }
[data-testid="stChatInputSubmitButton"] button {
    background-color: #4f6bbd !important;
    border: none !important;
    border-radius: 7px !important;
    color: #fff !important;
}
[data-testid="stChatInputSubmitButton"] button:hover {
    background-color: #6078d4 !important;
}
[data-testid="stBottom"] {
    background-color: #0f1117 !important;
}

:root { --primary-color: #818cf8 !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #2d3148; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #4f5b8a; }
</style>
""", unsafe_allow_html=True)

# ── Init ──────────────────────────────────────────────
init_db()

if "active_session" not in st.session_state:
    st.session_state.active_session = None
if "messages" not in st.session_state:
    st.session_state.messages = {}
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "renaming" not in st.session_state:
    st.session_state.renaming = None

def ensure_default_chat():
    chats = get_chats()
    if not chats:
        sid = str(uuid.uuid4())
        create_chat(sid, "New Chat")
        st.session_state.active_session = sid
        st.session_state.messages[sid] = []
    elif st.session_state.active_session is None:
        st.session_state.active_session = chats[0]["id"]

ensure_default_chat()

# ── Helpers ───────────────────────────────────────────
def new_chat():
    sid = str(uuid.uuid4())
    create_chat(sid, "New Chat")
    st.session_state.active_session = sid
    st.session_state.messages[sid] = []
    st.session_state.renaming = None

def switch_chat(sid):
    st.session_state.active_session = sid
    st.session_state.renaming = None
    if sid not in st.session_state.messages:
        history = get_history(sid, limit=50)
        st.session_state.messages[sid] = [
            {"role": h["role"], "content": h["content"]}
            for h in history if h["role"] in ("user", "assistant")
        ]

def auto_name_chat(session_id, first_message):
    try:
        res = requests.post(
            "http://localhost:8000/name-chat",
            json={"prompt": first_message},
            timeout=10,
        )
        name = res.json().get("name", first_message[:28])
    except Exception:
        name = first_message[:28]
    rename_chat(session_id, name)

def send_message(prompt: str):
    sid = st.session_state.active_session
    msgs = st.session_state.messages.get(sid, [])

    if len(msgs) == 0:
        auto_name_chat(sid, prompt)

    msgs.append({"role": "user", "content": prompt})
    st.session_state.messages[sid] = msgs

    placeholder = st.empty()
    placeholder.markdown("""
    <div class="thinking">
        <div class="dots"><span></span><span></span><span></span></div>
        <div class="thinking-text">thinking</div>
    </div>
    """, unsafe_allow_html=True)

    try:
        res = requests.post(
            API_URL,
            json={"prompt": prompt, "session_id": sid},
            timeout=60,
        )
        reply = res.json().get("response", "Something went wrong.")
    except Exception as e:
        reply = f"⚠️ Could not reach agent. Is the server running?\n`{e}`"

    placeholder.empty()
    msgs.append({"role": "assistant", "content": reply})
    st.session_state.messages[sid] = msgs

# ── Sidebar ───────────────────────────────────────────
with st.sidebar:

    # Header
    st.markdown("""
        <div style="padding:1rem 0.5rem 0.75rem;border-bottom:1px solid #2d3148;margin-bottom:0.6rem;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:0.75rem;font-weight:500;
                        color:#818cf8;letter-spacing:0.12em;text-transform:uppercase;">
                ✦ Agent
            </div>
            <div style="font-family:'Inter',sans-serif;font-size:0.62rem;color:#2d3148;margin-top:0.15rem;">
                productivity assistant
            </div>
        </div>
    """, unsafe_allow_html=True)

    # New Chat button
    if st.button("＋  New chat", key="new_chat_btn", use_container_width=True):
        new_chat()
        st.rerun()

    st.markdown("<div style='height:0.35rem'></div>", unsafe_allow_html=True)

    # Search
    search = st.text_input(
        "search",
        placeholder="Search chats...",
        key="search_input",
        label_visibility="collapsed",
    )

    # Recents label
    st.markdown("""
        <div style="font-family:'Inter',sans-serif;font-size:0.62rem;font-weight:500;
                    letter-spacing:0.1em;text-transform:uppercase;color:#2d3148;
                    padding:0.8rem 0.1rem 0.2rem;">
            Recents
        </div>
    """, unsafe_allow_html=True)

    # Chat list — one button per chat, no columns
    all_chats = get_chats()
    filtered = [c for c in all_chats if not search or search.lower() in c["name"].lower()]

    for chat in filtered:
        is_active = chat["id"] == st.session_state.active_session
        short_id = chat["id"].replace("-", "")[:10]
        prefix = "● " if is_active else "  "
        label = prefix + chat["name"]

        # Inject active color for this specific button via a unique CSS rule
        if is_active:
            st.markdown(f"""
                <style>
                div[data-testid="stButton"] [data-testid="stBaseButton-secondary"][data-active="{short_id}"],
                #active_{short_id} + div [data-testid="stBaseButton-secondary"] {{
                    color: #818cf8 !important;
                    background-color: #1e2235 !important;
                }}
                </style>
                <div id="active_{short_id}" style="display:none"></div>
            """, unsafe_allow_html=True)

        if st.button(label, key=f"chat_{short_id}", use_container_width=True):
            if is_active and st.session_state.renaming != chat["id"]:
                st.session_state.renaming = chat["id"]
            else:
                switch_chat(chat["id"])
                st.session_state.renaming = None
            st.rerun()

        # Inline rename
        if st.session_state.renaming == chat["id"]:
            new_name = st.text_input(
                "Rename",
                value=chat["name"],
                key=f"rename_{short_id}",
                label_visibility="collapsed",
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Save", key=f"save_{short_id}", use_container_width=True):
                    if new_name.strip():
                        rename_chat(chat["id"], new_name.strip())
                    st.session_state.renaming = None
                    st.rerun()
            with c2:
                if st.button("Cancel", key=f"cancel_{short_id}", use_container_width=True):
                    st.session_state.renaming = None
                    st.rerun()

        # Delete button (only show for active chat)
        if is_active:
            if st.button("✕  Delete chat", key=f"del_{short_id}", use_container_width=True):
                delete_chat(chat["id"])
                if chat["id"] in st.session_state.messages:
                    del st.session_state.messages[chat["id"]]
                st.session_state.active_session = None
                st.session_state.renaming = None
                ensure_default_chat()
                st.rerun()

# ── Main ──────────────────────────────────────────────
SUGGESTIONS = [
    "What's on my plate today?",
    "Add a high priority todo",
    "Show my notes",
    "Set a reminder",
]

sid = st.session_state.active_session
all_chats = get_chats()
chat_name = next((c["name"] for c in all_chats if c["id"] == sid), "Chat")

# Top bar
st.markdown(f"""
<div class="top-bar">
    <div class="top-bar-title">{chat_name}</div>
    <div class="top-bar-meta">{sid[:8] if sid else ''}</div>
</div>
""", unsafe_allow_html=True)

msgs = st.session_state.messages.get(sid, [])

if not msgs:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">✦</div>
        <h2>What can I help with?</h2>
        <p>Manage your todos, notes and reminders.</p>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(4)
    for col, s in zip(cols, SUGGESTIONS):
        with col:
            if st.button(s, key=f"chip_{s}"):
                st.session_state.pending_prompt = s
                st.rerun()
else:
    for msg in msgs:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="msg-wrap">
                <div class="msg-label you">You</div>
                <div class="msg-user">{msg['content']}</div>
            </div>
            """, unsafe_allow_html=True)
        elif msg["role"] == "assistant":
            st.markdown(f"""
            <div class="msg-wrap">
                <div class="msg-label agent">Agent</div>
                <div class="msg-agent">{msg['content']}</div>
            </div>
            """, unsafe_allow_html=True)

if st.session_state.pending_prompt:
    prompt = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
    send_message(prompt)
    st.rerun()

if prompt := st.chat_input("Message agent..."):
    send_message(prompt)
    st.rerun()