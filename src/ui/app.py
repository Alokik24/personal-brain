import streamlit as st

from api.drive_search import answer_drive_question
from api.email_search import answer_email_question

st.set_page_config(page_title="Personal Brain", page_icon="🧠")
st.title("Personal Brain")
source = st.radio("Search", ("Email", "Google Drive"), horizontal=True)
st.caption(f"Ask questions over your locally exported {source.lower()} data.")

if question := st.chat_input(f"Ask about {source.lower()}…"):
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        response = answer_email_question(question) if source == "Email" else answer_drive_question(question)
        st.write(response["answer"])
        if response["sources"]:
            with st.expander("Sources"):
                for source in response["sources"]:
                    label = (
                        f"{source['subject']} — {source['from']}"
                        if "subject" in source
                        else f"{source['name']} — {source['owner']}"
                    )
                    if source["link"]:
                        st.markdown(f"[{label}]({source['link']})")
                    else:
                        st.write(label)
