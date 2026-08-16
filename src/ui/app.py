import streamlit as st

from api.drive_search import answer_drive_question
from api.email_search import answer_email_question
from api.gbrain_think import answer_gbrain_question

st.set_page_config(page_title="Personal Brain", page_icon="🧠")
st.title("Personal Brain")

source = st.radio(
    "Search",
    ("Email", "Google Drive", "Both"),
    horizontal=True,
)

if source == "Email":
    caption = "Ask questions over your locally exported Gmail data."
    placeholder = "Ask about email…"
elif source == "Google Drive":
    caption = "Ask questions over your locally exported Google Drive data."
    placeholder = "Ask about Google Drive…"
else:
    caption = "Ask questions across Gmail and Google Drive."
    placeholder = "Ask your brain…"

st.caption(caption)

if question := st.chat_input(placeholder):
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        if source == "Email":
            response = answer_email_question(question)
        elif source == "Google Drive":
            response = answer_drive_question(question)
        else:
            response = answer_gbrain_question(question)

        st.write(response["answer"])

        if response.get("sources"):
            with st.expander("Sources"):
                for source_item in response["sources"]:
                    if "subject" in source_item:
                        label = (
                            f"{source_item.get('source_type', 'gmail')} — "
                            f"{source_item.get('title', source_item['subject'])}"
                        )
                    elif "name" in source_item:
                        label = (
                            f"{source_item.get('source_type', 'drive')} — "
                            f"{source_item['name']}"
                        )
                    else:
                        source_type = source_item.get(
                            "source_type",
                            source_item.get("source", "source"),
                        )
                        title = source_item.get(
                            "title",
                            source_item.get("name", "Untitled"),
                        )
                        label = f"{source_type} — {title}"

                    link = source_item.get("link", "")

                    if link:
                        st.markdown(f"[{label}]({link})")
                    else:
                        st.write(label)

        if response.get("citations"):
            with st.expander("Citations"):
                for citation in response["citations"]:
                    source_type = citation.get(
                        "source_type",
                        citation.get("source", "source"),
                    )
                    title = citation.get("title", "untitled")

                    st.markdown(
                        f"**{source_type} — {title}**"
                    )

                    if citation.get("quote"):
                        st.write(f"“{citation['quote']}”")