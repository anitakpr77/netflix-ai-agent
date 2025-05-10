import streamlit as st
import openai
import json
from datetime import datetime, timedelta
import pytz

# --- API Key ---
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Netflix AI Agent", page_icon="🎮")
st.title("🎮 Netflix AI Agent")
st.write("Tell me what you feel like watching and I’ll find something perfect.")

# --- Force timezone to Pacific Time ---
pacific = pytz.timezone("America/Los_Angeles")
now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
now = now_utc.astimezone(pacific)

# --- User Input ---
user_input = st.text_input("What are you in the mood for?", "")

# --- GPT System Prompt ---
system_prompt = """
You are a helpful movie assistant. Your job is to extract structured filters from natural-language movie prompts.

Return a dictionary with these keys:
- genres: list of genres like "Action", "Comedy", "Family"
- mood: list of mood words like "Fun", "Adventurous", "Romantic", "Intense", "Chill"
- min_age_rating: G, PG, PG-13, R, etc.
- keywords: list of subject-related terms (e.g., dinosaurs, pirates)

Important:
- If the user doesn’t explicitly state the mood, infer it based on their phrasing.
- Never return an empty list for mood — always include your best guess.
"""

# --- Load Movies ---
try:
    with open("movies.json", "r") as f:
        all_movies = json.load(f)
except FileNotFoundError:
    st.error("Could not find movies.json. Make sure it's in the same folder.")
    st.stop()

# --- Parse Filters ---
parsed_filters = {}
if user_input:
    with st.spinner("🧐 Thinking..."):
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            )
            raw_output = response.choices[0].message.content
            parsed_filters = json.loads(raw_output)
        except Exception:
            st.error("GPT request failed or response couldn't be parsed.")
            st.stop()

# --- Show Filters ---
if parsed_filters:
    with st.expander("🔍 GPT parsed filters:"):
        st.json(parsed_filters)

# --- Session State Tracking ---
if "shown_titles" not in st.session_state:
    st.session_state.shown_titles = []

if "last_filters" not in st.session_state or st.session_state.last_filters != parsed_filters:
    st.session_state.shown_titles = []
    st.session_state.last_filters = parsed_filters

# --- Age Rating Filter ---
def is_rating_appropriate(movie_rating, user_min_rating):
    rating_order = ["G", "PG", "PG-13", "R", "NC-17"]
    try:
        return rating_order.index(movie_rating) <= rating_order.index(user_min_rating)
    except ValueError:
        return False

# --- Score Function ---
def score_movie(movie, filters):
    score = 0
    if filters.get("genres"):
        if any(g.lower() in [m.lower() for m in movie.get("genres", [])] for g in filters["genres"]):
            score += 1
    if filters.get("mood"):
        score += sum(1 for m in filters["mood"] if m.lower() in [t.lower() for t in movie.get("tags", [])])
    if filters.get("keywords"):
        score += sum(1 for k in filters["keywords"] if k.lower() in movie.get("description", "").lower())
    if filters.get("min_age_rating") and movie.get("age_rating") == filters["min_age_rating"]:
        score += 1
    return score

# --- Explain Why Function ---
def explain_why(movie, filters, now):
    parts = []

    requested_family = any(
        term in filters.get("genres", []) + filters.get("keywords", [])
        for term in ["Family", "Kids", "Children", "Animated"]
    )
    is_suitable_rating = movie.get("age_rating") in ["G", "PG"]

    tag_map = {
        "high-stakes": "high-stakes action",
        "intense": "intense sequences",
        "relentless": "relentless pacing",
        "thrilling": "thrilling moments",
        "suspenseful": "suspenseful storytelling",
        "heroic": "heroic moments",
        "gritty": "gritty realism",
        "classic": "a classic tone",
    }

    selected = [tag_map[tag] for tag in movie.get("tags", []) if tag in tag_map]

    reason_parts = []
    if requested_family and is_suitable_rating:
        reason_parts.append("it’s family-friendly")
    if selected:
        if len(selected) == 1:
            reason_parts.append(f"it has {selected[0]}")
        elif len(selected) == 2:
            reason_parts.append(f"it has {selected[0]} and {selected[1]}")
        else:
            reason_parts.append(f"it has {', '.join(selected[:2])}, and {selected[2]}")

    if reason_parts:
        parts.append("We picked this film for you because " + " and ".join(reason_parts) + ".")
    else:
        parts.append("We picked this film for you based on your preferences.")

    if movie.get("rt_quote"):
        parts.append(f"\n\nCritics say: “{movie['rt_quote']}”")

    # Time of day logic
    hour = now.hour
    date_time_string = f"\n\nIt’s also {now.strftime('%A')}"
    if movie.get("runtime"):
        minutes = movie["runtime"]
        end_time = now + timedelta(minutes=minutes)
        hours = minutes // 60
        mins = minutes % 60
        runtime_str = f"{hours} hour{'s' if hours > 1 else ''} {mins} mins" if hours else f"{mins} mins"

        if 5 <= hour < 12:
            date_time_string += f" and the runtime is {runtime_str} — perfect for a morning watch."
        elif 12 <= hour < 17:
            date_time_string += f" and the runtime is {runtime_str} — a great afternoon pick."
        elif 17 <= hour < 21:
            date_time_string += f" and the runtime is {runtime_str} — ideal for tonight’s unwind."
        elif 21 <= hour < 23:
            date_time_string += f" and the runtime is {runtime_str} — a solid late-night option."
        else:
            date_time_string += f" and the runtime is {runtime_str} — might be a bit late, but worth it."

    parts.append(date_time_string)

    return "Why this movie?\n\n" + "\n\n".join(parts)

# --- Movie Recommendation Display ---
if parsed_filters:
    scored_matches = []
    for movie in all_movies:
        if movie["title"] in st.session_state.shown_titles:
            continue
        if parsed_filters.get("min_age_rating"):
            if not is_rating_appropriate(movie.get("age_rating", ""), parsed_filters["min_age_rating"]):
                continue
        score = score_movie(movie, parsed_filters)
        if score > 0:
            scored_matches.append((score, movie))

    scored_matches.sort(reverse=True, key=lambda x: x[0])
    results_to_show = [m for _, m in scored_matches[:4]]

    if results_to_show:
        st.subheader("Here’s what I found:")
        for movie in results_to_show:
            st.markdown(f"**{movie['title']}**")

            if movie.get("director"):
                st.markdown(f"🎨 Directed by {movie['director']}")

            if movie.get("stars"):
                star_list = ", ".join(movie["stars"][:-1]) + f", and {movie['stars'][-1]}" if len(movie["stars"]) > 1 else movie["stars"][0]
                st.markdown(f"⭐ Starring {star_list}")

            st.markdown(f"🌟 {movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins")
            st.markdown(f"_{movie['description']}_")
            st.markdown(f"*{explain_why(movie, parsed_filters, now)}*")
            st.markdown("---")
            st.session_state.shown_titles.append(movie["title"])

        if len(scored_matches) > 4:
            if st.button("🔄 Show me different options"):
                st.rerun()
    else:
        st.warning("No perfect matches found. Want to try something close?")
        if st.button("🔄 Show me something similar"):
            st.session_state.shown_titles = []
            st.rerun()

