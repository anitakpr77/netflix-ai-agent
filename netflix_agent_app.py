import streamlit as st
import openai
import json
from datetime import datetime, timedelta

# --- API Key ---
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Netflix AI Agent", page_icon="🎬")
st.title("🎬 Netflix AI Agent")
st.write("Tell me what you feel like watching and I’ll find something perfect.")

# --- User Input ---
user_input = st.text_input("What are you in the mood for?", "")

# --- System Prompt for GPT ---
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

# --- Load Movies from JSON ---
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
        except Exception as e:
            st.error("GPT request failed or response couldn't be parsed.")
            st.exception(e)
            st.stop()

# --- Display Parsed Filters ---
if parsed_filters:
    with st.expander("🔍 GPT parsed filters:"):
        st.json(parsed_filters)

# --- Session Tracking ---
if "shown_titles" not in st.session_state:
    st.session_state.shown_titles = []

if "last_filters" not in st.session_state or st.session_state.last_filters != parsed_filters:
    st.session_state.shown_titles = []
    st.session_state.last_filters = parsed_filters

# --- Rating Filter Helper ---
def is_rating_appropriate(movie_rating, user_min_rating):
    rating_order = ["G", "PG", "PG-13", "R", "NC-17"]
    try:
        return rating_order.index(movie_rating) <= rating_order.index(user_min_rating)
    except ValueError:
        return False  # Unknown rating format

# --- Scoring Function ---
def score_movie(movie, filters):
    score = 0

    if filters.get("genres"):
        if any(genre.lower() in [g.lower() for g in movie.get("genres", [])] for genre in filters["genres"]):
            score += 1

    if filters.get("mood"):
        mood_matches = sum(1 for mood in filters["mood"] if mood.lower() in [tag.lower() for tag in movie.get("tags", [])])
        score += mood_matches

    if filters.get("keywords"):
        keyword_matches = sum(1 for k in filters["keywords"] if k.lower() in movie.get("description", "").lower() or k.lower() in [tag.lower() for tag in movie.get("tags", [])])
        score += keyword_matches

    if filters.get("min_age_rating"):
        movie_rating = movie.get("age_rating", "")
        if movie_rating == filters["min_age_rating"]:
            score += 1

    return score

# --- Explanation Generator ---
def explain_why(movie, filters):
    parts = []

    # 1. Family-friendly label
    if movie.get("age_rating") in ["G", "PG", "PG-13"]:
        parts.append("This is a family-friendly pick")

    # 2. Themes
    themes = []
    if movie.get("tags") and filters.get("mood"):
        themes += [tag for tag in movie["tags"] if tag.lower() in [m.lower() for m in filters["mood"]]]
    if filters.get("keywords"):
        themes += [k for k in filters["keywords"] if k.lower() in movie.get("description", "").lower()]
    if themes:
        unique_themes = list(set(themes))
        parts.append(f"with themes like {', '.join(unique_themes)}")

    # 3. Rating
    if movie.get("age_rating"):
        parts.append(f"and it’s rated {movie['age_rating']}.")

    # 4. Critics quote
    if movie.get("rt_quote"):
        parts.append(f'Critics say: “{movie["rt_quote"]}”')

    # 5. Day of the week
    today = datetime.now().strftime("%A")
    parts.append(f"It’s also {today}")

    # 6. Runtime with time check
    if movie.get("runtime"):
        minutes = movie["runtime"]
        now = datetime.now()
        end_time = now + timedelta(minutes=minutes)

        hours = minutes // 60
        mins = minutes % 60
        if hours:
            runtime_str = f"{hours} hour{'s' if hours > 1 else ''}"
            if mins:
                runtime_str += f" {mins} mins"
        else:
            runtime_str = f"{mins} mins"

        # Add smart suggestion based on current time
        if end_time.hour < 22 or (end_time.hour == 22 and end_time.minute <= 30):
            parts.append(f"and the runtime is {runtime_str}—you’ll finish by {end_time.strftime('%I:%M %p')}, perfect for tonight.")
        else:
            parts.append(f"and the runtime is {runtime_str}. Heads up—it ends around {end_time.strftime('%I:%M %p')}, so maybe save it for the weekend.")

    return " ".join(parts)

# --- Get Ranked Results ---
if parsed_filters:
    scored_matches = []
    for movie in all_movies:
        if movie["title"] in st.session_state.shown_titles:
            continue

        # Filter out movies above the max acceptable age rating
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
            st.markdown(f"🌟 {movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins")
            st.markdown(f"_{movie['description']}_")
            st.markdown(f"*Why this movie?* {explain_why(movie, parsed_filters)}")
            st.markdown("---")
            st.session_state.shown_titles.append(movie["title"])

        if len(scored_matches) > 4:
            if st.button("🔄 Show me different options"):
                st.rerun()
    elif user_input and parsed_filters:
        st.warning("No perfect matches left — but I can show you some close fits if you're open to it!")
        if st.button("🔄 Show me something similar"):
            st.session_state.shown_titles = []
            st.rerun()


