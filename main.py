import asyncio
import os
import re
import uuid
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
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

BACKGROUND_TASKS: set = set()
PDF_LOCK = asyncio.Semaphore(1)  # 512 MB RAM: render one PDF at a time
PDF_CACHE_VERSION = "v1"  # bump this if the PDF layout code changes

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEFAULT_HEADLINE = os.getenv("DEFAULT_HEADLINE", "ENGLISH STUDY CENTRE").strip() or "ENGLISH STUDY CENTRE"
WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "ENGLISH STUDY CENTRE").strip() or "ENGLISH STUDY CENTRE"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")


class _SharedClient:
    """Reuse one MongoClient for the whole process.

    Opening a new TLS connection to Atlas on every command is slow. Existing
    code calls client.close() after each use, so close() is a no-op here.
    """

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    def __getitem__(self, name):
        return self._client[name]

    def close(self):
        pass


_MONGO = None


def get_mongo():
    global _MONGO
    if not MONGODB_URI:
        raise RuntimeError("MONGODB_URI environment variable is required")
    if _MONGO is None:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000, maxPoolSize=5)
        client.admin.command("ping")
        _MONGO = _SharedClient(client)
    return _MONGO, _MONGO[MONGODB_DB]


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
    "📚 English Study Centre Mock Test Bot — Guide\n\n"
    "🧾 Quiz / PDF बनाना\n"
    "1. TXT file upload करें।\n"
    "2. Bot Subject, Lesson, Section, Class और Set No. पूछेगा — सभी optional हैं।\n"
    "3. Quiz ID मिलेगा।\n"
    "4. /pdf QUIZ_ID भेजकर PDF लें।\n"
    "किसी optional field को छोड़ने के लिए /skip भेजें।\n\n"
    "⚙️ Settings \n"
    "/settings या /toggle भेजें — बटन से ये बदलें:\n"
    "• 📄 PDF Layout: 50 = 25 questions/page (बड़े और साफ़), 100 = 50 questions/page\n"
    "• 📜 Question Paper: ON करके TXT पर reply में /paper भेजें\n"
    "• 📝 OMR: ON करके /omr 1 to 100 भेजें (किसी भी range के लिए)\n\n"
    "📋 Commands\n"
    "/start — शुरू करें\n"
    "/help — यह guide\n"
    "/settings — Settings panel\n"
    "/pdf QUIZ_ID — Quiz PDF\n"
    "/paper — Question Paper (TXT पर reply)\n"
    "/omr 1 to 100 — OMR sheet\n"
    "/cancel — चल रहा process रोकें\n\n"
    "╭─────────────────╮\n"
    "│ 💐 𝐃𝐢𝐫. 𝐃𝐞𝐞𝐩𝐚𝐤 𝐒𝐢𝐫 💐     │\n"
    "╰─────────────────╯"
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
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="set:menu")],
    ])
    await message.answer(HELP, reply_markup=kb)


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
        "PDF लेने के लिए नीचे का बटन दबाएँ 👇\n"
        f"(या भेजें: `/pdf {quiz_id}`)",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Get PDF", callback_data=f"getpdf:{quiz_id}")],
        ]),
    )

    # Start rendering the PDF now, in the background, so /pdf is instant later.
    task = asyncio.create_task(prebuild_pdf(quiz_id, message.from_user.id))
    BACKGROUND_TASKS.add(task)
    task.add_done_callback(BACKGROUND_TASKS.discard)


# ---------------------------------------------------------------------------
# Settings panel (inline buttons)
# ---------------------------------------------------------------------------
FEATURES = {
    "paper": {"key": "paper_enabled", "icon": "📜", "name": "Question Paper"},
    "omr": {"key": "omr_enabled", "icon": "📝", "name": "OMR"},
}


def load_settings(user_id: int) -> dict:
    client, database = get_mongo()
    try:
        return database.user_settings.find_one({"_id": user_id}) or {}
    finally:
        client.close()


def save_setting(user_id: int, key: str, value) -> None:
    client, database = get_mongo()
    try:
        database.user_settings.update_one(
            {"_id": user_id},
            {"$set": {key: value}},
            upsert=True,
        )
    finally:
        client.close()


def current_pdf_mode(settings: dict) -> int:
    try:
        mode = int(settings.get("pdf_mode", 100))
    except (TypeError, ValueError):
        mode = 100
    return mode if mode in (50, 100) else 100


def on_off(flag: bool) -> str:
    return "ON ✅" if flag else "OFF ❌"


def main_menu(settings: dict) -> tuple[str, InlineKeyboardMarkup]:
    mode = current_pdf_mode(settings)
    per_page = 25 if mode == 50 else 50
    paper = bool(settings.get("paper_enabled", False))
    omr = bool(settings.get("omr_enabled", False))
    text = (
        "⚙️ Settings\n\n"
        f"📄 PDF Layout: {mode} ({per_page} questions/page)\n"
        f"📜 Question Paper: {on_off(paper)}\n"
        f"📝 OMR: {on_off(omr)}\n\n"
        "बदलने के लिए नीचे का बटन दबाएँ।"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📄 PDF Layout · {mode}", callback_data="set:layout")],
        [InlineKeyboardButton(text=f"📜 Question Paper · {on_off(paper)}", callback_data="set:paper")],
        [InlineKeyboardButton(text=f"📝 OMR · {on_off(omr)}", callback_data="set:omr")],
        [InlineKeyboardButton(text="📖 Help / Guide", callback_data="set:help")],
        [InlineKeyboardButton(text="✖️ Close", callback_data="set:close")],
    ])
    return text, kb


def layout_menu(settings: dict) -> tuple[str, InlineKeyboardMarkup]:
    mode = current_pdf_mode(settings)
    text = (
        "📄 PDF Layout\n\n"
        "• 50 = 25 questions/page (बड़े और साफ़)\n"
        "• 100 = 50 questions/page (25 left + 25 right)\n\n"
        f"अभी चुना हुआ: {mode}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=("✅ " if mode == 50 else "") + "50 · 25 Q/page", callback_data="set:layout:50"),
            InlineKeyboardButton(text=("✅ " if mode == 100 else "") + "100 · 50 Q/page", callback_data="set:layout:100"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="set:menu")],
    ])
    return text, kb


def feature_menu(feature: str, settings: dict) -> tuple[str, InlineKeyboardMarkup]:
    info = FEATURES[feature]
    enabled = bool(settings.get(info["key"], False))
    if feature == "paper":
        how = "ON करने के बाद TXT file भेजें और उस file पर reply करके /paper भेजें।"
    else:
        how = "ON करने के बाद /omr 1 to 100 (या /omr 1-100) भेजें।"
    text = f"{info['icon']} {info['name']}\n\nStatus: {on_off(enabled)}\n\n{how}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=("✅ " if enabled else "") + "ON", callback_data=f"set:{feature}:on"),
            InlineKeyboardButton(text=("✅ " if not enabled else "") + "OFF", callback_data=f"set:{feature}:off"),
        ],
        [InlineKeyboardButton(text="🔙 Back", callback_data="set:menu")],
    ])
    return text, kb


def help_menu() -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="set:menu")],
    ])
    return HELP, kb


@dp.message(Command("settings"))
async def settings_cmd(message: Message):
    try:
        settings = load_settings(message.from_user.id)
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    text, kb = main_menu(settings)
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data.startswith("set:"))
async def settings_callback(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        await callback.answer("Message पुराना हो गया है। /settings दोबारा भेजें।", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    screen = parts[1] if len(parts) > 1 else "menu"
    value = parts[2] if len(parts) > 2 else None
    user_id = callback.from_user.id
    toast = None

    try:
        if screen == "close":
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.answer()
            return

        if screen == "layout" and value in {"50", "100"}:
            save_setting(user_id, "pdf_mode", int(value))
            toast = f"✅ PDF layout set: {value}"
        elif screen in FEATURES and value in {"on", "off"}:
            save_setting(user_id, FEATURES[screen]["key"], value == "on")
            toast = f"{FEATURES[screen]['name']}: " + ("ENABLED ✅" if value == "on" else "DISABLED ❌")

        settings = load_settings(user_id)
    except PyMongoError as exc:
        await callback.answer(f"❌ MongoDB error: {type(exc).__name__}", show_alert=True)
        return

    if screen == "layout":
        text, kb = layout_menu(settings)
    elif screen in FEATURES:
        text, kb = feature_menu(screen, settings)
    elif screen == "help":
        text, kb = help_menu()
    else:
        text, kb = main_menu(settings)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await callback.answer(toast)


@dp.message(Command("toggle"))
async def toggle_cmd(message: Message):
    parts = (message.text or "").split()

    # /toggle  -> open the inline settings panel
    if len(parts) == 1:
        await settings_cmd(message)
        return

    # Old text commands still work: /toggle paper on, /toggle omr off
    if len(parts) == 3 and parts[1].lower() in FEATURES and parts[2].lower() in {"on", "off"}:
        feature = parts[1].lower()
        enabled = parts[2].lower() == "on"
        info = FEATURES[feature]
        try:
            save_setting(message.from_user.id, info["key"], enabled)
        except PyMongoError as exc:
            await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
            return
        await message.answer(f"{info['icon']} {info['name']}: " + ("ENABLED ✅" if enabled else "DISABLED ❌"))
        return

    # Old text commands still work: /toggle 50, /toggle 100
    if len(parts) != 2 or parts[1].strip() not in {"50", "100"}:
        await message.answer("❌ सही option नहीं मिला। बटन वाला panel खोलने के लिए /settings भेजें।")
        return
    mode = int(parts[1].strip())
    try:
        save_setting(message.from_user.id, "pdf_mode", mode)
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    if mode == 50:
        await message.answer("✅ PDF layout set: 50\n25 questions per page — बड़ा और साफ़ format.")
    else:
        await message.answer("✅ PDF layout set: 100\n50 questions per page — 25 left + 25 right.")


@dp.message(Command("omr"))
async def omr_cmd(message: Message):
    parts = (message.text or "").split()
    if len(parts) == 4 and parts[2].lower() == "to":
        start_text, end_text = parts[1], parts[3]
    elif len(parts) == 2 and "-" in parts[1]:
        start_text, end_text = parts[1].split("-", 1)
    elif len(parts) == 2 and parts[1].isdigit():
        start_text, end_text = "1", parts[1]
    else:
        await message.answer("Usage: /omr 1 to 100\nया /omr 1-100")
        return

    try:
        start_num, end_num = int(start_text), int(end_text)
        if start_num < 1 or end_num < start_num or end_num > 1000:
            raise ValueError
    except ValueError:
        await message.answer("❌ सही range दें। उदाहरण: /omr 1 to 100 (अधिकतम 1000 questions)")
        return

    try:
        client, database = get_mongo()
        settings = database.user_settings.find_one({"_id": message.from_user.id}) or {}
        client.close()
    except PyMongoError as exc:
        await message.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return

    if not settings.get("omr_enabled", False):
        await message.answer("⛔ OMR function disabled है। पहले /settings में OMR ON करें।")
        return

    output = GENERATED / f"OMR_{start_num}_to_{end_num}_{message.from_user.id}_{uuid.uuid4().hex[:8]}.pdf"
    status = await message.answer("⏳ OMR PDF बना रहा हूँ...")
    try:
        generate_omr_pdf(start_num, end_num, output)
        await message.answer_document(
            FSInputFile(output),
            caption=f"📝 OMR Answer Sheet\nQuestions: {start_num}–{end_num}",
        )
        await status.edit_text("✅ OMR PDF तैयार है।")
    except Exception as exc:
        await status.edit_text(f"❌ OMR PDF error: {type(exc).__name__}: {exc}")


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
        await message.answer("⛔ Question Paper function disabled है। पहले /settings में Question Paper ON करें।")
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


def questions_from_row(row) -> list[Question]:
    # MongoDB stores each question as a dict; the PDF generator expects
    # Question objects. Support both formats (old and new quizzes).
    return [
        q if isinstance(q, Question) else Question(
            number=int(q.get("number", index)),
            text=str(q.get("text", "")),
            options=list(q.get("options") or []),
        )
        for index, q in enumerate(row.get("questions", []), start=1)
    ]


async def render_quiz_pdf(row, pdf_mode: int):
    """Render (or reuse an already rendered) PDF. One render at a time."""
    quiz_id = row["_id"]
    questions = questions_from_row(row)
    output = GENERATED / f"English_Study_Centre_{quiz_id}_M{pdf_mode}.pdf"
    async with PDF_LOCK:
        if not output.exists():
            try:
                # WeasyPrint is CPU heavy; use a worker thread so the bot and
                # Render's /health check keep responding meanwhile.
                await asyncio.to_thread(
                    generate_pdf,
                    questions=questions,
                    output_path=output,
                    headline=row.get("headline") or DEFAULT_HEADLINE,
                    subject=row.get("subject"), lesson=row.get("lesson"),
                    section=row.get("section") if row.get("section") is not None else row.get("to" + "pic"), class_name=row.get("class_name"),
                    set_no=row.get("set_no"), watermark=WATERMARK_TEXT,
                    pdf_mode=pdf_mode,
                )
            except BaseException:
                output.unlink(missing_ok=True)  # never keep a half-written PDF
                raise
    return output, len(questions)


async def prebuild_pdf(quiz_id: str, user_id: int):
    """Best-effort: render the PDF in the background right after quiz creation."""
    try:
        client, database = get_mongo()
        row = database.quizzes.find_one({"_id": quiz_id})
        settings = database.user_settings.find_one({"_id": user_id}) or {}
        client.close()
        if row:
            await render_quiz_pdf(row, current_pdf_mode(settings))
    except Exception:
        pass  # /pdf will simply render it on demand


PDF_IN_PROGRESS: set = set()


async def deliver_quiz_pdf(target: Message, user_id: int, quiz_id: str):
    """Send the PDF of a quiz to the chat of `target`. Used by /pdf and the Get PDF button."""
    quiz_id = quiz_id.strip().upper()
    try:
        client, database = get_mongo()
        row = database.quizzes.find_one({"_id": quiz_id})
        client.close()
    except PyMongoError as exc:
        await target.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return
    if not row:
        await target.answer("❌ Quiz ID नहीं मिला।")
        return
    if row.get("user_id") != user_id:
        await target.answer("❌ यह Quiz ID आपके account की नहीं है।")
        return

    try:
        client, database = get_mongo()
        settings = database.user_settings.find_one({"_id": user_id}) or {}
        client.close()
        pdf_mode = int(settings.get("pdf_mode", 100))
        if pdf_mode not in (50, 100):
            pdf_mode = 100
    except PyMongoError as exc:
        await target.answer(f"❌ MongoDB error: {type(exc).__name__}: {exc}")
        return

    cache_key = f"{PDF_CACHE_VERSION}_{pdf_mode}"
    cached_id = (row.get("pdf_cache") or {}).get(cache_key)
    if cached_id:
        # Same quiz + same layout was already generated: resend instantly.
        try:
            await target.answer_document(
                cached_id, caption=f"📄 Quiz ID: {quiz_id}\n{row.get('question_count', '')} questions"
            )
            return
        except TelegramBadRequest:
            pass  # file_id expired/invalid -> regenerate below

    progress_key = (quiz_id, pdf_mode)
    if progress_key in PDF_IN_PROGRESS:
        await target.answer("⏳ यह PDF पहले से बन रहा है, थोड़ा रुकें।")
        return
    PDF_IN_PROGRESS.add(progress_key)

    per_page = 25 if pdf_mode == 50 else 50
    status = await target.answer(f"⏳ PDF बना रहा हूँ... {per_page} questions/page layout तैयार हो रहा है।")
    output = None
    try:
        output, question_count = await render_quiz_pdf(row, pdf_mode)
        await status.edit_text("✅ PDF तैयार है।")
        sent = await target.answer_document(FSInputFile(output), caption=f"📄 Quiz ID: {quiz_id}\n{question_count} questions")
        try:
            if sent.document:
                client, database = get_mongo()
                database.quizzes.update_one({"_id": quiz_id}, {"$set": {f"pdf_cache.{cache_key}": sent.document.file_id}})
                client.close()
        except PyMongoError:
            pass  # caching is best-effort
    except Exception as exc:
        await status.edit_text(f"❌ PDF generation error: {type(exc).__name__}: {exc}")
    finally:
        PDF_IN_PROGRESS.discard(progress_key)
        if output is not None:
            output.unlink(missing_ok=True)  # keep the small free-tier disk clean


@dp.message(Command("pdf"))
async def pdf_cmd(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: `/pdf QUIZ_ID`", parse_mode="Markdown")
        return
    await deliver_quiz_pdf(message, message.from_user.id, parts[1])


@dp.callback_query(F.data.startswith("getpdf:"))
async def get_pdf_button(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        await callback.answer("Message पुराना हो गया है। /pdf QUIZ_ID भेजें।", show_alert=True)
        return
    quiz_id = (callback.data or "").split(":", 1)[1]
    await callback.answer("⏳ PDF भेज रहा हूँ...")
    await deliver_quiz_pdf(callback.message, callback.from_user.id, quiz_id)


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
        await bot.set_my_commands([
            BotCommand(command="start", description="Bot शुरू करें"),
            BotCommand(command="help", description="Guide / मदद"),
            BotCommand(command="settings", description="Settings (layout, paper, OMR)"),
            BotCommand(command="pdf", description="Quiz PDF — /pdf QUIZ_ID"),
            BotCommand(command="cancel", description="Current process रोकें"),
        ])
    except Exception:
        pass  # command menu is optional; never block bot start-up
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
