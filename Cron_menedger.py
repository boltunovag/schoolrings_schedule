import os
import telebot
from telebot import types
import time
from dotenv import load_dotenv

# --- Настройки ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

AUDIO_DIR = "audio_files"
CRON_FILE = "audio_schedule.cron"
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- Класс для событий ---
class LessonEvent:
    def __init__(self, lesson_num, event_type, time, audio_file):
        self.lesson_num = lesson_num
        self.event_type = event_type  # 'start' или 'end'
        self.time = time  # 'hh:mm'
        self.audio_file = audio_file  # имя файла

# --- Работа с cron ---
def generate_cron_content(events):
    """Генерирует содержимое cron-файла"""
    content = "# Аудио расписание\n\n"
    for event in events:
        if event.event_type == "start":
            hour, minute = event.time.split(':')
            audio_path = os.path.join(AUDIO_DIR, event.audio_file)
            content += f"{minute} {hour} * * 1-5 /usr/bin/mpg123 '{audio_path}' >/dev/null 2>&1\n"
    return content

def install_cron_jobs(events):
    """Устанавливает задания в crontab"""
    try:
        # 1. Генерируем временный файл
        cron_content = generate_cron_content(events)
        with open(CRON_FILE, 'w') as f:
            f.write(cron_content)
        
        # 2. Устанавливаем crontab
        os.system(f"crontab {CRON_FILE}")
        
        # 3. Проверяем успешность
        exit_code = os.system("crontab -l > /dev/null 2>&1")
        return exit_code == 0
        
    except Exception as e:
        print(f"Cron error: {str(e)}")
        return False

# --- Команды бота ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "📅 Бот для расписания аудиоуроков\n\n"
        "Доступные команды:\n"
        "/add_lesson - добавить урок\n"
        "/show_schedule - показать расписание\n"
        "/install_cron - установить cron-задания"
    )

@bot.message_handler(commands=['install_cron'])
def handle_install_cron(message):
    events = load_events()  # Ваша функция загрузки событий
    if not events:
        bot.send_message(message.chat.id, "❌ Нет событий для установки")
        return
    
    if install_cron_jobs(events):
        bot.send_message(message.chat.id, "✅ Cron-задания успешно установлены!")
        # Отправляем файл для проверки
        with open(CRON_FILE, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="Содержимое crontab")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка установки cron. Проверьте права.")

# --- Полный процесс добавления урока ---
# (Добавьте вашу реализацию сбора данных об уроке)
# После успешного добавления урока вызываем:
# install_cron_jobs(updated_events)

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()