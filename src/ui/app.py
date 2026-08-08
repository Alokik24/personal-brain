import streamlit as st

from api.email_search import answer_email_question

st.set_page_config(page_title="Personal Brain", page_icon="🧠")
st.title("Personal Brain")
st.caption("Ask questions over your locally ingested Gmail messages.")

if question := st.chat_input("Ask about an email…"):
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        response = answer_email_question(question)
        st.write(response["answer"])
        if response["sources"]:
            with st.expander("Sources"):
                for source in response["sources"]:
                    label = f"{source['subject']} — {source['from']}"
                    if source["link"]:
                        st.markdown(f"[{label}]({source['link']})")
                    else:
                        st.write(label)
