import asyncio
import os
import re
import uuid
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from pdfgen.generator import generate_pdf
from pdfgen.omr import generate_omr_pdf
from pdfgen.parser import Question, parse_questions
from pdfgen.paper_generator import generate_paper_pdf

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
GENERATED = DATA / "generated"
UPLOADS.mkdir(parents=True, exist_ok=True)
GENERATED.mkdir(parents=True, exist_ok=True)
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB = os.getenv("MONGODB_DB", "english_study_centre").strip() or "english_study_centre"

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEFAULT_HEADLINE = os.getenv("DEFAULT_HEADLINE", "ENGLISH STUDY CENTRE").strip() or "ENGLISH STUDY CENTRE"
WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "ENGLISH STUDY CENTRE").strip() or "ENGLISH STUDY CENTRE"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")


def get_mongo():
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI environment variable is required")
    client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")
    return client, client[MONGODB_DB]


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() in {"/skip", "skip", "-", "none", "no"}:
        return None
    return value


class Form(StatesGroup):
    subject = State()
    lesson = State()
    section = State()
    class_name = State()
    set_no = State()


bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

HELP = (
    "📚 English Study Centre Mock Test Bot\n\n"
    "1. TXT file upload करें।\n"
    "2. Bot Subject, Lesson, Section, Class और Set No. पूछेगा — सभी optional हैं।\n"
    "3. Quiz ID मिलेगा।\n"
    "4. /pdf QUIZ_ID भेजकर PDF लें।\n\n"
    "Layout चुनने के लिए /toggle 50 या /toggle 100 भेजें।\n"
    "Question Paper: /toggle paper on या /toggle paper off; TXT पर reply करके /paper भेजें।\n"
    "OMR enable/disable: /toggle omr on या /toggle omr off\n"
    "OMR PDF: /omr 1 to 100 (किसी भी question range के लिए)\n"
    "/toggle 50 = 25 questions/page (बड़े और साफ़), /toggle 100 = 50 questions/page।\n"
    "Hindi Unicode और options A) B) C) D) सुरक्षित रहेंगे।\n"
    "किसी optional field को छोड़ने के लिए /skip भेजें।"
)


@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Welcome to English Study Centre!\n\n"
        "अपनी questions वाली .txt file upload करें।\n"
        "मैं questions process करके Quiz ID बनाऊँगा।\n\n" + HELP
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP)


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Current process cancelled. नई TXT file भेज सकते हैं।")


@dp.message(F.document)
async def txt_upload(message: Message, state: FSMContext):
    doc = message.document
    filename = doc.file_name or "questions.txt"
    if not filename.lower().endswith(".txt"):
        await message.answer("❌ केवल .txt file upload करें।")
        return

    # When Question Paper mode is enabled, keep this upload for the /paper reply flow.
    try:
        client, database = get_mongo()
        settings = database.user_settings.find_one({"_id": message.from_user.id}) or {}
        client.close()
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    if settings.get("paper_enabled", False):
        await message.answer(
            "✅ TXT file मिल गई। अब इसी file के reply में /paper भेजें。\n"
            "PDF में TXT का दिया हुआ content ही रखा जाएगा; कोई समय, अंक या खंड अपने आप नहीं जोड़ा जाएगा।"
        )
        return

    await state.clear()
    status = await message.answer("⏳ TXT process कर रहा हूँ...")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    source = UPLOADS / f"{message.from_user.id}_{uuid.uuid4().hex[:8]}_{safe}"
    await bot.download(doc, destination=source)

    try:
        text = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = source.read_text(encoding="cp1252", errors="replace")

    questions = parse_questions(text)
    if not questions:
        await status.edit_text(
            "❌ Questions नहीं मिलीं।\n\n"
            "TXT में numbering और options इस तरह रखें:\n"
            "1. Question text\n"
            "A) Option 1\nB) Option 2\nC) Option 3\nD) Option 4"
        )
        return

    await state.update_data(source_file=str(source), questions=questions, question_count=len(questions), headline=DEFAULT_HEADLINE)
    await state.set_state(Form.subject)
    await status.edit_text(
        f"✅ {len(questions)} questions process हो गए।\n\n"
        "अब details दें। सभी optional हैं।\n\n"
        "Subject: ?\n"
        "(नहीं देना हो तो /skip)"
    )


@dp.message(Form.subject)
async def get_subject(message: Message, state: FSMContext):
    value = clean_optional(message.text)
    await state.update_data(subject=value)
    await state.set_state(Form.lesson)
    await message.answer("Lesson: ?\n(नहीं देना हो तो /skip)")


@dp.message(Form.lesson)
async def get_lesson(message: Message, state: FSMContext):
    value = clean_optional(message.text)
    await state.update_data(lesson=value)
    await state.set_state(Form.section)
    await message.answer("Section: ?\n(नहीं देना हो तो /skip)")


@dp.message(Form.section)
async def get_section(message: Message, state: FSMContext):
    value = clean_optional(message.text)
    await state.update_data(section=value)
    await state.set_state(Form.class_name)
    await message.answer("Class: ?\n(नहीं देना हो तो /skip)")


@dp.message(Form.class_name)
async def get_class_name(message: Message, state: FSMContext):
    value = clean_optional(message.text)
    await state.update_data(class_name=value)
    await state.set_state(Form.set_no)
    await message.answer("Set No: ?\n(नहीं देना हो तो /skip)")


@dp.message(Form.set_no)
async def get_set_no(message: Message, state: FSMContext):
    value = clean_optional(message.text)
    data = await state.get_data()
    await state.clear()

    quiz_id = uuid.uuid4().hex[:8].upper()
    try:
        client, database = get_mongo()
        database.quizzes.insert_one({
            "_id": quiz_id,
            "user_id": message.from_user.id,
            "source_file": data["source_file"],
            "subject": data.get("subject"),
            "lesson": data.get("lesson"),
            "section": data.get("section"),
            "class_name": data.get("class_name"),
            "set_no": value,
            "headline": data.get("headline") or DEFAULT_HEADLINE,
            "question_count": data["question_count"],
            # Convert parser Question dataclass objects to MongoDB-safe documents.
            "questions": [
                {
                    "number": q.number,
                    "text": q.text,
                    "options": q.options,
                }
                if hasattr(q, "number") and hasattr(q, "text") and hasattr(q, "options")
                else q
                for q in data["questions"]
            ],
        })
        client.close()
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB save error: {type(exc).__name__}: {exc}")
        return

    await message.answer(
        f"✅ Quiz ready!\n\n"
        f"Quiz ID: `{quiz_id}`\n"
        f"Questions: {data['question_count']}\n\n"
        f"PDF लेने के लिए भेजें:\n`/pdf {quiz_id}`",
        parse_mode="Markdown",
    )


@dp.message(Command("toggle"))
async def toggle_cmd(message: Message):
    parts = (message.text or "").split()
    if len(parts) == 3 and parts[1].lower() == "paper" and parts[2].lower() in {"on", "off"}:
        enabled = parts[2].lower() == "on"
        try:
            client, database = get_mongo()
            database.user_settings.update_one(
                {"_id": message.from_user.id},
                {"$set": {"paper_enabled": enabled}},
                upsert=True,
            )
            client.close()
        except PyMongoError as exc:
            await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
            return
        await message.answer("✅ Question Paper: " + ("ENABLED" if enabled else "DISABLED ❌❌"))
        return

    if len(parts) != 2 or parts[1].strip() not in {"50", "100"}:
        await message.answer(
            "Usage:\n/toggle 50\n/toggle 100\n/toggle paper on\n/toggle paper off\n\n"
            "50 = 25 questions per page; 100 = 50 questions per page."
        )
        return
    mode = int(parts[1].strip())
    try:
        client, database = get_mongo()
        database.user_settings.update_one(
            {"_id": message.from_user.id},
            {"$set": {"pdf_mode": mode}},
            upsert=True,
        )
        client.close()
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    if mode == 50:
        await message.answer("✅ PDF layout set: 50\n25 questions per page — बड़ा और साफ़ format.")
    else:
        await message.answer("✅ PDF layout set: 100\n50 questions per page — 25 left + 25 right.")


@dp.message(Command("paper"))
async def paper_cmd(message: Message):
    replied = message.reply_to_message
    doc = replied.document if replied else None
    if not doc or not (doc.file_name or "").lower().endswith(".txt"):
        await message.answer("❌ TXT file के message पर Reply करके /paper भेजें।")
        return

    try:
        client, database = get_mongo()
        settings = database.user_settings.find_one({"_id": message.from_user.id}) or {}
        client.close()
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    if not settings.get("paper_enabled", False):
        await message.answer("⛔ Question Paper function disabled है। पहले /toggle paper on करें।")
        return

    safe = re.sub(r"[^A-Za-z0-9._-]", "_", doc.file_name or "paper.txt")
    source = UPLOADS / f"paper_{message.from_user.id}_{uuid.uuid4().hex[:8]}_{safe}"
    output = GENERATED / f"Question_Paper_{message.from_user.id}_{uuid.uuid4().hex[:8]}.pdf"
    status = await message.answer("⏳ TXT से Question Paper PDF बना रहा हूँ...")
    try:
        # Resolve the Telegram file_id to a fresh file_path before downloading.
        # Passing the whole Document object to bot.download() can cause Telegram
        # to receive an invalid file identifier on some aiogram versions.
        telegram_file = await bot.get_file(doc.file_id)
        if not telegram_file.file_path:
            raise RuntimeError("Telegram ने इस TXT file का download path नहीं दिया। कृपया TXT दोबारा upload करें।")
        await bot.download_file(telegram_file.file_path, destination=source)
        try:
            raw_text = source.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raw_text = source.read_text(encoding="utf-8", errors="replace")
        generate_paper_pdf(raw_text, output)
        await message.answer_document(
            FSInputFile(output),
            caption="📄 Question Paper PDF तैयार है।\nTXT में जो content दिया गया था, उसी के आधार पर बनाया गया है।",
        )
        await status.edit_text("✅ Question Paper generated.")
    except Exception as exc:
        await status.edit_text(f"❌ Question Paper error: {type(exc).__name__}: {exc}")


@dp.message(Command("pdf"))
async def pdf_cmd(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: `/pdf QUIZ_ID`", parse_mode="Markdown")
        return
    quiz_id = parts[1].strip().upper()
    try:
        client, database = get_mongo()
        row = database.quizzes.find_one({"_id": quiz_id})
        client.close()
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    if not row:
        await message.answer("❌ Quiz ID नहीं मिला।")
        return
    if row.get("user_id") != message.from_user.id:
        await message.answer("❌ यह Quiz ID आपके account की नहीं है।")
        return

    try:
        client, database = get_mongo()
        settings = database.user_settings.find_one({"_id": message.from_user.id}) or {}
        client.close()
        pdf_mode = int(settings.get("pdf_mode", 100))
        if pdf_mode not in (50, 100):
            pdf_mode = 100
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return

    per_page = 25 if pdf_mode == 50 else 50
    status = await message.answer(f"⏳ PDF बना रहा हूँ... {per_page} questions/page layout तैयार हो रहा है।")
    try:
        # MongoDB returns each saved question as a dict; the PDF generator
        # expects Question dataclass instances. Support both formats so older
        # and newly saved quizzes can generate PDFs.
        questions = [
            q if isinstance(q, Question) else Question(
                number=int(q.get("number", index)),
                text=str(q.get("text", "")),
                options=list(q.get("options") or []),
            )
            for index, q in enumerate(row.get("questions", []), start=1)
        ]
        output = GENERATED / f"English_Study_Centre_{quiz_id}_M{pdf_mode}.pdf"
        generate_pdf(
            questions=questions,
            output_path=output,
            headline=row.get("headline") or DEFAULT_HEADLINE,
            subject=row.get("subject"), lesson=row.get("lesson"),
            section=row.get("section") if row.get("section") is not None else row.get("to" + "pic"), class_name=row.get("class_name"),
            set_no=row.get("set_no"), watermark=WATERMARK_TEXT,
            pdf_mode=pdf_mode,
        )
        await status.edit_text("✅ PDF तैयार है।")
        await message.answer_document(FSInputFile(output), caption=f"📄 Quiz ID: {quiz_id}\n{len(questions)} questions")
    except Exception as exc:
        await status.edit_text(f"❌ PDF generation error: {type(exc).__name__}: {exc}")


async def health(request):
    return web.Response(text="English Study Centre Bot is running")


async def web_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


async def main():
    try:
        client, _ = get_mongo()
        client.close()
    except PyMongoError as exc:
        raise RuntimeError(f"MongoDB connection failed: {exc}") from exc
    runner = await web_server()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
