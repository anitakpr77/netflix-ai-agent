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

# --- Session State Init ---
if "shown_titles" not in st.session_state:
    st.session_state.shown_titles = []
if "shuffle_seed" not in st.session_state:
    st.session_state.shuffle_seed = random.randint(0, 10000)
if "refresh_trigger" not in st.session_state:
    st.session_state.refresh_trigger = False

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
- If the user says "romantic comedy" or "romcom", set genres to ["Romance", "Comedy"].
- If the user doesn’t explicitly state the mood, infer it based on their phrasing.
- Never return an empty list for mood — always include your best guess.
- If the user mentions a specific age:
    - under 10 → set min_age_rating: "G"
    - age 10–12 → "PG"
    - age 13–17 → "PG-13"
    - adults → "R"
"""

# --- Load Movies ---
try:
    with open("movies.json", "r") as f:
        all_movies = json.load(f)
except FileNotFoundError:
    st.error("Could not find movies.json. Make sure it's in the same folder.")
    st.stop()

# --- Age Rating Filter ---
def is_rating_appropriate(movie_rating, user_min_rating):
    rating_order = ["G", "PG", "PG-13", "R", "NC-17"]
    try:
        return rating_order.index(movie_rating) <= rating_order.index(user_min_rating)
    except ValueError:
        return False

# --- Relaxed Age Rating Check ---
def is_relaxed_rating_acceptable(movie_rating, user_min_rating):
    rating_order = ["G", "PG", "PG-13", "R", "NC-17"]
    try:
        return rating_order.index(movie_rating) <= rating_order.index("PG-13")
    except ValueError:
        return False

# --- Fallback Filtering ---
def filter_movies_with_fallback(movies, filters):
    strict_matches = []
    relaxed_matches = []
    for m in movies:
        if is_rating_appropriate(m.get("age_rating", ""), filters.get("min_age_rating", "R")):
            strict_matches.append(m)
        elif is_relaxed_rating_acceptable(m.get("age_rating", ""), filters.get("min_age_rating", "R")):
            relaxed_matches.append(m)
    return strict_matches if strict_matches else relaxed_matches

# --- Scoring Function ---
def score_movie(movie, filters):
    score = 0
    reasons = []

    genres = [g.lower() for g in filters.get("genres", [])]
    moods = [m.lower() for m in filters.get("mood", [])]
    keywords = [k.lower() for k in filters.get("keywords", [])]

    movie_genres = [g.lower() for g in movie.get("genres", [])]
    movie_tags = [t.lower() for t in movie.get("tags", [])]
    description = movie.get("description", "").lower()

    if "horror" in genres and "horror" not in movie_genres:
        return 0, ["rejected: not a horror genre"]

    if "romance" in genres and "romance" not in movie_genres:
        return 0, ["rejected: not a romance genre"]

    if "romance" in genres and "comedy" in genres:
        if "romance" in movie_genres and "comedy" in movie_genres:
            score += 3
            reasons.append("perfect romcom match")
        elif "romance" in movie_genres or "comedy" in movie_genres:
            score += 1
            reasons.append("partial romcom match — allowed")
        else:
            reasons.append("no romcom elements found")

    for g in genres:
        if g in movie_genres:
            score += 2 if g in ["romance", "horror"] else 1
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

# (the rest of the code remains unchanged)

# --- GPT Ranking Function ---
def gpt_rank_movies(user_input, filters, candidate_movies):
    try:
        movie_summaries = "\n".join([
            f"{i+1}. {m['title']} - Genres: {', '.join(m['genres'])}; Tags: {', '.join(m['tags'])}" for i, m in enumerate(candidate_movies)
        ])

gpt_prompt = f"""
A user asked: "{user_input}"

Session context ID: {random.randint(0, 999999)}  # 👈 inject randomness here to avoid same GPT output

Structured filters:
Genres: {filters.get('genres')}
Mood: {filters.get('mood')}
Min Age Rating: {filters.get('min_age_rating')}
...
"""

Structured filters:
Genres: {filters.get('genres')}
Mood: {filters.get('mood')}
Min Age Rating: {filters.get('min_age_rating')}

Candidate movies:
{movie_summaries}

Please select and rank the top 4 movies that best match the user's request. Return only a list of movie titles in order of best fit.
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {"role": "user", "content": gpt_prompt}
            ]
        )

        titles = response.choices[0].message.content.split("\n")
        titles = [t.strip("0123456789. ") for t in titles if t.strip()]
        return titles[:4]

    except Exception:
        return []

# --- Explain Why Function ---
def explain_why(movie, user_input, filters, client, now):
    parsed = json.dumps(filters, indent=2)
    age_warning = ""
    if movie.get("age_rating") == "Not Rated":
        age_warning = "\n\n⚠️ *This film is not officially rated. Viewer discretion advised.*"

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
{age_warning}

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
        explanation = response.choices[0].message.content
    except Exception as e:
        explanation = f"(There was an error generating a response.)\n\n{str(e)}"

    return f"### 🎯 Why this movie?\n\n{explanation}"

# --- Main Logic ---
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

    shown_titles = st.session_state.get("shown_titles", [])
    filtered_movies = filter_movies_with_fallback(
        [m for m in all_movies if m["title"] not in shown_titles],
        parsed_filters
    )

    scored = [(score_movie(m, parsed_filters)[0], m) for m in filtered_movies]
    scored = [pair for pair in scored if pair[0] > 0]
    sorted_scored = sorted(scored, key=lambda x: x[0], reverse=True)

    # Shuffle after scoring to ensure fresh candidate pool
    top_candidates_pool = [m for _, m in sorted_scored[:25]]  # Take top 25 high scorers
    random.Random(st.session_state.shuffle_seed).shuffle(top_candidates_pool)
    top_candidates = top_candidates_pool[:12]  # Randomized top 12 sent to GPT

    if top_candidates:
            final_movies = top_candidates[:4]

        st.subheader("Here’s what I found:")
        for movie in final_movies:
            st.markdown(f"### 🎬 {movie['title']}")
            st.markdown(explain_why(movie, user_input, parsed_filters, client, now))

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
            shown_titles.append(movie["title"])

        st.session_state["shown_titles"] = shown_titles

        if len(filtered_movies) > len(final_movies):
            if st.button("🔄 Show me different options", key="refresh_button"):
                st.session_state.shown_titles = []
                st.session_state.shuffle_seed = random.randint(0, 1000000)
    else:
        st.warning("No strong matches found. Try a different request!")
