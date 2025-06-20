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
SCHEDULE_FILE = "schedule.txt"
CRON_FILE = "audio_schedule.cron"
SETTINGS_FILE = "settings.json"          # Новый файл для настроек
CRON_BACKUP_FILE = "cron_backup.txt"     # Резервная копия cron
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- Класс для событий ---
class LessonEvent:
    def __init__(self, lesson_num, event_type, time, audio_file):
        self.lesson_num = lesson_num
        self.event_type = event_type  # 'start' или 'end'
        self.time = time  # 'hh:mm'
        self.audio_file = audio_file  # имя файла

import logging

logging.basicConfig(
    filename='bot_errors.log',
    level=logging.INFO,  # Изменил на INFO чтобы видеть больше событий
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'  # Добавляем в конец файла, а не перезаписываем
)

# --- Работа с расписанием ---

def load_events():
    """Загружает события из файла"""
    events = []
    if not os.path.exists(SCHEDULE_FILE):
        return events
        
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 4:
                    event_type, lesson_num, time, audio_file = parts
                    events.append(LessonEvent(lesson_num, event_type, time, audio_file))
    except Exception as e:
        print(f"Ошибка загрузки: {str(e)}")
    return events


def save_events(events):
    """Сохраняет события в файл, обновляя существующие уроки"""
    # Создаем словарь для хранения последних версий событий
    lesson_records = {}
    
    # Группируем события по номеру урока и типу
    for event in events:
        key = (event.lesson_num, event.event_type)
        lesson_records[key] = event
    
    # Записываем в файл, сохраняя порядок уроков
    with open(SCHEDULE_FILE, 'w') as f:
        # Сначала записываем все начала уроков
        for key in sorted(lesson_records.keys()):
            if key[1] == 'start':
                event = lesson_records[key]
                line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
                f.write(line)
        
        # Затем записываем все окончания уроков
        for key in sorted(lesson_records.keys()):
            if key[1] == 'end':
                event = lesson_records[key]
                line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
                f.write(line)


# --- Работа с настройками ---
def load_settings():
    """Загружает настройки из файла"""
    default_settings = {
        "lesson_duration": 45,  # по умолчанию 45 минут
        "cron_paused": False
    }
    try:
        with open(SETTINGS_FILE, 'r') as f:
            import json
            return {**default_settings, **json.load(f)}
    except:
        return default_settings

def save_settings(settings):
    """Сохраняет настройки в файл"""
    with open(SETTINGS_FILE, 'w') as f:
        import json
        json.dump(settings, f)
        
# --- Ненужная функция. Будет удалена
def clear_schedule():
    """Полностью очищает расписание"""
    try:
        if os.path.exists(SCHEDULE_FILE):
            os.remove(SCHEDULE_FILE)
        if os.path.exists(CRON_FILE):
            os.remove(CRON_FILE)
        os.system("crontab -r 2>/dev/null")
        return True
    except Exception as e:
        print(f"Ошибка очистки: {str(e)}")
        return False

# --- Работа с cron ---
def generate_cron_jobs(events):
    """Генерирует crontab с абсолютными путями"""
    if not os.path.exists(AUDIO_DIR):
        os.makedirs(AUDIO_DIR, exist_ok=True)
    
    # Получаем абсолютный путь к папке с аудио
    abs_audio_dir = os.path.abspath(AUDIO_DIR)
    cron_log = os.path.join(abs_audio_dir, 'cron.log')
    
    cron_content = "# Аудио расписание\n\n"
    cron_content += f"# Audio dir: {abs_audio_dir}\n\n"
    
    for event in sorted(events, key=lambda x: x.time):
        try:
            # Используем абсолютный путь к файлу
            audio_path = os.path.join(abs_audio_dir, event.audio_file)
            print(f"DEBUG: Audio path: {audio_path}")  # Для отладки
            
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file {audio_path} not found")
            
            hour, minute = event.time.split(':')
            cron_content += (
                f"{minute} {hour} * * 1-5 "
                f"/usr/bin/mpg123 '{audio_path}' "
                f">>{cron_log} 2>&1\n"
            )
        except Exception as e:
            print(f"Error processing event {event.lesson_num}: {str(e)}")
            continue
    
    return cron_content

def install_cron_jobs():
    """Устанавливает задания в crontab"""
    try:
        events = load_events()
        if not events:
            return False, "Нет событий для установки"
        
        cron_content = generate_cron_jobs(events)
        with open(CRON_FILE, 'w') as f:
            f.write(cron_content)
        
        exit_code = os.system(f"crontab {CRON_FILE}")
        return exit_code == 0, "Cron-задания успешно установлены!" if exit_code == 0 else "Ошибка установки crontab"
    except Exception as e:
        return False, f"Ошибка: {str(e)}"

# --- Команды бота ---

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton('/add_lesson'),
        types.KeyboardButton('/show_schedule'),
        types.KeyboardButton('/install_cron'),
        types.KeyboardButton('/clear'),
        types.KeyboardButton('/settings')  # Новая кнопка
    ]
    markup.add(*buttons)
    
    bot.send_message(
        message.chat.id,
        "📅 Бот для управления расписанием\n\n"
        "Доступные команды:\n"
        "/add_lesson - добавить урок\n"
        "/show_schedule - показать расписание\n"
        "/install_cron - установить cron\n"
        "/clear - очистить расписание\n"
        "/settings - настройки",
        reply_markup=markup
    )

@bot.message_handler(commands=['cancel'])
def cancel(message):
    start(message)

@bot.message_handler(commands=['show_schedule'])
def show_schedule(message):
    events = load_events()
    if not events:
        bot.send_message(message.chat.id, "Расписание пусто.")
        return
    
    response = "📅 Текущее расписание:\n\n"
    for event in events:
        response += f"Урок {event.lesson_num}: {'Начало' if event.event_type == 'start' else 'Конец'} в {event.time}\n"
    bot.send_message(message.chat.id, response)

_unused='''@bot.message_handler(commands=['clear'])
    if clear_schedule():
        bot.send_message(message.chat.id, "✅ Расписание и crontab очищены")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка при очистке")'''

@bot.message_handler(commands=['install_cron'])
def handle_install_cron(message):
    success, result = install_cron_jobs()
    if success:
        with open(CRON_FILE, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"✅ {result}"
            )
    else:
        bot.send_message(message.chat.id, f"❌ {result}")

# --- Добавление урока ---
@bot.message_handler(commands=['add_lesson'])
def add_lesson(message):
    msg = bot.send_message(message.chat.id, "Введите номер урока:")
    bot.register_next_step_handler(msg, process_lesson_number)

# В process_lesson_number:
def process_lesson_number(message):
    try:
        if not message.text:  # Добавляем проверку на наличие текста
            raise ValueError("Пожалуйста, введите номер урока")
            
        lesson_num = message.text.strip()
        if not lesson_num.isdigit():
            raise ValueError("Номер урока должен быть числом")
            
        msg = bot.send_message(message.chat.id, f"Урок {lesson_num}. Введите время начала (hh:mm):")
        bot.register_next_step_handler(msg, process_start_time, lesson_num)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)  # Возвращаем в начало

# В process_start_time и process_end_time:

def validate_time(time_str):
    try:
        hh, mm = map(int, time_str.split(':'))
        return 0 <= hh < 24 and 0 <= mm < 60
    except:
        return False
    


def process_start_time(message, lesson_num):
    try:
        if not message.text:  # Проверка наличия текста
            raise ValueError("Пожалуйста, введите время в формате hh:mm")
            
        start_time = message.text.strip()  # Получаем время из сообщения
        if not validate_time(start_time):
            raise ValueError("Некорректное время. Формат: HH:MM (00:00-23:59)")
            
        msg = bot.send_message(message.chat.id, "Отправьте аудиофайл для начала урока:")
        bot.register_next_step_handler(msg, process_start_audio, lesson_num, start_time)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        add_lesson(message)  # Возврат к вводу номера урока


# В process_start_audio и process_end_audio:

def process_start_audio(message, lesson_num, start_time):
    try:
        os.makedirs(AUDIO_DIR, exist_ok=True)

        if not (message.audio or message.voice or message.text):
            raise ValueError("Пожалуйста, отправьте аудиофайл или введите /cancel для отмены")

        if message.text and message.text.strip().lower() == '/cancel':
            return start(message)

        if not (message.audio or message.voice):
            raise ValueError("Пожалуйста, отправьте именно аудиофайл")

        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_ext = "ogg" if message.voice else message.audio.file_name.split('.')[-1]
        file_name = f"lesson_{lesson_num}_start_{int(time.time())}.{file_ext}"

        bot.send_chat_action(message.chat.id, 'upload_audio')
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)        

        if len(downloaded_file) > 10 * 1024 * 1024:
            raise ValueError("Аудиофайл слишком большой (макс. 10MB)")

        file_path = os.path.join(AUDIO_DIR, file_name)
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)

        if not os.path.exists(file_path):
            raise IOError("Не удалось сохранить аудиофайл")

        msg = bot.send_message(message.chat.id, 
                               f"Аудио для начала урока сохранено.\n"
            f"Введите время окончания урока {lesson_num} (hh:mm):")
        bot.register_next_step_handler(msg, process_end_time, lesson_num, start_time, file_name)

    except Exception as e:
        error_msg = f"❌ Ошибка: {str(e)}\n\nПопробуй снова: /add_lesson"
        bot.send_message(message.chat.id, error_msg)
        logging.error(f"Error in process_start_audio: {str(e)}", exc_info=True)

def process_end_time(message, lesson_num, start_time, start_audio_file):
    try:
        if not message.text:  # Добавлена проверка на наличие текста
            raise ValueError("Пожалуйста, введите время окончания урока")
            
        end_time = message.text.strip()
        if not validate_time(end_time):  # Используем функцию валидации
            raise ValueError("Некорректное время. Формат: HH:MM (00:00-23:59)")
            
        # Загружаем текущие события и добавляем начало урока
        events = load_events()
        events.append(LessonEvent(lesson_num, "start", start_time, start_audio_file))
        
        # Запрашиваем аудио для конца урока
        msg = bot.send_message(message.chat.id, "Отправьте аудиофайл для окончания урока:")
        bot.register_next_step_handler(msg, process_end_audio, lesson_num, end_time, events)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)

def process_end_audio(message, lesson_num, end_time, events):
    try:
        if not (message.audio or message.voice or message.text):
            raise ValueError("Пожалуйста, отправьте аудиофайл или введите /cancel для отмены")
            
        if message.text and message.text.strip().lower() == '/cancel':
            return start(message)
            
        if not (message.audio or message.voice):
            raise ValueError("Пожалуйста, отправьте именно аудиофайл")

        # Вставляем здесь - перед началом загрузки аудио
        bot.send_chat_action(message.chat.id, 'upload_audio')  # <-- ВОТ ТУТ
            
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_ext = "ogg" if message.voice else message.audio.file_name.split('.')[-1]
        file_name = f"lesson_{lesson_num}_end_{int(time.time())}.{file_ext}"
        
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        audio_path = os.path.join(AUDIO_DIR, file_name)
        with open(audio_path, 'wb') as f:
            bot.send_chat_action(message.chat.id, 'upload_document')  # Для записи на диск
            f.write(downloaded_file)        
            
        events.append(LessonEvent(lesson_num, "end", end_time, file_name))
        save_events(events)
        
        bot.send_message(
            message.chat.id,
            f"✅ Урок {lesson_num} успешно добавлен!\n"
            f"Начало: {events[-2].time}\n"
            f"Окончание: {end_time}\n\n"
            f"Не забудьте установить расписание командой /install_cron"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)
        
"""Новый код"""
# --- Меню настроек ---
@bot.message_handler(commands=['settings'])
def settings_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    buttons = [
        types.KeyboardButton('1. Продолжительность урока'),
        types.KeyboardButton('2. Приостановить звонки'),
        types.KeyboardButton('3. Запустить звонки'),
        types.KeyboardButton('/start')
    ]
    markup.add(*buttons)
    
    settings = load_settings()
    status = "приостановлены" if settings["cron_paused"] else "активны"
    
    bot.send_message(
        message.chat.id,
        f"⚙️ Настройки:\n\n"
        f"1. Текущая продолжительность урока: {settings['lesson_duration']} мин\n"
        f"2. Статус звонков: {status}\n\n"
        f"Выберите действие:",
        reply_markup=markup
    )

# Обработчики пунктов меню настроек
@bot.message_handler(func=lambda message: message.text == '1. Продолжительность урока')
def set_lesson_duration(message):
    msg = bot.send_message(message.chat.id, "Сколько минут длится урок? (Введите число от 1 до 120):")
    bot.register_next_step_handler(msg, process_lesson_duration)

def process_lesson_duration(message):
    try:
        duration = int(message.text)
        if not 1 <= duration <= 120:
            raise ValueError("Длительность должна быть от 1 до 120 минут")
            
        settings = load_settings()
        settings["lesson_duration"] = duration
        save_settings(settings)
        
        bot.send_message(message.chat.id, f"✅ Продолжительность урока установлена: {duration} мин")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        settings_menu(message)

@bot.message_handler(func=lambda message: message.text == '2. Приостановить звонки')
def pause_cron(message):
    try:
        # Резервное копирование и очистка cron
        with open(CRON_BACKUP_FILE, 'w') as f:
            f.write(os.popen("crontab -l").read())
        os.system("crontab -r")
        
        settings = load_settings()
        settings["cron_paused"] = True
        save_settings(settings)
        
        bot.send_message(message.chat.id, "✅ Звонки приостановлены. Cron очищен.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        settings_menu(message)

@bot.message_handler(func=lambda message: message.text == '3. Запустить звонки')
def resume_cron(message):
    try:
        if os.path.exists(CRON_BACKUP_FILE):
            os.system(f"crontab {CRON_BACKUP_FILE}")
            status = "восстановлены"
        else:
            install_cron_jobs()
            status = "запущены (новые)"
            
        settings = load_settings()
        settings["cron_paused"] = False
        save_settings(settings)
        
        bot.send_message(message.chat.id, f"✅ Звонки {status}. Cron активирован.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        settings_menu(message)
#________________________________________________

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
