import os
import logging
import re
import random
import asyncio
import subprocess
import unicodedata
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import TerminatedByOtherGetUpdates
import textwrap

# ========== КОНФИГ ==========
BOT_VERSION = "video-stories-v2"

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Создай переменную BOT_TOKEN.")

ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
if ADMIN_CHAT_ID:
    try:
        ADMIN_CHAT_ID = int(ADMIN_CHAT_ID)
    except ValueError:
        ADMIN_CHAT_ID = None
        logging.warning("⚠️ ADMIN_CHAT_ID должен быть числом")
else:
    logging.warning("⚠️ ADMIN_CHAT_ID не задан")

FONT_PATHS = [
    "Inter-Black.ttf", "Inter-Bold.ttf", "Inter-Regular.ttf", "Inter-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "arial.ttf"
]

W, H = 1080, 1920
PHOTO_TOP = 0
PHOTO_HEIGHT = 900
PHOTO_WIDTH = W
PHOTO_LEFT = 0

RUBRIC_TOP = PHOTO_TOP + PHOTO_HEIGHT + 20
RUBRIC_LEFT = 40
RUBRIC_PADDING_X = 30
RUBRIC_PADDING_Y = 12

TITLE_TOP = PHOTO_TOP + PHOTO_HEIGHT + 90
TITLE_MAX_WIDTH = W - 100
TITLE_LINE_SPACING = 12
LINE_TOP_OFFSET = 30
LINE_HEIGHT = 8
TEXT_TOP_OFFSET = 15

# Инста-шаблон
IW, IH = 720, 1280
I_PHOTO_TOP = 0
I_PHOTO_HEIGHT = 520
I_PHOTO_WIDTH = IW
I_PHOTO_LEFT = 0
I_MARGIN_X = 32
I_TITLE_TOP = I_PHOTO_HEIGHT + 28
I_TITLE_FONT_MAX = 54
I_TITLE_FONT_MIN = 20
I_TITLE_PLATE_PAD_X = 18
I_TITLE_PLATE_PAD_Y = 10
I_TITLE_PLATE_RADIUS = 16
I_TITLE_LINE_GAP = -1
I_TEXT_TOP_GAP = 24
I_TEXT_FONT_MAX = 30
I_TEXT_FONT_MIN = 16
I_TEXT_LINE_GAP = 6
I_TEXT_PARA_GAP = 16

RUBRICS = ["НОВОСТИ", "АФИША", "СПОРТ", "ФИНАНСЫ", "АВТО", "НЕДВИЖИМОСТЬ"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

VIDEO_MAX_DURATION = 30


# ========== УТИЛИТЫ ==========
def load_font(size, weight='regular'):
    font_names = {
        'black': ["Inter-Black.ttf"] + FONT_PATHS,
        'bold': ["Inter-Bold.ttf", "Inter-Black.ttf"] + FONT_PATHS,
        'bold_text': ["Inter-Bold.ttf", "Inter-Black.ttf"] + FONT_PATHS,
        'medium': [FONT_PATHS[3], FONT_PATHS[1], FONT_PATHS[5]],
        'regular': ["Inter-Regular.ttf", "Inter-Bold.ttf"] + FONT_PATHS[4:]
    }
    paths = font_names.get(weight, ["Inter-Regular.ttf", "Inter-Bold.ttf"] + FONT_PATHS[4:])
    for path in paths:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    logging.warning(f"⚠️ Шрифт не найден (weight={weight}, size={size})")
    return ImageFont.load_default()


def remove_emojis(text: str) -> str:
    if not text:
        return text
    out = []
    for ch in text:
        code = ord(ch)
        if (0x1F300 <= code <= 0x1FAFF or 0x1F000 <= code <= 0x1F2FF or
            0x2600 <= code <= 0x27BF or 0x2B00 <= code <= 0x2BFF or
            0xFE00 <= code <= 0xFE0F or 0x1F1E6 <= code <= 0x1F1FF or
            0xE0020 <= code <= 0xE007F):
            continue
        if unicodedata.category(ch) == 'So':
            continue
        out.append(ch)
    cleaned = ''.join(out)
    cleaned = re.sub(r'\s+([,.!?;:…»)])', r'\1', cleaned)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = '\n'.join(line.strip() for line in cleaned.split('\n'))
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def parse_text(text: str):
    if not text:
        return "", ""
    text = text.strip()
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) > 1:
        return paragraphs[0], "\n\n".join(paragraphs[1:])
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) > 1:
        return lines[0], '\n\n'.join(lines[1:])
    for pattern in (r'\.\s+([А-ЯA-Z])', r'[?!]\s+([А-ЯA-Z])'):
        m = re.search(pattern, text)
        if m:
            cut = m.start() + 1
            return text[:cut].strip(), text[cut:].strip()
    return text, ""


def apply_photo_effect(image: Image.Image) -> Image.Image:
    if image.mode != 'RGB':
        image = image.convert('RGB')
    image = ImageEnhance.Color(image).enhance(1.05)
    pixels = list(image.getdata())
    noisy = []
    for (r, g, b) in pixels:
        noisy.append((
            max(0, min(255, r + random.randint(-12, 12))),
            max(0, min(255, g + random.randint(-12, 12))),
            max(0, min(255, b + random.randint(-12, 12))),
        ))
    out = Image.new('RGB', image.size)
    out.putdata(noisy)
    return out


def fit_photo(photo: Image.Image, tw: int, th: int) -> Image.Image:
    pr = photo.width / photo.height
    tr = tw / th
    if pr > tr:
        nh = th
        nw = int(nh * pr)
        photo = photo.resize((nw, nh), Image.Resampling.LANCZOS)
        left = (nw - tw) // 2
        return photo.crop((left, 0, left + tw, nh))
    nw = tw
    nh = int(nw / pr)
    photo = photo.resize((nw, nh), Image.Resampling.LANCZOS)
    top = (nh - th) // 2
    return photo.crop((0, top, nw, top + th))


# ========== РЕНДЕР СТАТИЧНОГО СЛОЯ ==========
def render_base_canvas(title, content, rubric, highlight_words, theme, photo_path=None, transparent_top=False):
    is_dark = (theme == "dark")
    bg_color = 'black' if is_dark else 'white'
    text_color = 'white' if is_dark else 'black'
    placeholder_bg = '#1a1a1a' if is_dark else '#f0f0f0'
    placeholder_outline = '#333333' if is_dark else '#cccccc'
    placeholder_text = '#666666' if is_dark else '#999999'

    mode = 'RGBA' if transparent_top else 'RGB'
    canvas = Image.new(mode, (W, H), (0, 0, 0, 0) if transparent_top else bg_color)
    draw = ImageDraw.Draw(canvas)

    if not transparent_top:
        try:
            if photo_path and os.path.exists(photo_path):
                photo = Image.open(photo_path).convert("RGB")
                photo = fit_photo(photo, PHOTO_WIDTH, PHOTO_HEIGHT)
                photo = apply_photo_effect(photo)
                canvas.paste(photo, (PHOTO_LEFT, PHOTO_TOP))
            else:
                raise FileNotFoundError(photo_path)
        except Exception as e:
            logging.error(f"❌ Фото: {e}")
            draw.rectangle([PHOTO_LEFT, PHOTO_TOP, PHOTO_LEFT + PHOTO_WIDTH, PHOTO_TOP + PHOTO_HEIGHT],
                           fill=placeholder_bg, outline=placeholder_outline, width=2)
            draw.text((W // 2 - 60, PHOTO_TOP + PHOTO_HEIGHT // 2 - 10),
                      "📷 ФОТО", font=load_font(36, 'bold'), fill=placeholder_text)

    if rubric:
        rf = load_font(34, 'bold')
        rb = draw.textbbox((0, 0), rubric, font=rf)
        rw, rh = rb[2] - rb[0], rb[3] - rb[1]
        x1, y1 = RUBRIC_LEFT, RUBRIC_TOP
        x2 = x1 + rw + RUBRIC_PADDING_X * 2
        y2 = y1 + rh + RUBRIC_PADDING_Y * 2
        draw.rectangle([x1, y1, x2, y2], fill='#6C3CE1')
        draw.text((x1 + (x2 - x1 - rw) // 2, y1 + (y2 - y1 - rh) // 2 - 4),
                  rubric, font=rf, fill='white')

    title_y = TITLE_TOP
    max_title_height = 380
    title_font_size = 56
    title_lines = []

    for size in range(72, 32, -2):
        tf = load_font(size, 'bold')
        words = title.upper().split()
        lines, cur = [], []
        for word in words:
            test = ' '.join(cur + [word])
            bb = draw.textbbox((0, 0), test, font=tf)
            if bb[2] - bb[0] <= TITLE_MAX_WIDTH:
                cur.append(word)
            else:
                if cur:
                    lines.append(' '.join(cur))
                cur = [word]
        if cur:
            lines.append(' '.join(cur))
        if lines:
            lb = draw.textbbox((0, 0), "A", font=tf)
            lh = lb[3] - lb[1]
            th = len(lines) * lh + (len(lines) - 1) * TITLE_LINE_SPACING
            if th <= max_title_height and len(lines) <= 4:
                title_font_size = size
                title_lines = lines
                break
    else:
        tf = load_font(32, 'bold')
        words = title.upper().split()
        lines, cur = [], []
        for word in words:
            test = ' '.join(cur + [word])
            bb = draw.textbbox((0, 0), test, font=tf)
            if bb[2] - bb[0] <= TITLE_MAX_WIDTH:
                cur.append(word)
            else:
                if cur:
                    lines.append(' '.join(cur))
                cur = [word]
        if cur:
            lines.append(' '.join(cur))
        title_lines = lines
        title_font_size = 32

    title_font = load_font(title_font_size, 'bold')
    purple_font = load_font(title_font_size, 'bold')
    lb = draw.textbbox((0, 0), "A", font=title_font)
    lh = lb[3] - lb[1]

    current_y = title_y
    for line in title_lines:
        cx = 50
        for word in line.split():
            is_hl = word in [w.upper() for w in highlight_words]
            font = purple_font if is_hl else title_font
            color = '#6C3CE1' if is_hl else text_color
            draw.text((cx, current_y), word, font=font, fill=color)
            wb = draw.textbbox((0, 0), word, font=font)
            cx += (wb[2] - wb[0]) + 10
        current_y += lh + TITLE_LINE_SPACING
    title_end_y = current_y - TITLE_LINE_SPACING

    LINE_TOP = title_end_y + LINE_TOP_OFFSET
    draw.rectangle([50, LINE_TOP, W - 50, LINE_TOP + LINE_HEIGHT], fill='#6C3CE1')

    text_y = LINE_TOP + LINE_HEIGHT + TEXT_TOP_OFFSET
    available_text_height = H - text_y - 50
    if content and content != "Текст отсутствует":
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    else:
        paragraphs = ["Текст отсутствует"]

    text_font_size = 34
    wrapped_paragraphs = []
    for size in range(42, 20, -2):
        tf = load_font(size, 'regular')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        total_h = 0
        tmp = []
        for para in paragraphs:
            cpl = int((W - 100) / (size * 0.6))
            w = textwrap.wrap(para, width=cpl) or [para]
            tmp.append(w)
            total_h += len(w) * (sh + 8) + 18
        if total_h <= available_text_height:
            text_font_size = size
            wrapped_paragraphs = tmp
            break
    else:
        tf = load_font(20, 'regular')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        for para in paragraphs:
            cpl = int((W - 100) / (20 * 0.6))
            wrapped_paragraphs.append(textwrap.wrap(para, width=cpl) or [para])
        text_font_size = 20

    text_font = load_font(text_font_size, 'regular')
    sb = draw.textbbox((0, 0), "A", font=text_font)
    sh = sb[3] - sb[1]
    pos_y = text_y
    for para_lines in wrapped_paragraphs:
        for line in para_lines:
            draw.text((50, pos_y), line, font=text_font, fill=text_color)
            pos_y += sh + 8
        pos_y += 18

    return canvas


# ========== СТАТИЧНЫЕ ГЕНЕРАТОРЫ ==========
async def generate_story_classic(photo_path, title, content, rubric, highlight_words, theme="light"):
    canvas = render_base_canvas(title, content, rubric, highlight_words, theme, photo_path)
    out = f"output_story_classic_{theme}.png"
    canvas.save(out, format='PNG')
    return out


def draw_rounded_rect_highres(draw, box, radius, fill):
    x1, y1, x2, y2 = box
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    if r <= 0:
        draw.rectangle(box, fill=fill)
        return
    scale = 4
    width, height = (x2 - x1) * scale, (y2 - y1) * scale
    if width <= 0 or height <= 0:
        return
    temp = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(temp).rounded_rectangle([0, 0, width - 1, height - 1], radius=r * scale, fill=fill)
    temp = temp.resize((x2 - x1, y2 - y1), Image.Resampling.LANCZOS)
    draw._image.paste(temp, (x1, y1), temp)


def wrap_title_by_width(draw, text, font, max_width):
    words = text.upper().split()
    lines, cur = [], []
    for word in words:
        test = ' '.join(cur + [word])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_width:
            cur.append(word)
        else:
            if cur:
                lines.append(' '.join(cur))
            cur = [word]
    if cur:
        lines.append(' '.join(cur))
    return lines


def wrap_text_strict(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], []
    for word in words:
        test = ' '.join(cur + [word])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_width:
            cur.append(word)
        else:
            if cur:
                lines.append(' '.join(cur))
            cur = [word]
    if cur:
        lines.append(' '.join(cur))
    return lines


async def generate_story_insta(photo_path, title, content, theme="dark"):
    if theme == "dark":
        bg_color, text_color, plate_color, title_text_color = 'black', 'white', 'white', 'black'
        placeholder_bg, placeholder_outline, placeholder_text = '#111111', '#333333', '#666666'
    else:
        bg_color, text_color, plate_color, title_text_color = 'white', 'black', 'black', 'white'
        placeholder_bg, placeholder_outline, placeholder_text = '#f0f0f0', '#cccccc', '#999999'

    canvas = Image.new('RGB', (IW, IH), color=bg_color)
    draw = ImageDraw.Draw(canvas)

    try:
        if photo_path and os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo = fit_photo(photo, I_PHOTO_WIDTH, I_PHOTO_HEIGHT)
            photo = apply_photo_effect(photo)
            canvas.paste(photo, (I_PHOTO_LEFT, I_PHOTO_TOP))
        else:
            raise FileNotFoundError(photo_path)
    except Exception as e:
        logging.error(f"❌ Фото: {e}")
        draw.rectangle([I_PHOTO_LEFT, I_PHOTO_TOP, I_PHOTO_LEFT + I_PHOTO_WIDTH, I_PHOTO_TOP + I_PHOTO_HEIGHT],
                       fill=placeholder_bg, outline=placeholder_outline, width=2)
        draw.text((IW // 2 - 50, I_PHOTO_HEIGHT // 2 - 10), "📷 ФОТО",
                  font=load_font(28, 'black'), fill=placeholder_text)

    max_width = IW - 2 * I_MARGIN_X
    title_words_count = len(title.upper().split())
    max_lines_allowed = 3 if title_words_count <= 9 else 4

    title_font_size, title_lines = I_TITLE_FONT_MAX, []
    for size in range(I_TITLE_FONT_MAX, I_TITLE_FONT_MIN - 1, -1):
        tf = load_font(size, 'black')
        lines = wrap_title_by_width(draw, title, tf, max_width - 2 * I_TITLE_PLATE_PAD_X)
        lb = draw.textbbox((0, 0), "A", font=tf)
        lh = lb[3] - lb[1]
        plate_h = lh + 2 * I_TITLE_PLATE_PAD_Y
        total_h = len(lines) * plate_h + (len(lines) - 1) * I_TITLE_LINE_GAP
        if len(lines) <= max_lines_allowed and total_h <= 300:
            title_font_size, title_lines = size, lines
            break
    if not title_lines:
        tf = load_font(I_TITLE_FONT_MIN, 'black')
        title_lines = wrap_title_by_width(draw, title, tf, max_width - 2 * I_TITLE_PLATE_PAD_X)
        title_font_size = I_TITLE_FONT_MIN

    title_font = load_font(title_font_size, 'black')
    lb = draw.textbbox((0, 0), "A", font=title_font)
    lh = lb[3] - lb[1]
    plate_h = lh + 2 * I_TITLE_PLATE_PAD_Y
    cur_y = I_TITLE_TOP
    max_plate_w = 0

    for line in title_lines:
        wb = draw.textbbox((0, 0), line, font=title_font)
        line_w = wb[2] - wb[0]
        plate_w = line_w + 2 * I_TITLE_PLATE_PAD_X
        max_plate_w = max(max_plate_w, plate_w)
        x1, y1 = I_MARGIN_X, cur_y
        x2, y2 = x1 + plate_w, y1 + plate_h
        draw_rounded_rect_highres(draw, [x1, y1, x2, y2], I_TITLE_PLATE_RADIUS, plate_color)
        draw.text((x1 + plate_w / 2, y1 + plate_h / 2), line, font=title_font, fill=title_text_color, anchor="mm")
        cur_y = y2 + I_TITLE_LINE_GAP

    text_y = cur_y + I_TEXT_TOP_GAP
    available_h = IH - text_y - 24
    text_line_max_width = max_plate_w - 4

    if content and content != "Текст отсутствует":
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    else:
        paragraphs = ["Текст отсутствует"]

    text_font_size, wrapped_paragraphs = I_TEXT_FONT_MAX, []
    for size in range(I_TEXT_FONT_MAX, I_TEXT_FONT_MIN - 1, -1):
        tf = load_font(size, 'bold_text')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        total_h, tmp = 0, []
        for para in paragraphs:
            lines = wrap_text_strict(draw, para.upper(), tf, text_line_max_width)
            tmp.append(lines)
            total_h += len(lines) * (sh + I_TEXT_LINE_GAP) + I_TEXT_PARA_GAP
        if total_h <= available_h:
            text_font_size, wrapped_paragraphs = size, tmp
            break
    if not wrapped_paragraphs:
        tf = load_font(I_TEXT_FONT_MIN, 'bold_text')
        for para in paragraphs:
            wrapped_paragraphs.append(wrap_text_strict(draw, para.upper(), tf, text_line_max_width))
        text_font_size = I_TEXT_FONT_MIN

    text_font = load_font(text_font_size, 'bold_text')
    sb = draw.textbbox((0, 0), "A", font=text_font)
    sh = sb[3] - sb[1]
    pos_y = text_y
    for para_lines in wrapped_paragraphs:
        for line in para_lines:
            draw.text((I_MARGIN_X, pos_y), line, font=text_font, fill=text_color)
            pos_y += sh + I_TEXT_LINE_GAP
        pos_y += I_TEXT_PARA_GAP

    out = f"output_story_insta_{theme}.png"
    canvas.save(out, format='PNG')
    return out


# ========== ВИДЕО-СТОРИС ==========
def generate_video_story(video_path, title, content, rubric, highlight_words, theme, out_path):
    logging.info(f"🎬 Старт генерации видео: {video_path} → {out_path}")
    base = render_base_canvas(
        title, content, rubric, highlight_words, theme,
        photo_path=None, transparent_top=True
    )
    base_path = f"base_{os.path.basename(out_path)}.png"
    base.save(base_path, format='PNG')
    logging.info(f"🖼 Подложка сохранена: {base_path}")

    filter_complex = (
        f"[0:v]trim=0:{VIDEO_MAX_DURATION},setpts=PTS-STARTPTS,"
        f"scale={PHOTO_WIDTH}:{PHOTO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={PHOTO_WIDTH}:{PHOTO_HEIGHT},setsar=1,fps=30[v];"
        f"[1:v][v]overlay=0:0:shortest=0[outv]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-loop", "1", "-i", base_path,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-t", str(VIDEO_MAX_DURATION),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        out_path,
    ]

    logging.info(f"🎬 FFmpeg: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        os.remove(base_path)
    except Exception:
        pass

    if result.returncode != 0:
        logging.error(f"❌ FFmpeg returncode={result.returncode}")
        logging.error(f"❌ FFmpeg stderr:\n{result.stderr}")
        raise RuntimeError(f"FFmpeg failed ({result.returncode}): {result.stderr[-800:]}")

    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f"FFmpeg завершился успешно, но файл {out_path} пуст или отсутствует")

    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    logging.info(f"✅ Видео готово: {out_path} ({size_mb:.2f} MB)")
    return out_path


# ========== КЛАВИАТУРЫ ==========
def get_template_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎨 Классик", callback_data="template_classic"),
        InlineKeyboardButton("📸 Инста-дизайн", callback_data="template_insta"),
    )
    return kb


def get_theme_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("☀️ Светлая", callback_data="theme_light"),
        InlineKeyboardButton("🌙 Тёмная", callback_data="theme_dark"),
    )
    return kb


def get_rubric_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(r, callback_data=f"rubric_{r}") for r in RUBRICS]
    buttons.append(InlineKeyboardButton("🚫 БЕЗ РУБРИКИ", callback_data="rubric_none"))
    kb.add(*buttons)
    return kb


async def safe_remove_keyboard(message: types.Message):
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ========== СОСТОЯНИЕ ==========
user_data = {}


# ========== ХЕНДЛЕРЫ ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {"step": "waiting_photo"}
    await bot.send_message(
        user_id,
        f"📱 Привет! Я делаю стильные сторис (фото или видео)!\n\n"
        f"🆔 Твой user_id: <code>{user_id}</code>\n\n"
        f"Отправь РЕПОСТ поста с фото/видео и текстом — или фото/видео + подпись.\n"
        f"Видео будет обрезано до {VIDEO_MAX_DURATION} сек и вставлено сверху.",
        parse_mode="HTML"
    )


async def _download_media(message: types.Message, user_id: int):
    if message.photo:
        f = await bot.get_file(message.photo[-1].file_id)
        p = f"temp_{user_id}.jpg"
        await bot.download_file(f.file_path, p)
        return p, False
    if message.document and message.document.mime_type:
        mt = message.document.mime_type
        if mt.startswith('image/'):
            f = await bot.get_file(message.document.file_id)
            p = f"temp_{user_id}.jpg"
            await bot.download_file(f.file_path, p)
            return p, False
        if mt.startswith('video/'):
            f = await bot.get_file(message.document.file_id)
            p = f"temp_{user_id}.mp4"
            await bot.download_file(f.file_path, p)
            return p, True
    if message.video:
        f = await bot.get_file(message.video.file_id)
        p = f"temp_{user_id}.mp4"
        await bot.download_file(f.file_path, p)
        return p, True
    return None, False


@dp.message_handler(content_types=['photo', 'document', 'video'])
async def handle_media(message: types.Message):
    user_id = message.from_user.id
    is_forward = message.forward_from or message.forward_from_chat or message.forward_date

    if is_forward:
        await bot.send_message(user_id, "📥 Обнаружен репост! Обрабатываю...")

    media_path, is_video = await _download_media(message, user_id)
    if not media_path:
        await bot.send_message(user_id, "❌ Не удалось получить медиа.")
        return

    text = message.text or message.caption or ""
    text = remove_emojis(text)
    text = text.replace("**Текст отсутствует**", "").strip()
    lines = text.split('\n')
    clean = [l.strip() for l in lines
             if l.strip() and not l.strip().startswith(('Подписаться', '@', '#'))]
    text = '\n'.join(clean)

    if text:
        title, content = parse_text(text)
        if not title:
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            title = sentences[0] if sentences else "ЗАГОЛОВОК"
            content = ". ".join(sentences[1:]) if len(sentences) > 1 else "Текст отсутствует"
        if not content:
            content = "Текст отсутствует"

        user_data[user_id] = {
            "photo": media_path,
            "is_video": is_video,
            "title": title,
            "content": content,
            "highlight_words": [],
            "step": "waiting_template"
        }
        await bot.send_message(
            user_id,
            f"📝 Заголовок:\n{title}\n\n🖼 Выберите шаблон:",
            reply_markup=get_template_keyboard()
        )
        return

    user_data[user_id] = {
        "photo": media_path,
        "is_video": is_video,
        "title": None,
        "content": None,
        "highlight_words": [],
        "step": "waiting_title"
    }
    await bot.send_message(user_id, "✅ Медиа принято! Теперь отправь ЗАГОЛОВОК.")


@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if message.text.startswith('/'):
        return
    if user_id not in user_data:
        await start(message)
        return

    step = user_data[user_id].get("step", "")

    if step == "waiting_title":
        user_data[user_id]["title"] = remove_emojis(message.text)
        user_data[user_id]["step"] = "waiting_content"
        await bot.send_message(user_id, "✅ Заголовок сохранён! Теперь ОСНОВНОЙ ТЕКСТ.")
        return

    if step == "waiting_content":
        user_data[user_id]["content"] = remove_emojis(message.text)
        user_data[user_id]["step"] = "waiting_template"
        await bot.send_message(user_id, "✅ Текст сохранён!\n\n🖼 Выберите шаблон:",
                               reply_markup=get_template_keyboard())
        return

    if step == "waiting_highlight_words":
        text = message.text.strip()
        if text.lower() in ['нет', '-', 'без', 'none', 'skip', 'не надо']:
            user_data[user_id]["highlight_words"] = []
        else:
            parts = text.split(',') if ',' in text else text.split()
            user_data[user_id]["highlight_words"] = [w.strip() for w in parts if len(w.strip()) > 2]
        user_data[user_id]["step"] = "waiting_theme"
        hl = ', '.join(user_data[user_id]['highlight_words']) or 'Нет'
        await bot.send_message(
            user_id,
            f"✅ Слова сохранены!\nВыделенные: {hl}\n\n🎨 Выберите тему:",
            reply_markup=get_theme_keyboard()
        )
        return

    await bot.send_message(user_id, "❓ Не понял. /start чтобы начать заново.")


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('template_'))
async def process_template_callback(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    logging.info(f"🔘 template callback: {cb.data} от {user_id}")
    template = "insta" if cb.data == "template_insta" else "classic"
    await cb.answer()

    if user_id not in user_data:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return
    if user_data[user_id].get("step") not in ["waiting_template", "waiting_title", "waiting_content"]:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return

    user_data[user_id]["template"] = template
    await safe_remove_keyboard(cb.message)

    if template == "classic":
        user_data[user_id]["step"] = "waiting_highlight_words"
        title = user_data[user_id].get("title", "") or ""
        example = ', '.join(title.split()[:3]) if title.split() else 'важные слова'
        await bot.send_message(
            user_id,
            f"🎨 Шаблон: Классик\n\n"
            f"✏️ Отправь слова для выделения фиолетовым (через запятую/пробел).\n"
            f"Например: {example}\n\nЕсли не нужно — 'нет' или '-'"
        )
    else:
        if user_data[user_id].get("is_video"):
            user_data[user_id]["step"] = "waiting_theme"
            await bot.send_message(
                user_id,
                "📸 Шаблон: Инста-дизайн (видео).\n\n🎨 Выберите тему:",
                reply_markup=get_theme_keyboard()
            )
            return

        user_data[user_id]["step"] = "waiting_generation"
        photo_path = user_data[user_id].get("photo")
        title = user_data[user_id].get("title")
        content = user_data[user_id].get("content")
        if not photo_path or not title:
            await bot.send_message(user_id, "❌ Не хватает данных. /start")
            return

        await bot.send_message(
            user_id,
            "⏳ Генерирую два варианта «Инста-дизайн»...\n1. Чёрный фон\n2. Белый фон"
        )
        dark_out = await generate_story_insta(photo_path, title, content, theme="dark")
        with open(dark_out, 'rb') as f:
            await bot.send_photo(chat_id=user_id, photo=f, caption="1. Чёрный фон")
        light_out = await generate_story_insta(photo_path, title, content, theme="light")
        with open(light_out, 'rb') as f:
            await bot.send_photo(chat_id=user_id, photo=f, caption="2. Белый фон")
        for p in [photo_path, dark_out, light_out]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        user_data.pop(user_id, None)


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('theme_'))
async def process_theme_callback(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    logging.info(f"🔘 theme callback: {cb.data} от {user_id}")
    theme = "dark" if cb.data == "theme_dark" else "light"
    await cb.answer()

    if user_id not in user_data:
        await bot.send_message(user_id, "❌ /start")
        return
    if user_data[user_id].get("step") not in ["waiting_theme", "waiting_highlight_words"]:
        await bot.send_message(user_id, "❌ /start")
        return

    user_data[user_id]["theme"] = theme
    user_data[user_id]["step"] = "waiting_rubric"
    await safe_remove_keyboard(cb.message)

    await bot.send_message(
        user_id,
        f"🎨 Тема: {'🌙 Тёмная' if theme == 'dark' else '☀️ Светлая'}\n\n"
        f"📌 Выберите рубрику:",
        reply_markup=get_rubric_keyboard()
    )


@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rubric_'))
async def process_rubric_callback(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    logging.info(f"🔘 rubric callback: {cb.data} от {user_id}")
    raw = cb.data.replace('rubric_', '')
    rubric = None if raw == 'none' else raw
    await cb.answer()

    if user_id not in user_data:
        await bot.send_message(user_id, "❌ /start")
        return
    if user_data[user_id].get("step") not in ["waiting_rubric", "waiting_theme"]:
        await bot.send_message(user_id, "❌ /start")
        return

    user_data[user_id]["rubric"] = rubric
    await safe_remove_keyboard(cb.message)

    photo_path = user_data[user_id].get("photo")
    title = user_data[user_id].get("title")
    content = user_data[user_id].get("content")
    highlight_words = user_data[user_id].get("highlight_words", [])
    theme = user_data[user_id].get("theme", "light")
    template = user_data[user_id].get("template", "classic")
    is_video = user_data[user_id].get("is_video", False)

    if not photo_path or not title:
        await bot.send_message(user_id, "❌ Не хватает данных. /start")
        return

    if is_video:
        await bot.send_message(user_id, "⏳ Обрабатываю видео (до 30 сек) — это займёт немного времени...")
        out_path = f"output_video_{user_id}.mp4"
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                generate_video_story,
                photo_path, title, content, rubric, highlight_words, theme, out_path
            )
            logging.info(f"📤 Отправляю видео: {out_path}")
            with open(out_path, 'rb') as f:
                await bot.send_video(
                    chat_id=user_id,
                    video=f,
                    duration=VIDEO_MAX_DURATION,
                    caption=f"✅ Готово! ({'🌙' if theme == 'dark' else '☀️'} · {rubric or 'без рубрики'})"
                )
            logging.info(f"✅ Видео отправлено пользователю {user_id}")
        except Exception as e:
            logging.exception("❌ Video generation failed")
            await bot.send_message(user_id, f"❌ Ошибка видео: {e}")
        finally:
            for p in [photo_path, out_path]:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            user_data.pop(user_id, None)
        return

    await bot.send_message(
        user_id,
        f"⏳ Генерирую сторис (🎨 {'тёмная' if theme == 'dark' else 'светлая'}"
        f"{', рубрика: ' + rubric if rubric else ''})..."
    )
    try:
        out = await generate_story_classic(photo_path, title, content, rubric, highlight_words, theme)
        with open(out, 'rb') as f:
            await bot.send_photo(chat_id=user_id, photo=f, caption="✅ Готово!")
        for p in [photo_path, out]:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
    except Exception as e:
        logging.exception("❌ Photo generation failed")
        await bot.send_message(user_id, f"❌ Ошибка: {e}")
    finally:
        user_data.pop(user_id, None)


# ========== АВТОПОСТИНГ ИЗ КАНАЛА ==========
@dp.channel_post_handler(content_types=['photo', 'document', 'video', 'text'])
async def handle_channel_post(message: types.Message):
    chat_title = message.chat.title or str(message.chat.id)
    logging.info(f"📢 Новый пост в канале «{chat_title}» (id={message.chat.id})")

    text = message.text or message.caption or ""
    if not text.strip():
        logging.info("⏭ Пост без текста — пропускаю")
        return

    target_chat = ADMIN_CHAT_ID if ADMIN_CHAT_ID else message.chat.id

    media_path = None
    is_video = False
    try:
        if message.photo:
            f = await bot.get_file(message.photo[-1].file_id)
            media_path = f"temp_ch_{message.chat.id}_{message.message_id}.jpg"
            await bot.download_file(f.file_path, media_path)
        elif message.video:
            f = await bot.get_file(message.video.file_id)
            media_path = f"temp_ch_{message.chat.id}_{message.message_id}.mp4"
            await bot.download_file(f.file_path, media_path)
            is_video = True
        elif message.document and message.document.mime_type:
            mt = message.document.mime_type
            if mt.startswith('image/'):
                f = await bot.get_file(message.document.file_id)
                media_path = f"temp_ch_{message.chat.id}_{message.message_id}.jpg"
                await bot.download_file(f.file_path, media_path)
            elif mt.startswith('video/'):
                f = await bot.get_file(message.document.file_id)
                media_path = f"temp_ch_{message.chat.id}_{message.message_id}.mp4"
                await bot.download_file(f.file_path, media_path)
                is_video = True
    except Exception as e:
        logging.error(f"❌ Скачивание медиа из канала: {e}")

    text = text.replace("**Текст отсутствует**", "").strip()
    lines = text.split('\n')
    clean = [l.strip() for l in lines
             if l.strip() and not l.strip().startswith(('Подписаться', '@', '#'))]
    text = remove_emojis('\n'.join(clean))

    title, content = parse_text(text)
    if not title and text:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        title = sentences[0] if sentences else "ЗАГОЛОВОК НОВОСТИ"
        content = ". ".join(sentences[1:]) if len(sentences) > 1 else "Текст отсутствует"
    if not title:
        title = "ЗАГОЛОВОК НОВОСТИ"
    if not content:
        content = "Текст отсутствует"

    media_for_gen = media_path if media_path else "nonexistent.jpg"
    generated = []

    try:
        await bot.send_message(
            target_chat,
            f"📢 Новый пост в канале «{chat_title}»\n"
            f"{'🎬 Обнаружено видео — генерирую видео-сторис (30 сек)' if is_video else '🎨 Генерирую 4 варианта сторис'}"
        )

        if is_video:
            out_v = f"ch_video_{message.chat.id}_{message.message_id}.mp4"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, generate_video_story,
                media_for_gen, title, content, None, [], "dark", out_v
            )
            generated.append(out_v)
            logging.info(f"📤 Отправляю видео из канала: {out_v}")
            with open(out_v, 'rb') as f:
                await bot.send_video(
                    chat_id=target_chat,
                    video=f,
                    duration=VIDEO_MAX_DURATION,
                    caption=f"🎬 Видео-сторис (30 сек)\n\n📝 {title[:120]}"
                )
            logging.info(f"✅ Видео из канала отправлено в {target_chat}")
        else:
            variants = [
                ("classic", "light", "🎨 Классик · ☀️ Светлая"),
                ("classic", "dark",  "🎨 Классик · 🌙 Тёмная"),
                ("insta",   "light", "📸 Инста-дизайн · ☀️ Светлая"),
                ("insta",   "dark",  "📸 Инста-дизайн · 🌙 Тёмная"),
            ]
            for template, theme, label in variants:
                try:
                    if template == "classic":
                        out_path = await generate_story_classic(media_for_gen, title, content, None, [], theme)
                    else:
                        out_path = await generate_story_insta(media_for_gen, title, content, theme)
                    generated.append(out_path)
                    with open(out_path, 'rb') as f:
                        await bot.send_photo(chat_id=target_chat, photo=f,
                                             caption=f"{label}\n\n📝 {title[:120]}")
                except Exception as e:
                    logging.error(f"❌ {template}/{theme}: {e}")

        logging.info(f"✅ Сторис для «{chat_title}» отправлены в {target_chat}")

    except Exception as e:
        logging.exception("❌ Channel post processing failed")
        try:
            await bot.send_message(target_chat, f"❌ Ошибка: {e}")
        except Exception:
            pass

    finally:
        for p in [media_path] + generated:
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


# ========== ЗАПУСК ==========
async def on_startup(dp):
    print(f"🚀 BOT VERSION: {BOT_VERSION}")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Вебхук удалён")
    except Exception as e:
        print(f"⚠️ delete_webhook: {e}")
    await asyncio.sleep(3)
    try:
        me = await bot.get_me()
        print(f"✅ Бот: @{me.username} (id={me.id})")
    except Exception as e:
        print(f"⚠️ get_me: {e}")
    print(f"📥 ADMIN_CHAT_ID: {ADMIN_CHAT_ID or 'не задан (в канал)'}")


async def on_shutdown(dp):
    try:
        await bot.close()
        print("✅ Сессия закрыта")
    except Exception as e:
        print(f"⚠️ close: {e}")


if __name__ == "__main__":
    from aiogram import executor
    print(f"🚀 Бот запускается... VERSION: {BOT_VERSION}")
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            executor.start_polling(
                dp,
                skip_updates=True,
                allowed_updates=['message', 'callback_query', 'channel_post'],
                on_startup=on_startup,
                on_shutdown=on_shutdown,
            )
            break
        except TerminatedByOtherGetUpdates:
            print(f"⚠️ Конфликт getUpdates ({attempt}/{max_attempts}), ждём 5 сек...")
            import time
            time.sleep(5)
        except Exception as e:
            print(f"❌ Ошибка запуска: {e}")
            break
