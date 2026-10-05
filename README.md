# English Study Centre — Telegram Mock Test PDF Bot

Render-ready Telegram bot that converts a TXT question bank into a professional A4 question-paper PDF and stores quiz data in MongoDB.

## Features

- Upload `.txt` questions to Telegram.
- Automatically counts/processes all questions.
- Asks for **Subject**, **Section**, and **Set No.** — all optional.
- Send `/skip` for any field you do not want.
- Default headline: **ENGLISH STUDY CENTRE**.
- Default watermark: **ENGLISH STUDY CENTRE** on every page.
- `/pdf QUIZ_ID` generates the PDF.
- Exactly **50 questions per page**: Q1–Q50, Q51–Q100, etc.
- PDF content area adapts to the header/footer, with smaller typography on unusually dense pages to reduce clipping risk.
- Options are exactly `A)`, `B)`, `C)`, `D)` — no checkbox symbols.
- Bundled Noto Sans Devanagari font + HarfBuzz support for proper Hindi shaping.
- Quiz metadata **and the complete parsed question list are stored in MongoDB**, so Render restarts/redeploys do not remove saved Quiz IDs or questions.
- Render-compatible HTTP health endpoint.

## TXT format

Use one question followed by four options:

```text
1. भारत की राजधानी क्या है?
A) मुंबई
B) नई दिल्ली
C) पटना
D) जयपुर

2. प्रश्न यहाँ...
A) विकल्प 1
B) विकल्प 2
C) विकल्प 3
D) विकल्प 4
```

The parser also accepts `1)`, `1-`, and option forms such as `A.`, `A)`, `A-`, `A:`.

## MongoDB setup

Create a free MongoDB Atlas cluster, create a database user, and allow your Render service to connect. Copy the Atlas connection string into Render as `MONGODB_URI`.

Recommended database name:

```text
english_study_centre
```

The bot automatically creates/uses the `quizzes` collection. No manual collection creation is required.

### Data saved in MongoDB

Each Quiz ID document stores:

- Telegram user ID
- Subject / Section / Set No.
- Headline
- Question count
- Complete parsed questions and options
- Source filename

The PDF itself is generated when `/pdf QUIZ_ID` is requested, so the source TXT file does not need to survive a Render restart.

## Deploy on Render

1. Create a new Render Web Service from this repository.
2. Keep the included Docker configuration.
3. Add these environment variables:

```text
BOT_TOKEN=your Telegram BotFather token
MONGODB_URI=your MongoDB Atlas connection string
MONGODB_DB=english_study_centre
```

`DEFAULT_HEADLINE` and `WATERMARK_TEXT` are optional and default to `ENGLISH STUDY CENTRE`.

`render.yaml` is included for Blueprint-based deployment.

## Commands

- `/start`
- `/help`
- `/cancel`
- `/pdf QUIZ_ID`

## Local run

```bash
pip install -r requirements.txt
export BOT_TOKEN="YOUR_TOKEN"
export MONGODB_URI="YOUR_MONGODB_ATLAS_URI"
export MONGODB_DB="english_study_centre"
python main.py
```

## Important

MongoDB keeps the saved Quiz data persistent. Render's local filesystem is still temporary, but that no longer affects saved Quiz IDs/questions because `/pdf` reads them from MongoDB.
