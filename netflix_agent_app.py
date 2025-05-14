import streamlit as st
import openai
import json
from datetime import datetime, timedelta
import pytz
import random

# --- API Key ---
client = openai.OpenAI(api_key=st.secrets["openai_api_key"])

# --- Streamlit UI Setup ---
st.set_page_config(page_title="Movie AI Agent", page_icon="🎬")
st.title("🎬 Movie AI Agent")
st.write("Tell me what you feel like watching and I’ll find something perfect.")

# --- Timezone ---
pacific = pytz.timezone("America/Los_Angeles")
now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
now = now_utc.astimezone(pacific)

# --- Session State Init ---
if "shuffle_seed" not in st.session_state:
    st.session_state.shuffle_seed = random.randint(0, 1000000)
if "user_input" not in st.session_state:
    st.session_state.user_input = ""
if "parsed_filters" not in st.session_state:
    st.session_state.parsed_filters = {}
if "final_movies" not in st.session_state:
    st.session_state.final_movies = []
if "generate_trigger" not in st.session_state:
    st.session_state.generate_trigger = False
if "last_used_seed" not in st.session_state:
    st.session_state.last_used_seed = None

# --- User Input Control ---
user_input = st.text_input("What are you in the mood for?", value=st.session_state.user_input)
if user_input != st.session_state.user_input:
    st.session_state.user_input = user_input

# --- Refresh Flags ---
if st.button("🔍 Search"):
    st.session_state.shuffle_seed = random.randint(0, 1000000)
    st.session_state.generate_trigger = True

if st.button("🔄 Show me different options"):
    st.session_state.shuffle_seed = random.randint(0, 1000000)
    st.session_state.generate_trigger = True

# --- Prompt Template ---
system_prompt = """
You are a helpful movie assistant. Your job is to extract structured filters from natural-language movie prompts.
Return a dictionary with these keys:
- genres: list of genres like "Action", "Comedy", "Family"
- mood: list of mood words like "Fun", "Adventurous", "Romantic", "Intense", "Chill"
- min_age_rating: G, PG, PG-13, R, etc.
- keywords: list of subject-related terms (e.g., dinosaurs, pirates)
"""

# --- Load Movies ---
try:
    with open("movies.json", "r") as f:
        all_movies = json.load(f)
except FileNotFoundError:
    st.error("Could not find movies.json. Make sure it's in the same folder.")
    st.stop()

# --- Filtering/Scoring Utilities ---
def is_rating_appropriate(movie_rating, user_min_rating):
    rating_order = ["G", "PG", "PG-13", "R", "NC-17"]
    try:
        return rating_order.index(movie_rating) <= rating_order.index(user_min_rating)
    except ValueError:
        return False

def is_relaxed_rating_acceptable(movie_rating, user_min_rating):
    rating_order = ["G", "PG", "PG-13", "R", "NC-17"]
    try:
        return rating_order.index(movie_rating) <= rating_order.index("PG-13")
    except ValueError:
        return False

def filter_movies_with_fallback(movies, filters):
    strict, relaxed = [], []
    for m in movies:
        if is_rating_appropriate(m.get("age_rating", ""), filters.get("min_age_rating", "R")):
            strict.append(m)
        elif is_relaxed_rating_acceptable(m.get("age_rating", ""), filters.get("min_age_rating", "R")):
            relaxed.append(m)
    return strict if strict else relaxed

def score_movie(movie, filters):
    score = 0
    genres = [g.lower() for g in filters.get("genres", [])]
    moods = [m.lower() for m in filters.get("mood", [])]
    keywords = [k.lower() for k in filters.get("keywords", [])]
    movie_genres = [g.lower() for g in movie.get("genres", [])]
    movie_tags = [t.lower() for t in movie.get("tags", [])]
    description = movie.get("description", "").lower()

    if "horror" in genres and "horror" not in movie_genres:
        return 0, []
    if "romance" in genres and "romance" not in movie_genres:
        return 0, []
    if "romance" in genres and "comedy" in genres:
        if "romance" in movie_genres and "comedy" in movie_genres:
            score += 3
        elif "romance" in movie_genres or "comedy" in movie_genres:
            score += 1

    for g in genres:
        if g in movie_genres:
            score += 2 if g in ["romance", "horror"] else 1
    for m in moods:
        if m in movie_tags:
            score += 1
    for k in keywords:
        if k in description:
            score += 1
    if filters.get("min_age_rating") and movie.get("age_rating") == filters["min_age_rating"]:
        score += 1
    return score, []

def explain_why(movie, user_input, filters, client, now):
    parsed = json.dumps(filters, indent=2)
    age_warning = ""
    if movie.get("age_rating") == "Not Rated":
        age_warning = "\n\n🚨 *This film is not officially rated. Viewer discretion advised.*"
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
- Critics Quote: "{movie.get('rt_quote', '')}"{age_warning}

Your task:
- Write a short, conversational explanation (~3–5 sentences) of **why this movie fits their request**
- Start with: "We chose this film because you asked for: '..."
- If the match is not perfect, say so honestly
- Emphasize age-appropriateness if it's a good fit
- End with something warm like "We think you'll enjoy it!"
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
        return f"(There was an error generating a response.)\n\n{str(e)}"

# --- Main Logic ---
if (
    st.session_state.generate_trigger
    and st.session_state.user_input
    and st.session_state.shuffle_seed != st.session_state.last_used_seed
):
    st.session_state.final_movies = []  # 💥 Clear old movie list
    st.session_state.generate_trigger = False

    # --- Basic Keyword Parsing Instead of GPT ---
    filters = {
        "genres": [],
        "mood": [],
        "min_age_rating": "R",
        "keywords": []
    }
    text = st.session_state.user_input.lower()

    # Basic genre matching
    genres = ["action", "comedy", "drama", "romance", "horror", "thriller", "sci-fi", "fantasy", "family"]
    filters["genres"] = [g for g in genres if g in text]

    # Basic mood guessing
    if "fun" in text or "light" in text:
        filters["mood"].append("fun")
    if "romantic" in text:
        filters["mood"].append("romantic")
    if "scary" in text or "tense" in text:
        filters["mood"].append("intense")
    if not filters["mood"]:
        filters["mood"] = ["thoughtful"]

    # Keywords
    for word in ["dinosaur", "pirate", "robot", "space", "war"]:
        if word in text:
            filters["keywords"].append(word)

    st.session_state.parsed_filters = filters

    filtered_movies = filter_movies_with_fallback(all_movies, filters)
    scored = [(score_movie(m, filters)[0], m) for m in filtered_movies]
    scored = [pair for pair in scored if pair[0] > 0]
    sorted_scored = sorted(scored, key=lambda x: x[0], reverse=True)

    top_candidates_pool = [m for _, m in sorted_scored[:25]]
    random.Random(st.session_state.shuffle_seed).shuffle(top_candidates_pool)
    st.session_state.final_movies = top_candidates_pool[:4]
    st.session_state.last_used_seed = st.session_state.shuffle_seed

# --- Always Render from final_movies ---
final_movies = st.session_state.get("final_movies", [])
if final_movies:
    st.subheader("Here’s what I found:")
    for movie in final_movies:
        st.markdown(f"### 🎬 {movie['title']}")
        st.markdown(explain_why(movie, st.session_state.user_input, st.session_state.parsed_filters, client, now))

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

            day_of_week = now.strftime('%A')
            day_label = {
                "Friday": "It’s Friday night — perfect for family movie time.",
                "Saturday": "It’s Saturday — time to relax and enjoy something fun.",
                "Sunday": "It’s Sunday — the perfect wind-down before a new week.",
                "Monday": "It’s Monday — how about something uplifting?",
                "Tuesday": "It’s Tuesday — a midweek escape could be just right.",
                "Wednesday": "It’s Wednesday — halfway there, treat yourself.",
                "Thursday": "It’s Thursday — almost the weekend, time for something cozy."
            }.get(day_of_week, f"It’s {day_of_week}.")

            st.markdown(f"🕰 {day_label} You’ll finish by {end_time.strftime('%I:%M %p')} — {label}.")

        st.markdown(f"🎨 **Directed by** {movie['director']}")
        st.markdown(f"⭐ **Starring** {', '.join(movie['stars'])}")
        st.markdown(f"🌟 **{movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins**")
        st.markdown(f"_{movie['description']}_")
        st.markdown("---")
