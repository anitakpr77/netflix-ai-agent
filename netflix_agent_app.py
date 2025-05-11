import streamlit as st
import openai
import json
from datetime import datetime, timedelta
import pytz

# --- API Key ---
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Netflix AI Agent", page_icon="🎬")
st.title("🎬 Netflix AI Agent")
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

# --- Scoring Function ---
def score_movie(movie, filters):
    score = 0
    genres = [g.lower() for g in filters.get("genres", [])]
    movie_genres = [g.lower() for g in movie.get("genres", [])]
    tags = [t.lower() for t in movie.get("tags", [])]
    description = movie.get("description", "").lower()

    # Require genre match if user specified genres
    if genres:
        if not any(g in movie_genres for g in genres):
            return 0  # Reject movie if no matching genre

    for g in genres:
        if g in movie_genres:
            score += 2 if g == "romance" else 1

    if filters.get("mood"):
        score += sum(1 for m in filters["mood"] if m.lower() in tags)

    if filters.get("keywords"):
        score += sum(1 for k in filters["keywords"] if k.lower() in description)

    if filters.get("min_age_rating") and movie.get("age_rating") == filters["min_age_rating"]:
        score += 1

    return score

# --- Why This Movie Function ---
def explain_why(movie, filters, now):
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

    requested_family = any(term in filters.get("genres", []) + filters.get("keywords", []) for term in ["Family", "Kids", "Children", "Animated"])
    is_suitable_rating = movie.get("age_rating") in ["G", "PG"]
    selected = [tag_map[tag] for tag in movie.get("tags", []) if tag in tag_map]

    reason_parts = []
    if requested_family and is_suitable_rating:
        reason_parts.append("it’s family-friendly")
    if selected:
        reason_parts.append("it has " + ", ".join(selected[:3]))

    reason = "We picked this film for you because " + " and ".join(reason_parts) + "." if reason_parts else "We picked this film for you based on your preferences."
    critic_quote = f"\n\nCritics say: “{movie['rt_quote']}”" if movie.get("rt_quote") else ""

    if movie.get("runtime"):
        minutes = movie["runtime"]
        end_time = now + timedelta(minutes=minutes)
        hour = now.hour
        if 5 <= hour < 11:
            label = "perfect for a morning watch"
        elif 11 <= hour < 14:
            label = "a great midday pick"
        elif 14 <= hour < 17:
            label = "a great afternoon pick"
        elif 17 <= hour < 21:
            label = "ideal for tonight’s unwind"
        elif 21 <= hour < 23:
            label = "a solid late-night option"
        else:
            label = "a very late watch — maybe save it for tomorrow"

        finish_info = f"It’s {now.strftime('%A')} and the runtime is {minutes // 60} hours {minutes % 60} mins — you’ll finish by {end_time.strftime('%I:%M %p')} — {label}."
    else:
        finish_info = ""

    return f"### 🎯 Why this movie?\n\n{reason}{critic_quote}\n\n{finish_info}"

# --- Movie Recommendation Display ---
if parsed_filters:
    scored_matches = []
    for movie in all_movies:
        if parsed_filters.get("min_age_rating"):
            if not is_rating_appropriate(movie.get("age_rating", ""), parsed_filters["min_age_rating"]):
                continue
        score = score_movie(movie, parsed_filters)
        if score > 0:
            scored_matches.append((score, movie))

    # Deduplicate titles
    seen_titles = set()
    unique_results = []
    for score, movie in scored_matches:
        if movie["title"] not in seen_titles:
            seen_titles.add(movie["title"])
            unique_results.append((score, movie))

    results_to_show = [m for _, m in unique_results[:4]]

    if results_to_show:
        st.subheader("Here’s what I found:")
        for movie in results_to_show:
            st.markdown(f"### 🎬 {movie['title']}")
            st.markdown(explain_why(movie, parsed_filters, now))
            st.markdown(f"🎨 **Directed by** {movie['director']}")
            st.markdown(f"⭐ **Starring** {', '.join(movie['stars'])}")
            st.markdown(f"🌟 **{movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins**")
            st.markdown(f"_{movie['description']}_")
            st.markdown("---")
            st.session_state.shown_titles.append(movie["title"])

        if len(unique_results) > 4:
            if st.button("🔄 Show me different options"):
                st.session_state.shown_titles = []
                st.rerun()
    else:
        st.warning("No perfect matches found. Want to try something close?")
        if st.button("🔄 Show me something similar"):
            st.session_state.shown_titles = []
            st.rerun()
