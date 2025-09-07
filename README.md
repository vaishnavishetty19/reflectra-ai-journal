# Reflectra : AI-Powered Wellness Journal 🪞

Reflectra is a **privacy-first journaling app** powered by **local GenAI (Ollama)**.  
It converts daily reflections into **summaries, affirmations, and micro-rituals** — stored safely in SQLite.  

### ✨ Features
- 📝 Write reflections in a simple Streamlit interface  
- 🤖 Local AI (Ollama) → generates summary, affirmation, ritual  
- 📊 Mood & burnout meter (sentiment + habits)  
- ✅ Ritual tracker with streaks & adherence score  
- 📚 History tab with filters + CSV export  
- 🔒 100% offline, no cloud calls  

### 🛠 Tech Stack
- Python, Streamlit  
- Ollama (local LLMs like `phi3:mini`)  
- SQLite  
- vaderSentiment, pandas  

### 🚀 Run locally
```bash
# clone repo
git clone https://github.com/<your-username>/reflectra-ai-journal.git
cd reflectra-ai-journal

# create venv
python -m venv .venv
.\.venv\Scripts\activate


<img width="1689" height="953" alt="image" src="https://github.com/user-attachments/assets/9d100b30-f373-4cbf-a46a-0d20b4ecad93" />


# install deps
pip install -r requirements.txt

# run app
streamlit run app.py
