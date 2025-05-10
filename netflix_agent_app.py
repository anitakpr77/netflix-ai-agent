import streamlit as st
import openai
import json
from datetime import datetime, timedelta
from streamlit_javascript import st_javascript

# --- API Key ---
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Netflix AI Agent", page_icon="🎬")
st.title("🎬 Netflix AI Agent")
st.write("Tell me what you feel like watching and I’ll find something perfect.")

# --- Get browser local time ---
local_time_str = st_javascript("new Date().toString()")
now = None
if local_time_str and "GMT" in local_time_str:
    try:
        now = datetime.strptime(local_time_str[:24], "%a %b %d %Y %H:%M:%S")
    except Exception:
        st.warning("Could not parse your local time.")
else:
    st.warning("Could not retrieve local time from browser.")

# --- User Input ---
user_input = st.text_input("What are you in the mood for?", "")



