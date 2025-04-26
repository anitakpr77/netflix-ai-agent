import streamlit as st
import openai
import json

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
    with open("full_movies_dataset.json", "r") as f:
        all_movies = json.load(f)
except FileNotFoundError:
    st.error("Could not find full_movies_dataset.json. Make sure it's in the same folder.")
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
    reasons = []
    for genre in filters.get("genres", []):
        if genre.lower() in [g.lower() for g in movie.get("genres", [])]:
            reasons.append(f"it's a {genre.lower()} movie")
    for mood in filters.get("mood", []):
        if mood.lower() in [t.lower() for t in movie.get("tags", [])]:
            reasons.append(f"it has a {mood.lower()} tone")
    for keyword in filters.get("keywords", []):
        if keyword.lower() in movie.get("description", "").lower() or keyword.lower() in [t.lower() for t in movie.get("tags", [])]:
            reasons.append(f"it features {keyword.lower()}")
    if "min_age_rating" in filters and movie.get("age_rating"):
        if filters["min_age_rating"] == movie["age_rating"]:
            reasons.append(f"it's rated {movie['age_rating']}")

    explanation = "Chosen because " + ", and ".join(reasons) + "."
    if movie.get("rt_quote"):
        explanation += f" Critics said: \u201c{movie['rt_quote']}\u201d"
    return explanation

# --- Get Ranked Results ---
if parsed_filters:
    scored_matches = []
    for movie in all_movies:
        if movie["title"] not in st.session_state.shown_titles:
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
