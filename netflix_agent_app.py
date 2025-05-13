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
- If the user says "romantic comedy" or "romcom", set genres to ["Romance", "Comedy"].
- If the user doesn’t explicitly state the mood, infer it based on their phrasing.
- Never return an empty list for mood — always include your best guess.
- If the user mentions a specific age (e.g., "for a 10 year old" or "for teens"), infer and set the appropriate min_age_rating (e.g., PG for under 10, PG-13 for 13–15, R for adults).
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

# --- GPT-Based Ranking Function ---
def gpt_rank_movies(user_input, filters, candidate_movies):
    try:
        movie_summaries = "\n".join([
            f"{i+1}. {m['title']} - Genres: {', '.join(m['genres'])}; Tags: {', '.join(m['tags'])}" for i, m in enumerate(candidate_movies)
        ])

        gpt_prompt = f"""
A user asked: "{user_input}"

Structured filters:
Genres: {filters.get('genres')}
Mood: {filters.get('mood')}
Min Age Rating: {filters.get('min_age_rating')}

Candidate movies:
{movie_summaries}

Please select and rank the top 4 movies that best match the user's request. For each movie, return:
- The title
- A short explanation for why it fits

Format your response as JSON like this:
[
  {{"title": "Movie Title", "reason": "why it fits"}},
  ...
]
"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0.7,
            messages=[
                {"role": "user", "content": gpt_prompt}
            ]
        )

        ranked_output = json.loads(response.choices[0].message.content)
        return ranked_output  # list of dicts with title + reason

    except Exception as e:
        st.warning("GPT ranking failed. Showing highest scored results instead.")
        return []

# --- Matching and Display Logic ---
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

            # --- GPT now handles age rating inference based on prompt --- (manual override removed)
        except Exception:
            st.error("GPT request failed or response couldn't be parsed.")
            st.stop()

    if "shown_titles" not in st.session_state:
        st.session_state.shown_titles = []

    def is_valid(movie):
        if movie["title"] in st.session_state.shown_titles:
            return False
        age = movie.get("age_rating", "")
        user_age = parsed_filters.get("min_age_rating")
        if user_age in ["G", "PG", "PG-13"] and age == "Not Rated":
            return False
        return not user_age or is_rating_appropriate(age, user_age)

    matches = [(score_movie(m, parsed_filters)[0], m) for m in all_movies if is_valid(m)]
    matches = [m for m in matches if m[0] >= 2]
    matches.sort(key=lambda x: x[0], reverse=True)
    candidates = [m[1] for m in matches[:12]]

    ranked_with_reasons = gpt_rank_movies(user_input, parsed_filters, candidates)
    title_to_reason = {entry["title"]: entry["reason"] for entry in ranked_with_reasons}

    final_movies = [m for m in candidates if m["title"] in title_to_reason]

    if final_movies:
        st.markdown(f"🔍 You asked for: *{user_input}*")
st.subheader("Here’s what I found:")
        for idx, movie in enumerate(final_movies, 1):
            title = movie["title"]
            reason = title_to_reason.get(title, "")
            st.markdown(f"### {idx}. 🎬 {title}")
            st.markdown(f"🧠 **Why GPT picked it:** {reason}")
            st.markdown(f"🎨 **Directed by** {movie['director']}")
            st.markdown(f"⭐ **Starring** {', '.join(movie['stars'])}")
            st.markdown(f"🌟 **{movie['rating']} Audience Score | {movie['age_rating']} | {movie['runtime']} mins**")

            # --- Add day/time label ---
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

                st.markdown(f"🕒 {day_label} You’ll finish by {end_time.strftime('%I:%M %p')} — {label}.")
            st.markdown(f"_{movie['description']}_")
            
            st.markdown(explain_why(movie, user_input, parsed_filters, client, now))
            st.markdown("---")
            st.session_state.shown_titles.append(title)
    else:
        st.warning("No matches found that GPT felt confident about. Want to try something else?")
