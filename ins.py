import instaloader
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes
from telegram.ext import filters
import os
import logging
import shutil
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or "7550884236:AAF0741O4sayt4E5VVfb2eHzF4LdGS6pFHo"

# Максимальный размер файла (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Инициализация Instaloader
try:
    L = instaloader.Instaloader()
    logger.info("Instaloader успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка при инициализации Instaloader: {e}")
    exit(1)

# Хранилище постов
user_data = {}

def cleanup_temp_files(directory):
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
            logger.info(f"Удалена временная директория: {directory}")
    except Exception as e:
        logger.error(f"Ошибка при удалении временной директории {directory}: {e}")

def create_temp_directory(directory):
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании директории {directory}: {e}")
        return False

def check_file_size(file_path):
    try:
        return os.path.getsize(file_path) <= MAX_FILE_SIZE
    except Exception as e:
        logger.error(f"Ошибка при проверке размера файла {file_path}: {e}")
        return False

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне ссылку на пост или сторис из Instagram, и я скачаю его для тебя.")

# Обработка ссылок
async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    url = update.message.text.strip()

    temp_dir_stories = f"{chat_id}_stories"
    temp_dir_post = f"{chat_id}_post"

    try:
        if "instagram.com" not in url:
            await update.message.reply_text("Пожалуйста, отправь корректную ссылку на Instagram.")
            return

        await update.message.reply_text("Обрабатываю ссылку...")
        logger.info(f"Получена ссылка: {url}")

        if "/stories/" in url:
            username = url.split("/stories/")[1].split("/")[0]
            logger.info(f"Username: {username}")

            if not create_temp_directory(temp_dir_stories):
                await update.message.reply_text("Ошибка при создании временной директории.")
                return

            try:
                profile = instaloader.Profile.from_username(L.context, username)
            except instaloader.exceptions.ProfileNotExistsException:
                await update.message.reply_text("Профиль не существует.")
                cleanup_temp_files(temp_dir_stories)
                return
            except instaloader.exceptions.ConnectionException:
                await update.message.reply_text("Ошибка подключения к Instagram.")
                cleanup_temp_files(temp_dir_stories)
                return

            story_items = []
            for story in L.get_stories([profile.userid]):
                for item in story.get_items():
                    story_items.append(item)

            if story_items:
                await update.message.reply_text("Скачиваю сторис...")
                success_count = 0
                for item in story_items:
                    try:
                        date_str = item.date_utc.strftime('%Y-%m-%d_%H-%M-%S')
                        L.download_storyitem(item, target=temp_dir_stories)

                        file_path = f"{temp_dir_stories}/{date_str}.mp4" if item.is_video else f"{temp_dir_stories}/{date_str}.jpg"

                        if os.path.exists(file_path) and check_file_size(file_path):
                            with open(file_path, 'rb') as file:
                                if item.is_video:
                                    await context.bot.send_video(chat_id, file)
                                else:
                                    await context.bot.send_photo(chat_id, file)
                            success_count += 1
                        elif os.path.exists(file_path):
                            await update.message.reply_text(f"Файл слишком большой: {os.path.basename(file_path)}")
                    except Exception as e:
                        logger.error(f"Ошибка при скачивании сторис: {e}")

                if success_count == 0:
                    await update.message.reply_text("Не удалось скачать сторис.")
                else:
                    await update.message.reply_text(f"Скачано и отправлено {success_count} сторис.")
            else:
                await update.message.reply_text("Сторис не найдены или они приватные.")
            cleanup_temp_files(temp_dir_stories)

        else:
            try:
                if "/p/" in url:
                    shortcode = url.split("/p/")[1].split("/")[0]
                elif "/reel/" in url:
                    shortcode = url.split("/reel/")[1].split("/")[0]
                else:
                    shortcode = url.split("/")[-2]

                logger.info(f"Shortcode: {shortcode}")

                if not create_temp_directory(temp_dir_post):
                    await update.message.reply_text("Ошибка при создании временной директории.")
                    return

                post = instaloader.Post.from_shortcode(L.context, shortcode)

                if post.is_video:
                    await update.message.reply_text("Скачиваю видео...")
                    L.download_post(post, target=temp_dir_post)
                    video_files = [f for f in os.listdir(temp_dir_post) if f.endswith('.mp4')]
                    if video_files:
                        file_path = os.path.join(temp_dir_post, video_files[0])
                        if check_file_size(file_path):
                            with open(file_path, 'rb') as file:
                                await context.bot.send_video(chat_id, file)
                            await update.message.reply_text("Видео отправлено!")
                        else:
                            await update.message.reply_text("Видео слишком большое.")
                    else:
                        await update.message.reply_text("Видео не найдено.")
                else:
                    await update.message.reply_text("Скачиваю фото...")
                    L.download_post(post, target=temp_dir_post)
                    jpg_files = [f for f in os.listdir(temp_dir_post) if f.endswith('.jpg')]
                    if jpg_files:
                        file_path = os.path.join(temp_dir_post, jpg_files[0])
                        if check_file_size(file_path):
                            with open(file_path, 'rb') as file:
                                await context.bot.send_photo(chat_id, file)
                            await update.message.reply_text("Фото отправлено!")
                        else:
                            await update.message.reply_text("Фото слишком большое.")
                    else:
                        await update.message.reply_text("Фото не найдено.")

                cleanup_temp_files(temp_dir_post)

            except instaloader.exceptions.ProfileNotExistsException:
                await update.message.reply_text("Профиль не существует.")
                cleanup_temp_files(temp_dir_post)
            except instaloader.exceptions.PostNotExistsException:
                await update.message.reply_text("Пост не существует или удалён.")
                cleanup_temp_files(temp_dir_post)
            except Exception as e:
                logger.error(f"Ошибка при обработке поста: {e}")
                await update.message.reply_text(f"Ошибка: {str(e)}")
                cleanup_temp_files(temp_dir_post)

    except instaloader.exceptions.PrivateProfileNotFollowedException:
        await update.message.reply_text("Контент приватный. Доступ только к публичным постам.")
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")
        await update.message.reply_text(f"Ошибка: {str(e)}")
        cleanup_temp_files(temp_dir_stories)
        cleanup_temp_files(temp_dir_post)

# Запуск бота
def main():
    try:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
        logger.info("Бот запущен")
        app.run_polling(poll_interval=1.0)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        exit(1)

if __name__ == "__main__":
    main()
