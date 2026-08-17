import os
import io
import logging
import sys
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Выводим версию Python при запуске
print(f"Python version: {sys.version}")
print(f"Python path: {sys.executable}")

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    logger.error("BOT_TOKEN не найден в переменных окружения!")
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    print("Проверьте переменные окружения на Render")
    sys.exit(1)

# Временная папка
TEMP_DIR = "temp_images"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
    logger.info(f"Создана папка {TEMP_DIR}")

# Параметры сторис
STORY_WIDTH = 1080
STORY_HEIGHT = 1920
BACKGROUND_COLOR = (0, 0, 0)
MARGIN = 60
IMAGE_HEIGHT_RATIO = 0.55

def download_image(url, filename):
    """Скачивает изображение по URL"""
    try:
        if url.startswith('file://'):
            import shutil
            file_path = url[7:]
            shutil.copy(file_path, filename)
            return True
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
    return False

def wrap_text(text, font, max_width, draw):
    """Разбивает текст на строки"""
    if not text:
        return []
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except:
            width = len(test_line) * 20
            
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

def get_font(font_size, bold=False):
    """Загружает шрифт с обработкой ошибок"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "arial.ttf",
        "Arial.ttf"
    ]
    
    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
            "arialbd.ttf",
            "Arialbd.ttf"
        ]
    
    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, font_size)
            logger.info(f"Загружен шрифт: {font_path}")
            return font
        except:
            continue
    
    logger.warning("Шрифты не найдены, используем стандартный")
    return ImageFont.load_default()

def create_story_image(image_path, title, text):
    """Создает изображение сторис"""
    logger.info("Начинаем создание сторис")
    
    # Создаем фон
    story = Image.new('RGB', (STORY_WIDTH, STORY_HEIGHT), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(story)
    
    # Загружаем и обрабатываем фотографию
    try:
        user_img = Image.open(image_path)
        user_img = user_img.convert('RGB')
        
        img_width = STORY_WIDTH - 2 * MARGIN
        img_height = int(STORY_HEIGHT * IMAGE_HEIGHT_RATIO)
        
        img_ratio = user_img.width / user_img.height
        target_ratio = img_width / img_height
        
        if img_ratio > target_ratio:
            new_width = int(img_height * img_ratio)
            user_img = user_img.resize((new_width, img_height), Image.Resampling.LANCZOS)
            left = (new_width - img_width) // 2
            user_img = user_img.crop((left, 0, left + img_width, img_height))
        else:
            new_height = int(img_width / img_ratio)
            user_img = user_img.resize((img_width, new_height), Image.Resampling.LANCZOS)
            top = (new_height - img_height) // 2
            user_img = user_img.crop((0, top, img_width, top + img_height))
        
        story.paste(user_img, (MARGIN, MARGIN))
        logger.info("Фото обработано и вставлено")
        
    except Exception as e:
        logger.error(f"Ошибка обработки изображения: {e}")
        return None
    
    # Создаем эллипс для заголовка
    ellipse_y_start = MARGIN + int(STORY_HEIGHT * IMAGE_HEIGHT_RATIO) + 20
    ellipse_height = 120
    ellipse_y_end = ellipse_y_start + ellipse_height
    
    ellipse_layer = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (255, 255, 255, 0))
    ellipse_draw = ImageDraw.Draw(ellipse_layer)
    ellipse_draw.ellipse([MARGIN, ellipse_y_start, STORY_WIDTH - MARGIN, ellipse_y_end], fill=(255, 255, 255, 200))
    
    story = story.convert('RGBA')
    story = Image.alpha_composite(story, ellipse_layer)
    story = story.convert('RGB')
    draw = ImageDraw.Draw(story)
    
    # Загружаем шрифты
    title_font = get_font(44, bold=True)
    text_font = get_font(32, bold=False)
    
    # Рисуем заголовок
    title_y = ellipse_y_start + 20
    title_lines = wrap_text(title, title_font, STORY_WIDTH - 2 * MARGIN - 40, draw)
    if len(title_lines) > 3:
        title_lines = title_lines[:3]
    
    for i, line in enumerate(title_lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(line) * 25
        x = (STORY_WIDTH - text_width) // 2
        y = title_y + i * 55
        draw.text((x, y), line, fill=(0, 0, 0), font=title_font)
    
    # Рисуем основной текст
    text_start_y = ellipse_y_end + 10
    
    # Подбираем размер шрифта
    max_text_lines = 6
    test_font_size = 32
    
    while test_font_size > 18:
        try:
            test_font = get_font(test_font_size, bold=False)
            test_lines = wrap_text(text, test_font, STORY_WIDTH - 2 * MARGIN, draw)
            if len(test_lines) <= max_text_lines:
                break
        except:
            test_lines = [text[:50]]
            break
        test_font_size -= 2
    
    if len(test_lines) > max_text_lines:
        test_lines = test_lines[:max_text_lines]
        test_lines[-1] = test_lines[-1] + "..."
    
    # Рисуем текст
    text_y = text_start_y
    for line in test_lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=test_font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(line) * 15
        x = (STORY_WIDTH - text_width) // 2
        draw.text((x, text_y), line, fill=(255, 255, 255), font=test_font)
        text_y += test_font_size + 10
    
    logger.info("Сторис успешно создана")
    return story

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я помогу создать стильные сторис для Instagram.\n\n"
        "📸 Отправь мне фото, а затем текст для сторис.\n"
        "✏️ Заголовком будет первая часть текста (первые 2-3 строки)\n"
        "📝 Остальной текст пойдет ниже\n\n"
        "🚀 Бот автоматически подгонит размер текста!"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    context.user_data['photo_file_id'] = file.file_id
    
    await update.message.reply_text(
        "✅ Фото получено!\n"
        "Теперь отправьте текст для сторис.\n\n"
        "📝 Первые 2-3 строки будут заголовком в белом эллипсе."
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document.mime_type and document.mime_type.startswith('image/'):
        file = await document.get_file()
        context.user_data['photo_file_id'] = file.file_id
        await update.message.reply_text(
            "✅ Изображение получено!\n"
            "Теперь отправьте текст для сторис."
        )
    else:
        await update.message.reply_text("❌ Пожалуйста, отправьте изображение.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    if 'photo_file_id' not in context.user_data:
        await update.message.reply_text(
            "❌ Сначала отправьте фото!\n"
            "Отправьте изображение, а затем текст."
        )
        return
    
    try:
        file = await context.bot.get_file(context.user_data['photo_file_id'])
        file_path = os.path.join(TEMP_DIR, f"photo_{user.id}_{update.message.message_id}.jpg")
        await file.download_to_drive(file_path)
        
        await update.message.reply_text("🔄 Создаю сторис... Подождите немного.")
        
        # Разделяем текст
        lines = text.split('\n')
        if len(lines) >= 3:
            title = '\n'.join(lines[:3])
            body_text = '\n'.join(lines[3:])
        elif len(lines) >= 2:
            title = '\n'.join(lines[:2])
            body_text = '\n'.join(lines[2:])
        else:
            title = lines[0] if lines else " "
            body_text = ""
        
        if not body_text.strip():
            body_text = " "
        
        story_image = create_story_image(file_path, title, body_text)
        
        if os.path.exists(file_path):
            os.remove(file_path)
        context.user_data.pop('photo_file_id', None)
        
        if story_image:
            output_path = os.path.join(TEMP_DIR, f"story_{user.id}_{update.message.message_id}.jpg")
            story_image.save(output_path, "JPEG", quality=95)
            
            with open(output_path, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="✅ Ваша сторис готова!\n💾 Сохраните и публикуйте в Instagram."
                )
            
            if os.path.exists(output_path):
                os.remove(output_path)
        else:
            await update.message.reply_text("❌ Произошла ошибка при создании сторис. Попробуйте еще раз.")
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Как пользоваться ботом:\n\n"
        "1️⃣ Отправьте фото\n"
        "2️⃣ Отправьте текст\n"
        "3️⃣ Получите готовую сторис\n\n"
        "📝 Первые 2-3 строки текста станут заголовком в белом эллипсе\n"
        "🔽 Остальной текст будет ниже\n"
        "📏 Бот автоматически подгонит размер текста\n\n"
        "Команды:\n"
        "/start - Начать\n"
        "/help - Помощь"
    )

def main():
    logger.info("🚀 Запуск бота...")
    logger.info(f"📁 Текущая директория: {os.getcwd()}")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("✅ Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
