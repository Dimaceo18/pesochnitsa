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
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import textwrap
import hashlib

# ========== КОНФИГ ==========
BOT_VERSION = "video-stories-v13-polling-webservice-20261123"

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

# Готовые сторис отправляются только в личный чат ADMIN_CHAT_ID.
# STORY_CHANNEL_ID намеренно не используется.
# Необязательно: обрабатывать только один исходный канал.
STORY_SOURCE_CHANNEL_ID = os.getenv("STORY_SOURCE_CHANNEL_ID", "").strip()
AUTO_STORY_MARKER = "🎞 Автосторис"

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

# Резерв снизу под ссылку (10% высоты — только фон)
I_TEXT_BOTTOM_RESERVE_PCT = 0.10

# Порог минимального шрифта заголовка, при котором ещё пытаемся уложить в 3 строки
I_TITLE_THREE_LINE_MIN_SIZE = 40
# Максимальная высота блока заголовка (плашки)
I_TITLE_BLOCK_MAX_H = 300

RUBRICS = ["НОВОСТИ", "АФИША", "СПОРТ", "ФИНАНСЫ", "АВТО", "НЕДВИЖИМОСТЬ"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

class IncomingUpdateLogger(BaseMiddleware):
    async def on_pre_process_update(self, update, data):
        kind = "message" if update.message else "channel_post" if update.channel_post else "callback_query" if update.callback_query else "other"
        logging.info("📨 TELEGRAM UPDATE RECEIVED: id=%s type=%s", update.update_id, kind)

dp.middleware.setup(IncomingUpdateLogger())

VIDEO_MAX_DURATION = 60


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


LIST_ITEM_RE = re.compile(
    r'^\s*(?:'
    r'\d{1,3}[.)]\s+'
    r'|[•●○◦▪▫■□►▶➤➢✓✔]\s+'
    r'|[-–—*]\s+'
    r')'
)


def is_list_item(line: str) -> bool:
    return bool(LIST_ITEM_RE.match(line))


def normalize_lists(text: str) -> str:
    if not text:
        return text
    lines = text.split('\n')
    out = []
    prev_was_list = False
    pending_blank = 0

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            pending_blank += 1
            continue

        cur_is_list = is_list_item(stripped)

        if pending_blank > 0:
            if prev_was_list and cur_is_list:
                pass
            else:
                if out:
                    out.append('')
            pending_blank = 0

        out.append(line)
        prev_was_list = cur_is_list

    return '\n'.join(out).strip()


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
            logging.debug(f"Фото отсутствует в макете видео: {e}") if transparent_top else logging.error(f"❌ Фото: {e}")
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
    # Основной текст классик-шаблона всегда меньше заголовка (минимум на 2pt)
    classic_text_max = max(20, title_font_size - 2)
    classic_text_start = min(42, classic_text_max)
    for size in range(classic_text_start, 19, -2):
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
    out = f"output_story_classic_{theme}_{os.getpid()}_{__import__('uuid').uuid4().hex}.png"
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


def split_content_blocks(content: str):
    if not content or content == "Текст отсутствует":
        return [("para", ["Текст отсутствует"])]

    blocks = []
    cur_kind = None
    cur_lines = []

    for raw in content.split('\n'):
        line = raw.rstrip()
        if not line.strip():
            if cur_lines:
                blocks.append((cur_kind, cur_lines))
                cur_lines = []
                cur_kind = None
            continue

        stripped = line.strip()
        is_list = is_list_item(stripped)
        kind = "list" if is_list else "para"

        if cur_kind is None:
            cur_kind = kind
            cur_lines = [stripped]
        elif kind == cur_kind:
            cur_lines.append(stripped)
        else:
            blocks.append((cur_kind, cur_lines))
            cur_kind = kind
            cur_lines = [stripped]

    if cur_lines:
        blocks.append((cur_kind, cur_lines))

    return blocks


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

    # ========== 1) Пытаемся уложить заголовок в 3 строки ==========
    title_font_size, title_lines = None, []
    for size in range(I_TITLE_FONT_MAX, I_TITLE_THREE_LINE_MIN_SIZE - 1, -1):
        tf = load_font(size, 'black')
        lines = wrap_title_by_width(draw, title, tf, max_width - 2 * I_TITLE_PLATE_PAD_X)
        lb = draw.textbbox((0, 0), "A", font=tf)
        lh = lb[3] - lb[1]
        plate_h = lh + 2 * I_TITLE_PLATE_PAD_Y
        total_h = len(lines) * plate_h + (len(lines) - 1) * I_TITLE_LINE_GAP
        if len(lines) <= 3 and total_h <= I_TITLE_BLOCK_MAX_H:
            title_font_size, title_lines = size, lines
            break

    # ========== 2) Если в 3 строки не влезло — разрешаем 4 строки ==========
    if not title_lines:
        for size in range(I_TITLE_FONT_MAX, I_TITLE_FONT_MIN - 1, -1):
            tf = load_font(size, 'black')
            lines = wrap_title_by_width(draw, title, tf, max_width - 2 * I_TITLE_PLATE_PAD_X)
            lb = draw.textbbox((0, 0), "A", font=tf)
            lh = lb[3] - lb[1]
            plate_h = lh + 2 * I_TITLE_PLATE_PAD_Y
            total_h = len(lines) * plate_h + (len(lines) - 1) * I_TITLE_LINE_GAP
            if len(lines) <= 4 and total_h <= I_TITLE_BLOCK_MAX_H:
                title_font_size, title_lines = size, lines
                break

    # ========== 3) Фолбэк — минимальный шрифт ==========
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

    # ========== Основной текст с резервом 10% снизу под ссылку ==========
    text_y = cur_y + I_TEXT_TOP_GAP
    bottom_reserve = int(IH * I_TEXT_BOTTOM_RESERVE_PCT)
    available_h = IH - text_y - bottom_reserve
    if available_h < 60:
        available_h = 60
    text_line_max_width = max_plate_w - 4

    blocks = split_content_blocks(content)

    def measure_blocks(tf, sh):
        total = 0
        tmp = []
        for kind, raw_lines in blocks:
            if kind == "list":
                wrapped = []
                for i, ln in enumerate(raw_lines):
                    ls = wrap_text_strict(draw, ln.upper(), tf, text_line_max_width)
                    wrapped.append(ls)
                    total += len(ls) * (sh + I_TEXT_LINE_GAP)
                    if i < len(raw_lines) - 1:
                        total += I_TEXT_LINE_GAP
                tmp.append(("list", wrapped))
                total += I_TEXT_PARA_GAP
            else:
                wrapped = []
                for ln in raw_lines:
                    ls = wrap_text_strict(draw, ln.upper(), tf, text_line_max_width)
                    wrapped.append(ls)
                    total += len(ls) * (sh + I_TEXT_LINE_GAP)
                tmp.append(("para", wrapped))
                total += I_TEXT_PARA_GAP
        return total, tmp

    # Заголовок всегда должен быть крупнее основного текста:
    # ограничиваем верхнюю границу шрифта текста так,
    # чтобы он был минимум на 2pt меньше заголовка.
    text_font_max_allowed = max(I_TEXT_FONT_MIN, title_font_size - 2)
    text_font_start = min(I_TEXT_FONT_MAX, text_font_max_allowed)

    text_font_size, wrapped_blocks = text_font_start, []
    for size in range(text_font_start, I_TEXT_FONT_MIN - 1, -1):
        tf = load_font(size, 'bold_text')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        total_h, tmp = measure_blocks(tf, sh)
        if total_h <= available_h:
            text_font_size, wrapped_blocks = size, tmp
            break
    if not wrapped_blocks:
        tf = load_font(I_TEXT_FONT_MIN, 'bold_text')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        _, wrapped_blocks = measure_blocks(tf, sh)
        text_font_size = I_TEXT_FONT_MIN

    text_font = load_font(text_font_size, 'bold_text')
    sb = draw.textbbox((0, 0), "A", font=text_font)
    sh = sb[3] - sb[1]
    pos_y = text_y

    for kind, wrapped in wrapped_blocks:
        if kind == "list":
            for i, ls in enumerate(wrapped):
                for line in ls:
                    draw.text((I_MARGIN_X, pos_y), line, font=text_font, fill=text_color)
                    pos_y += sh + I_TEXT_LINE_GAP
                if i < len(wrapped) - 1:
                    pos_y += I_TEXT_LINE_GAP
            pos_y += I_TEXT_PARA_GAP
        else:
            for ls in wrapped:
                for line in ls:
                    draw.text((I_MARGIN_X, pos_y), line, font=text_font, fill=text_color)
                    pos_y += sh + I_TEXT_LINE_GAP
            pos_y += I_TEXT_PARA_GAP

    out = f"output_story_insta_{theme}_{os.getpid()}_{__import__('uuid').uuid4().hex}.png"
    canvas.save(out, format='PNG')
    return out


# ========== ВИДЕО-СТОРИС ==========
def generate_video_story(video_path, title, content, rubric, highlight_words, theme, out_path, template="classic"):
    """MP4: исходный шаблон без изменений, видео только вместо фото."""
    import tempfile
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg не установлен. Добавьте его в Dockerfile.")
    if template not in ("classic", "insta"):
        raise ValueError("Неизвестный шаблон: " + str(template))

    with tempfile.TemporaryDirectory(prefix="story_video_") as td:
        base_path = os.path.join(td, "layout.png")
        if template == "insta":
            # Вызываем ИСХОДНЫЙ генератор: все плашки, отступы, шрифты
            # и расположение текста идентичны фото-сторис.
            import asyncio as _asyncio
            # Подставляем техническое изображение вместо None, чтобы
            # исходный генератор не сообщал об ошибке фотографии.
            placeholder_path = os.path.join(td, "placeholder.png")
            Image.new("RGB", (I_PHOTO_WIDTH, I_PHOTO_HEIGHT), "#111111").save(placeholder_path)
            original_path = _asyncio.run(generate_story_insta(placeholder_path, title, content, theme))
            try:
                with Image.open(original_path) as im:
                    overlay = im.convert("RGBA")
            finally:
                if os.path.exists(original_path):
                    os.remove(original_path)
            vw, vh, top = I_PHOTO_WIDTH, I_PHOTO_HEIGHT, I_PHOTO_TOP
        else:
            overlay = render_base_canvas(
                title, content, rubric, highlight_words, theme,
                photo_path=None, transparent_top=True
            )
            vw, vh, top = PHOTO_WIDTH, PHOTO_HEIGHT, PHOTO_TOP

        # Делаем прозрачной только зону исходной фотографии.
        overlay.paste((0, 0, 0, 0), (0, top, vw, top + vh))
        overlay.save(base_path, "PNG")

        # Первый вход: исходное видео; второй: неподвижный макет.
        # overlay=shortest=1 завершает результат вместе с видео.
        filters = (
            f"[0:v]trim=duration={VIDEO_MAX_DURATION},setpts=PTS-STARTPTS,"
            f"scale={vw}:{vh}:force_original_aspect_ratio=increase,"
            f"crop={vw}:{vh},setsar=1,fps=30,format=yuva420p[clip];"
            f"[1:v][clip]overlay=0:{top}:shortest=1:format=auto,"
            f"format=yuv420p[outv]"
        )
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", video_path,
            "-loop", "1", "-framerate", "30", "-i", base_path,
            "-filter_complex", filters,
            "-map", "[outv]", "-map", "0:a?",
            "-t", str(VIDEO_MAX_DURATION),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("Ошибка FFmpeg: " + result.stderr[-1500:])
        if not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
            raise RuntimeError("FFmpeg не создал итоговый MP4")
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
    text = normalize_lists('\n'.join(clean))

    if text:
        title, content = parse_text(text)
        if not title:
            sentences = re.split(r'(?<=[.!?])\s+', text.strip())
            title = sentences[0] if sentences else "ЗАГОЛОВОК"
            content = ". ".join(sentences[1:]) if len(sentences) > 1 else "Текст отсутствует"
        if not content:
            content = "Текст отсутствует"
        content = normalize_lists(content)

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
        content = normalize_lists(remove_emojis(message.text))
        user_data[user_id]["content"] = content
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
        await bot.send_message(user_id, "⏳ Обрабатываю видео (до 60 сек) — это займёт немного времени...")
        out_path = f"output_video_{user_id}.mp4"
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                generate_video_story,
                photo_path, title, content, rubric, highlight_words, theme, out_path, template
            )
            logging.info(f"📤 Отправляю видео: {out_path}")
            with open(out_path, 'rb') as f:
                await bot.send_video(
                    chat_id=user_id,
                    video=f,
                                        caption=f"✅ Готово! ({'🌙' if theme == 'dark' else '☀️'} · {rubric or 'без рубрики'})"
                )
            with open(out_path, 'rb') as f:
                await bot.send_document(chat_id=user_id, document=f,
                                        caption="📥 Скачать готовую сторис MP4",
                                        filename=f"story_{user_id}.mp4")
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


# ========== АВТОМАТИЧЕСКАЯ СТОРИС ИЗ ПОСТА КАНАЛА ==========
@dp.channel_post_handler(content_types=['photo', 'document', 'video', 'text'])
async def handle_channel_post(message: types.Message):
    source_id = message.chat.id
    if STORY_SOURCE_CHANNEL_ID and str(source_id) != STORY_SOURCE_CHANNEL_ID and (message.chat.username or "").lower() != STORY_SOURCE_CHANNEL_ID.lstrip("@").lower():
        return

    # Не обрабатываем собственные сторис повторно, даже если бот публикует
    # результат в том же исходном канале.
    if message.from_user and message.from_user.is_bot:
        me = await bot.get_me()
        if message.from_user.id == me.id:
            return
    if message.sender_chat and message.sender_chat.id == source_id:
        # У обычных постов sender_chat тоже совпадает с каналом, поэтому
        # ориентируемся на метку в подписи, а не на sender_chat.
        pass
    raw_text = message.text or message.caption or ""
    if raw_text.startswith(AUTO_STORY_MARKER) or not raw_text.strip():
        return

    media_path = None
    is_video = False
    output_path = None
    if not ADMIN_CHAT_ID:
        logging.error("Для автосторис необходимо указать ADMIN_CHAT_ID в Render")
        return
    destination = ADMIN_CHAT_ID
    chat_title = message.chat.title or str(source_id)
    try:
        if message.photo:
            media = message.photo[-1]
            suffix = ".jpg"
        elif message.video:
            media = message.video
            suffix = ".mp4"
            is_video = True
        elif message.document and (message.document.mime_type or "").startswith(("image/", "video/")):
            media = message.document
            is_video = message.document.mime_type.startswith("video/")
            suffix = ".mp4" if is_video else ".jpg"
        else:
            logging.info("⏭ Пост без фото или видео: %s/%s", source_id, message.message_id)
            return

        # Уникальные имена исключают пересечение файлов при параллельных постах.
        key = f"{abs(source_id)}_{message.message_id}"
        media_path = f"source_story_{key}{suffix}"
        f = await bot.get_file(media.file_id)
        await bot.download_file(f.file_path, media_path)

        text = raw_text.replace("**Текст отсутствует**", "").strip()
        lines = text.split("\n")
        clean = [line.strip() for line in lines
                 if line.strip() and not line.strip().startswith(("Подписаться", "@", "#"))]
        text = normalize_lists(remove_emojis("\n".join(clean)))
        if not text:
            return
        title, content = parse_text(text)
        title = title or "ЗАГОЛОВОК НОВОСТИ"
        content = normalize_lists(content or "Текст отсутствует")

        # Единый автоматический стиль: Инста-дизайн, тёмный фон.
        if is_video:
            output_path = f"story_{key}.mp4"
            await asyncio.to_thread(
                generate_video_story, media_path, title, content,
                None, [], "dark", output_path, "insta"
            )
            with open(output_path, "rb") as video_file:
                await bot.send_video(
                    chat_id=destination,
                    video=video_file,
                    caption=f"{AUTO_STORY_MARKER} | {title[:140]}",
                    supports_streaming=True,
                )
        else:
            # Статический генератор использует общий файл результата;
            # копируем его в уникальный файл до отправки.
            import shutil
            generated = await generate_story_insta(media_path, title, content, theme="dark")
            output_path = f"story_{key}.png"
            shutil.copyfile(generated, output_path)
            if os.path.exists(generated):
                os.remove(generated)
            with open(output_path, "rb") as photo_file:
                await bot.send_photo(
                    chat_id=destination,
                    photo=photo_file,
                    caption=f"{AUTO_STORY_MARKER} | {title[:140]}",
                )

        logging.info("✅ Сторис из %s/%s отправлена администратору %s", source_id, message.message_id, destination)
        # Дополнительно отправляем MP4 документом, чтобы можно было скачать
        # исходный файл без повторного сжатия Telegram.
        if is_video:
            try:
                with open(output_path, "rb") as video_file:
                    await bot.send_document(
                        chat_id=ADMIN_CHAT_ID,
                        document=video_file,
                        caption=f"📥 MP4-сторис из канала «{chat_title}»",
                    )
            except Exception:
                logging.exception("Не удалось отправить MP4 документом администратору")
    except Exception as e:
        logging.exception("❌ Ошибка автоматической публикации сторис")
        if ADMIN_CHAT_ID:
            try:
                await bot.send_message(ADMIN_CHAT_ID, f"❌ Ошибка сторис для «{chat_title}»: {str(e)[:800]}")
            except Exception:
                logging.exception("Не удалось уведомить администратора")
    finally:
        for path in (media_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    logging.warning("Не удалось удалить временный файл %s", path)


# ========== POLLING + HTTP HEALTH ДЛЯ RENDER WEB SERVICE ==========
# Никаких set_webhook: Telegram updates принимаются только через getUpdates.
# WEBHOOK_URL можно удалить из Environment: в этом режиме она не используется.
from aiohttp import web

WEBHOOK_HOST = "0.0.0.0"
WEBHOOK_PORT = int(os.getenv("PORT", "10000"))


async def health(request):
    return web.json_response({
        "status": "ok",
        "version": BOT_VERSION,
        "mode": "polling",
    })


async def polling_worker(app):
    # Даём HTTP-серверу запуститься до подключения Telegram.
    await asyncio.sleep(2)
    while True:
        try:
            # Важно: удалить webhook ПЕРЕД первым getUpdates.
            await bot.delete_webhook(drop_pending_updates=False)
            info = await bot.get_webhook_info()
            if info.url:
                logging.error("❌ Webhook всё ещё активен; повторная попытка через 10 секунд")
                await asyncio.sleep(10)
                continue
            logging.info("✅ Webhook удалён, запускаю polling")
            # reset_webhook=False: мы уже удалили webhook и сохранили очередь.
            await dp.start_polling(
                reset_webhook=False,
                timeout=25,
                relax=1,
                error_sleep=10,
                allowed_updates=["message", "callback_query", "channel_post"],
            )
            logging.warning("⚠️ Polling завершился; повторный запуск через 10 секунд")
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("❌ Ошибка polling. Повтор через 10 секунд")
        await asyncio.sleep(10)


async def app_startup(app):
    me = await bot.get_me()
    logging.info("🚀 START %s: POLLING + WEB SERVICE, PORT=%s", BOT_VERSION, WEBHOOK_PORT)
    logging.info("🤖 Бот: @%s", me.username)
    logging.info("📥 ADMIN_CHAT_ID: %s", ADMIN_CHAT_ID or "НЕ ЗАДАН")
    logging.info("📡 Источник: %s", STORY_SOURCE_CHANNEL_ID or "все каналы, где бот администратор")
    # Запускаем polling в том же event loop, не блокируя HTTP health endpoint.
    app["polling_task"] = asyncio.create_task(polling_worker(app))


async def app_shutdown(app):
    task = app.get("polling_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    # При rolling deploy не удаляем webhook: новый экземпляр сам управляет им.
    await (await bot.get_session()).close()


def create_app():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.on_startup.append(app_startup)
    app.on_shutdown.append(app_shutdown)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host=WEBHOOK_HOST, port=WEBHOOK_PORT, print=None)
