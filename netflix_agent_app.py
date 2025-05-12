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

# --- GPT Prompt for Filter Extraction ---
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

# --- Scoring Function (stricter) ---
def score_movie(movie, filters):
    score = 0
    reasons = []

    genres = [g.lower() for g in filters.get("genres", [])]
    moods = [m.lower() for m in filters.get("mood", [])]
    keywords = [k.lower() for k in filters.get("keywords", [])]

    movie_genres = [g.lower() for g in movie.get("genres", [])]
    movie_tags = [t.lower() for t in movie.get("tags", [])]
    description = movie.get("description", "").lower()

    for g in genres:
        if g in movie_genres:
            score += 2 if g == "romance" else 1
            reasons.append(f"matched genre: {g}")

    for m in moods:
        if m in movie_tags:
            score += 1
            reasons.append(f"matched mood/tag: {m}")

    for k in keywords:
        if k in description:
            score += 1
            reasons.append(f"matched keyword: {k}")

    if filters.get("min_age_rating") and movie.get("age_rating") == filters["min_age_rating"]:
        score += 1
        reasons.append(f"matched age rating: {movie.get('age_rating')}")

    return score, reasons

# --- GPT-Powered Why This Movie ---
def explain_why(movie, user_input, filters, client):
    parsed = json.dumps(filters, indent=2)
    prompt = f"""
You are an AI movie assistant. A user asked for a movie recommendation: "{user_input}"

Your system parsed the following filters:
{parsed}

You selected the movie **{movie['title']}**. Here are the movie details:
- Rating: {movie.get('rating')}
- Age Rating: {movie.get('age_rating')}
- Runtime: {movie.get('runtime')} minutes
- Genres: {', '.join(movie.get('genres', []))}
- Tags: {', '.join(movie.get('tags', []))}
- Description: {movie.get('description')}
- Critics Quote: "{movie.get('rt_quote', '')}"

Your task:
- Write a short, conversational explanation (~3–5 sentences) of **why this movie fits their request**
- Start with: "We chose this film because you asked for: '...'"
- If the match is not perfect, **say so honestly**
- If the movie lacks a specific genre/mood the user asked for, gently explain that too
- Emphasize age-appropriateness if it's a good fit
- End with something warm like "We think you’ll enjoy it!"

Avoid pretending it's a perfect fit if it’s not. Be smart, transparent, and helpful.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0.7,
            messages=[
                {"role": "system", "content": "You are a thoughtful, honest movie assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        return f"### 🎯 Why this movie?\n\n{response.choices[0].message.content}"
    except Exception as e:
        return f"### 🎯 Why this movie?\n\n(There was an error generating a response.)\n\n{str(e)}"

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
        score, reasons = score_movie(movie, parsed_filters)
        if score >= 3:
            scored_matches.append((score, movie, reasons))

    seen_titles = set()
    unique_results = []
    for score, movie, reasons in scored_matches:
        if movie["title"] not in seen_titles:
            seen_titles.add(movie["title"])
            unique_results.append((score, movie, reasons))

    results_to_show = [m for _, m, _ in unique_results[:4]]

    if results_to_show:
        st.subheader("Here’s what I found:")
        for score, movie, reasons in unique_results[:4]:
            st.markdown(f"### 🎬 {movie['title']}")
            st.markdown(explain_why(movie, user_input, parsed_filters, client))
            st.markdown(f"🎨 **Directed by** {movie['director']}")
            st.markdown(f"⭐ **Starring** {', '.join(movie['stars'])}")
            st.markdown(f"🌟 **{movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins**")
            st.markdown(f"_{movie['description']}_")
            with st.expander("🛠 Debug: Why this was chosen"):
                st.write(f"Score: {score}")
                st.write(reasons)
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
