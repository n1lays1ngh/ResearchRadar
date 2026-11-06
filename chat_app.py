"""Research Radar web app: the newsletter (read, download, subscribe) and chat-with-a-paper.

Run: streamlit run chat_app.py
Links: /newsletter (default), /newsletter?action=unsubscribe, /chat, ?paper=<arxiv id> opens the chat.
"""
import streamlit as st

st.set_page_config(page_title="The Research Radar", page_icon="📡", layout="wide")

# Links in the emails use ?paper=<id>; those should land on the chat page.
open_chat = bool(st.query_params.get("paper"))
pages = [
    st.Page("app_pages/newsletter.py", title="The newsletter", icon="📰", url_path="newsletter",
            default=not open_chat),
    st.Page("app_pages/chat.py", title="Chat with a paper", icon="💬", url_path="chat", default=open_chat),
]
st.navigation(pages).run()
