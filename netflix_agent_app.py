import streamlit as st
import openai
import json
from datetime import datetime, timedelta
import pytz
import random

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
    moods = [m.lower() for m in filters.get("mood", [])]
    keywords = [k.lower() for k in filters.get("keywords", [])]

    movie_genres = [g.lower() for g in movie.get("genres", [])]
    movie_tags = [t.lower() for t in movie.get("tags", [])]
    description = movie.get("description", "").lower()

    for g in genres:
        if g in movie_genres:
            score += 2 if g == "romance" else 1

    for m in moods:
        if m in movie_tags:
            score += 1

    for k in keywords:
        if k in description:
            score += 1

    if filters.get("min_age_rating") and movie.get("age_rating") == filters["min_age_rating"]:
        score += 1

    return score

# --- Updated Why This Movie Function ---
def explain_why(movie, filters, now, user_input):
    title = movie.get("title", "This movie")
    age_rating = movie.get("age_rating", "N/A")
    genres = movie.get("genres", [])
    tags = movie.get("tags", [])
    description = movie.get("description", "")

    explanation = f'We chose this film because you asked for: **"{user_input}"**.\n\n'

    if age_rating:
        explanation += f'{title} is rated **{age_rating}**, which makes it suitable for many 13-year-old viewers.\n'

    matched_genres = [genre for genre in genres if genre.lower() in user_input.lower()]
    matched_tags = [tag for tag in tags if tag.lower() in user_input.lower()]

    if matched_genres or matched_tags:
        explanation += f"\nIt features elements of **{', '.join(matched_genres + matched_tags)}**, which match the kind of movie you're in the mood for.\n"
    else:
        explanation += "\nWhile it might not check every box, it shares a similar vibe with themes like "
        explanation += f"**{', '.join(genres[:2] + tags[:2])}**.\n"

    if movie.get("rt_quote"):
        explanation += f'\n\nCritics say: “{movie["rt_quote"]}”'

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

        explanation += f"\n\nIt’s {now.strftime('%A')} and the runtime is {minutes // 60} hours {minutes % 60} mins — you’ll finish by {end_time.strftime('%I:%M %p')} — {label}."

    return f"### 🎯 Why this movie?\n\n{explanation}"

# --- Movie Recommendation Display ---
if parsed_filters:
    random.shuffle(all_movies)
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
            st.markdown(explain_why(movie, parsed_filters, now, user_input))  # UPDATED
            st.markdown(f"🎨 **Directed by** {movie['director']}")
            st.markdown(f"⭐ **Starring** {', '.join(movie['stars'])}")
            st.markdown(f"🌟 **{movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins**")
            st.markdown(f"_{movie['description']}_")
            st.markdown("---")
            st.session_state.shown_titles.append(movie["title"])

        if len(scored_matches) > len(results_to_show):
            if st.button("🔄 Show me different options"):
                st.session_state.shown_titles = []
                st.rerun()
    else:
        st.warning("No perfect matches found. Want to try something close?")
        if st.button("🔄 Show me something similar"):
            st.session_state.shown_titles = []
            st.rerun()

