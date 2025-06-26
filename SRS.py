import os
import telebot
from telebot import types
import time
from dotenv import load_dotenv
import json
import logging
import re
from datetime import datetime 

# --- Настройки ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)


# Константы
AUDIO_DIR = "audio_files"
SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.txt")
CRON_FILE = "audio_schedule.cron"
SETTINGS_FILE = "settings.json"
CRON_BACKUP_FILE = "cron_backup.txt"
CRON_BACKUPS_DIR = "cron_backups"  # Добавьте эту строку
AUDIO_BACKUPS_DIR = "audio_backups"  # И эту строку

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(CRON_BACKUPS_DIR, exist_ok=True)
os.makedirs(AUDIO_BACKUPS_DIR, exist_ok=True)

# Добавляем в начало файла (после других констант)
PASSWORD_FILE = "password.txt"
MAX_ATTEMPTS = 3
SESSION_TIMEOUT = 30 * 60  # 30 минут в секундах

# Глобальные переменные для хранения состояния аутентификации
authenticated_users = {}  # {chat_id: (timestamp, level)}


# --- Класс для событий ---
class LessonEvent:
    def __init__(self, lesson_num, event_type, time, audio_file):
        self.lesson_num = lesson_num
        self.event_type = event_type
        self.time = time
        self.audio_file = audio_file

# --- Логирование ---
logging.basicConfig(
    filename='bot_errors.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'
)
#--------------------Аутентификация----------------------------------->
# Добавляем новые функции для работы с паролем
def init_password():
    """Инициализирует файл с паролем, если его нет"""
    if not os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'w') as f:
            f.write("admin123")  # Пароль по умолчанию
        os.chmod(PASSWORD_FILE, 0o600)  # Доступ только владельцу

def check_password(input_password):
    """Проверяет введённый пароль"""
    try:
        with open(PASSWORD_FILE, 'r') as f:
            correct_password = f.read().strip()
        return input_password == correct_password
    except Exception as e:
        logging.error(f"Ошибка проверки пароля: {str(e)}")
        return False

def change_password(new_password):
    """Изменяет пароль"""
    try:
        with open(PASSWORD_FILE, 'w') as f:
            f.write(new_password.strip())
        os.chmod(PASSWORD_FILE, 0o600)
        return True
    except Exception as e:
        logging.error(f"Ошибка изменения пароля: {str(e)}")
        return False

def is_authenticated(chat_id):
    """Проверяет, аутентифицирован ли пользователь"""
    if chat_id not in authenticated_users:
        return False
    
    login_time, _ = authenticated_users[chat_id]
    if time.time() - login_time > SESSION_TIMEOUT:
        del authenticated_users[chat_id]
        return False
    
    return True
def auth_required(func):
    """Декоратор для проверки аутентификации"""
    def wrapper(message):
        if not is_authenticated(message.chat.id):
            request_password(message)
            return
        return func(message)
    return wrapper

#--------------------Работа с cron------------------------------------>
def get_cron_path():
    """Определяет путь к crontab пользователя"""
    # Варианты расположения crontab для разных систем
    possible_paths = [
        f"/var/spool/cron/crontabs/{os.getenv('USER')}",  # Ubuntu/Debian
        f"/var/spool/cron/{os.getenv('USER')}",           # CentOS/RHEL
        os.path.expanduser("~/.crontab")                  # Альтернативный вариант
    ]
    
    for path in possible_paths:
        if os.path.exists(os.path.dirname(path)):
            return path
    return None
def check_file_permissions():
    try:
        test_file = SCHEDULE_FILE + '.test'
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return True
    except:
        return False
# --- Работа с расписанием ---

# В функции calculate_end_time можно добавить проверку:
def calculate_end_time(start_time, duration):
    h, m = map(int, start_time.split(':'))
    total_minutes = h * 60 + m + duration
    
    if total_minutes >= 24*60:
        raise ValueError("Урок не может заканчиваться после полуночи")
    
    end_h = total_minutes // 60
    end_m = total_minutes % 60
    return f"{end_h:02d}:{end_m:02d}"
#---------------------------------------------------->

def validate_lesson_times(new_lesson_num, new_start, new_end, existing_events):
    """Проверяет корректность времени урока с учетом последовательности"""
    try:
        # Преобразуем время в минуты для удобства сравнения
        def time_to_minutes(time_str):
            h, m = map(int, time_str.split(':'))
            return h * 60 + m

        new_start_min = time_to_minutes(new_start)
        new_end_min = time_to_minutes(new_end)

        # 1. Проверка что начало раньше конца
        if new_start_min >= new_end_min:
            return False, "⛔ Начало урока должно быть раньше конца"

        # 2. Проверка последовательности уроков
        existing_nums = {int(e.lesson_num) for e in existing_events}
        current_num = int(new_lesson_num)

        # Если это новый урок (не существующий номер)
        if current_num not in existing_nums:
            if existing_events:
                # Находим максимальный номер урока
                max_lesson_num = max(existing_nums)
                
                # Если номер нового урока не следующий по порядку
                if current_num != max_lesson_num + 1:
                    return False, f"⛔ Следующий урок должен иметь номер {max_lesson_num + 1}"

                # Находим время конца последнего урока
                last_lesson_ends = [
                    time_to_minutes(e.time) 
                    for e in existing_events 
                    if e.event_type == 'end'
                ]
                if last_lesson_ends:
                    last_lesson_end = max(last_lesson_ends)
                    if new_start_min < last_lesson_end:
                        last_end_str = f"{last_lesson_end//60:02d}:{last_lesson_end%60:02d}"
                        return False, (
                            f"⛔ Урок {new_lesson_num} должен начинаться ПОСЛЕ "
                            f"конца предыдущего урока ({last_end_str})"
                        )

        # 3. Проверка пересечений с другими уроками
        for event in existing_events:
            if event.lesson_num == new_lesson_num:
                continue

            if event.event_type == 'start':
                other_start = time_to_minutes(event.time)
                other_end = next(
                    (time_to_minutes(e.time) 
                     for e in existing_events 
                     if e.lesson_num == event.lesson_num and e.event_type == 'end'),
                    None
                )

                if other_end:
                    # Проверяем пересечение временных интервалов
                    if (new_start_min < other_end) and (new_end_min > other_start):
                        other_start_str = event.time
                        other_end_str = f"{other_end//60:02d}:{other_end%60:02d}"
                        return False, (
                            f"⛔ Пересечение с уроком {event.lesson_num} "
                            f"({other_start_str}-{other_end_str})"
                        )

        return True, "✅ Время урока корректно"

    except ValueError as e:
        return False, f"⛔ Ошибка формата времени: {str(e)}"
#---------------------------------------------------->
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
        logging.error(f"Ошибка загрузки расписания: {str(e)}")
    return events

    """Сохраняет события в файл и автоматически устанавливает cron"""
def save_events(events):
    try:
        logging.info(f"Попытка сохранения {len(events)} событий")
        logging.info(f"Путь к файлу: {os.path.abspath(SCHEDULE_FILE)}")
        logging.info(f"Права на директорию: {oct(os.stat(os.path.dirname(SCHEDULE_FILE)).st_mode)}")
        
        # Полный абсолютный путь
        schedule_path = os.path.abspath(SCHEDULE_FILE)
        os.makedirs(os.path.dirname(schedule_path), exist_ok=True)
        
        # Временный файл для безопасной записи
        temp_path = schedule_path + '.tmp'
        
        lesson_records = {}
        for event in events:
            key = (event.lesson_num, event.event_type)
            lesson_records[key] = event

        with open(temp_path, 'w') as f:
            for key in sorted(lesson_records.keys()):
                event = lesson_records[key]
                line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
                f.write(line)
        
        # Атомарная замена файла
        if os.path.exists(schedule_path):
            os.remove(schedule_path)
        os.rename(temp_path, schedule_path)
        
        return True
        
    except Exception as e:
        logging.error(f"Ошибка сохранения расписания: {str(e)}", exc_info=True)
        return False

# --- Работа с настройками ---
def load_settings():
    """Загружает настройки из файла"""
    default_settings = {
        "lesson_duration": 45,
        "cron_paused": False
    }
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return {**default_settings, **json.load(f)}
    except:
        return default_settings

def save_settings(settings):
    """Сохраняет настройки в файл"""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

# --- Работа с cron ---
def generate_cron_jobs(events):
    """Генерирует crontab с абсолютными путями"""
    if not os.path.exists(AUDIO_DIR):
        os.makedirs(AUDIO_DIR, exist_ok=True)
    
    abs_audio_dir = os.path.abspath(AUDIO_DIR)
    cron_log = os.path.join(abs_audio_dir, 'cron.log')
    
    cron_content = "# Аудио расписание\n\n"
    
    for event in sorted(events, key=lambda x: x.time):
        try:
            audio_path = os.path.join(abs_audio_dir, event.audio_file)
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file {audio_path} not found")
            
            hour, minute = event.time.split(':')
            cron_content += (
                f"{minute} {hour} * * 1-5 "
                f"/usr/bin/mpg123 '{audio_path}' "
                f">>{cron_log} 2>&1\n"
            )
        except Exception as e:
            logging.error(f"Error processing event {event.lesson_num}: {str(e)}")
    
    return cron_content
#------------------------------>
def install_cron_jobs():
    """Устанавливает задания в crontab с полной диагностикой"""
    try:
        events = load_events()
        if not events:
            return False, "Нет событий для установки"
        
        # Генерируем содержимое cron
        cron_content = generate_cron_jobs(events)
        
        # Сохраняем во временный файл
        with open(CRON_FILE, 'w') as f:
            f.write(cron_content)
        
        # 1. Пробуем стандартную установку
        exit_code = os.system(f"crontab {CRON_FILE} 2>&1")
        if exit_code == 0:
            return True, "Cron успешно установлен"
        
        # 2. Получаем информацию об ошибке
        error = os.popen(f"crontab {CRON_FILE} 2>&1").read()
        
        # 3. Проверяем возможные причины
        if "permission denied" in error.lower():
            # Пробуем через sudo
            username = os.getenv('USER')
            exit_code = os.system(f"sudo crontab -u {username} {CRON_FILE}")
            if exit_code == 0:
                return True, "Cron установлен через sudo"
            else:
                sudo_error = os.popen(f"sudo crontab -u {username} {CRON_FILE} 2>&1").read()
                manual_install = (
                    "Требуются права администратора.\n"
                    "Выполните вручную:\n"
                    f"1. nano {os.path.abspath(CRON_FILE)}\n"
                    f"2. sudo crontab -u {username} {os.path.abspath(CRON_FILE)}"
                )
                return False, f"{sudo_error}\n\n{manual_install}"
        
        elif "no crontab for" in error.lower():
            # Пробуем создать новый crontab
            exit_code = os.system(f"crontab -l >/dev/null 2>&1 || crontab {CRON_FILE}")
            if exit_code == 0:
                return True, "Создан новый crontab"
            else:
                return False, "Не удалось создать crontab"
        
        else:
            # Неизвестная ошибка
            return False, f"Неизвестная ошибка: {error}"
            
    except Exception as e:
        logging.error(f"Cron error: {str(e)}", exc_info=True)
        return False, f"Ошибка: {str(e)}"

#---------------------------------------------------------->
# --- Команды бота ---
# Модифицируем команду start
@bot.message_handler(commands=['start'])
def start(message):
    if not is_authenticated(message.chat.id):
        request_password(message)
        return
        
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton('/add_lesson'),
        types.KeyboardButton('/show_schedule'),
        types.KeyboardButton('/settings'),
        types.KeyboardButton('/change_password')
    ]
    markup.add(*buttons)
    
    bot.send_message(
        message.chat.id,
        "📅 Бот для управления расписанием\n\n"
        "Доступные команды:\n"
        "/add_lesson - добавить урок\n"
        "/show_schedule - показать расписание\n"
        "/settings - настройки\n"
        "/change_password - изменить пароль",
        reply_markup=markup
    )

def request_password(message):
    """Запрашивает пароль у пользователя"""
    msg = bot.send_message(
        message.chat.id,
        "🔒 Для работы с ботом требуется аутентификация.\n"
        "Введите пароль:"
    )
    bot.register_next_step_handler(msg, process_password)

def process_password(message):
    """Обрабатывает введённый пароль"""
    try:
        if check_password(message.text):
            authenticated_users[message.chat.id] = (time.time(), "admin")
            bot.send_message(message.chat.id, "✅ Успешная аутентификация!")
            start(message)
        else:
            # Подсчёт попыток
            if 'attempts' not in process_password.__dict__:
                process_password.attempts = {}
            
            if message.chat.id not in process_password.attempts:
                process_password.attempts[message.chat.id] = 1
            else:
                process_password.attempts[message.chat.id] += 1
            
            remaining = MAX_ATTEMPTS - process_password.attempts[message.chat.id]
            
            if remaining > 0:
                msg = bot.send_message(
                    message.chat.id,
                    f"❌ Неверный пароль. Осталось попыток: {remaining}\n"
                    "Попробуйте ещё раз:"
                )
                bot.register_next_step_handler(msg, process_password)
            else:
                del process_password.attempts[message.chat.id]
                bot.send_message(
                    message.chat.id,
                    "🚫 Превышено максимальное количество попыток. "
                    "Попробуйте позже."
                )
    except Exception as e:
        logging.error(f"Ошибка в process_password: {str(e)}")
        bot.send_message(
            message.chat.id,
            "⚠️ Произошла ошибка при) проверке пароля. Попробуйте позже."
        )

# Добавляем команду для смены пароля
@bot.message_handler(commands=['change_password'])
@auth_required
def change_password_command(message):
    if not is_authenticated(message.chat.id):
        request_password(message)
        return
        
    msg = bot.send_message(
        message.chat.id,
        "Введите новый пароль (не менее 8 символов):"
    )
    bot.register_next_step_handler(msg, process_new_password)
def process_new_password(message):
    try:
        new_password = message.text.strip()
        if len(new_password) < 8:
            raise ValueError("Пароль должен содержать не менее 8 символов")
            
        if change_password(new_password):
            bot.send_message(message.chat.id, "✅ Пароль успешно изменён!")
        else:
            bot.send_message(message.chat.id, "❌ Не удалось изменить пароль!")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
    finally:
        start(message)       
#-------------------Проверяем Cron------------------------->

@bot.message_handler(commands=['debug_cron'])
def debug_cron(message):
    """Команда для диагностики проблем с cron"""
    try:
        # 1. Проверяем доступность crontab
        crontab_path = os.popen("which crontab").read().strip()
        exists = "✅ Доступен" if crontab_path else "❌ Не установлен"
        
        # 2. Проверяем права
        test_file = "test_cron_job"
        with open(test_file, 'w') as f:
            f.write("* * * * * echo 'test'\n")
        
        exit_code = os.system(f"crontab {test_file} 2>/dev/null")
        permissions = "✅ Есть права" if exit_code == 0 else "❌ Нет прав"
        
        # 3. Пробуем получить текущие задания
        current_jobs = os.popen("crontab -l 2>&1").read()
        if "no crontab" in current_jobs:
            jobs_status = "Нет заданий"
        elif "permission denied" in current_jobs:
            jobs_status = "Ошибка прав доступа"
        else:
            jobs_status = f"{len(current_jobs.splitlines())} заданий"
        
        # 4. Проверяем системный cron.d
        cron_d_status = "✅ Доступен" if os.path.exists("/etc/cron.d") else "❌ Недоступен"
        
        report = (
            "Диагностика cron:\n"
            f"1. crontab: {exists} ({crontab_path})\n"
            f"2. Права: {permissions}\n"
            f"3. Текущие задания: {jobs_status}\n"
            f"4. Системный cron.d: {cron_d_status}"
        )
        
        bot.reply_to(message, report)
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка диагностики: {str(e)}")
################################Показ расписания##################################################

@bot.message_handler(commands=['show_schedule'])
def show_schedule(message):
    try:
        # Получаем текущие события из нашего расписания
        events = load_events()
        
        if not events:
            bot.send_message(message.chat.id, "Расписание пусто.")
            return
        
        # Группируем события по урокам для удобного отображения
        lessons = {}
        for event in events:
            if event.lesson_num not in lessons:
                lessons[event.lesson_num] = {'start': None, 'end': None}
            
            if event.event_type == 'start':
                lessons[event.lesson_num]['start'] = {
                    'time': event.time,
                    'audio': event.audio_file
                }
            elif event.event_type == 'end':
                lessons[event.lesson_num]['end'] = {
                    'time': event.time,
                    'audio': event.audio_file
                }
        
        # Формируем сообщение с расписанием
        schedule_text = "📅 Текущее расписание:\n\n"
        for lesson_num in sorted(lessons.keys(), key=lambda x: int(x)):
            lesson = lessons[lesson_num]
            schedule_text += (
                f"Урок {lesson_num}:\n"
                f"  🔔 Начало: {lesson['start']['time']} (аудио: {lesson['start']['audio']})\n"
                f"  🔕 Конец: {lesson['end']['time']} (аудио: {lesson['end']['audio']})\n\n"
            )
        
        # Добавляем информацию о cron
        cron_status = get_cron_status()
        schedule_text += f"\nСтатус cron: {cron_status}"
        
        bot.send_message(message.chat.id, schedule_text)
        
    except Exception as e:
        logging.error(f"Ошибка при показе расписания: {str(e)}")
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")

def get_cron_status():
    """Проверяет статус cron и возвращает текстовое описание"""
    try:
        # Получаем содержимое crontab
        cron_output = os.popen("crontab -l 2>&1").read()
        
        if "no crontab" in cron_output.lower():
            return "Не установлен"
        
        # Проверяем наличие наших записей
        events = load_events()
        if not events:
            return "Установлен (нет наших записей)"
        
        # Подсчитываем наши записи в crontab
        our_entries = 0
        for event in events:
            if f"mpg123 '{os.path.join(os.path.abspath(AUDIO_DIR), event.audio_file)}'" in cron_output:
                our_entries += 1
        
        settings = load_settings()
        if settings.get("cron_paused", False):
            return f"Приостановлен (наших записей: {our_entries}/{len(events)*2})"
        
        return f"Активен (наших записей: {our_entries}/{len(events)*2})"
    
    except Exception as e:
        logging.error(f"Ошибка проверки статуса cron: {str(e)}")
        return "Неизвестен"
################################Конец показа расписания##################################################

@bot.message_handler(commands=['settings'])
@auth_required
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

# Обработчики для меню настроек
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

# ... (остальные существующие функции process_lesson_number, 
# process_start_time, process_start_audio, process_end_time, 
# process_end_audio остаются без изменений)
current_lessons = {}  # Временное хранилище для уроков в процессе добавления


@bot.message_handler(commands=['add_lesson'])
@auth_required
def add_lesson(message):
    try:
        msg = bot.send_message(message.chat.id, "Введите номер урока (например, 1):")
        bot.register_next_step_handler(msg, process_lesson_number)
    except Exception as e:
        logging.error(f"Ошибка в /add_lesson: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, f"❌ Ошибка при начале добавления урока: {str(e)}")
        start(message)



def process_lesson_number(message):
    try:
        lesson_num = message.text.strip()
        if not lesson_num.isdigit():
            raise ValueError("Номер урока должен быть числом")
            
        existing_events = load_events()
        existing_nums = {int(e.lesson_num) for e in existing_events}
        current_num = int(lesson_num)
        
        # Если есть существующие уроки
        if existing_nums:
            max_num = max(existing_nums)
            
            # Проверяем можно ли добавить/изменить урок
            if current_num not in existing_nums:  # Новый номер
                if current_num != max_num + 1:
                    raise ValueError(
                        f"Нельзя добавить урок №{current_num}. "
                        f"Следующий доступный номер: {max_num + 1}"
                    )
            # else: номер существует - разрешаем редактирование
            
        # Сохраняем данные урока
        current_lessons[message.chat.id] = {
            'lesson_num': lesson_num,
            'start_time': None,
            'end_time': None,
            'start_audio': None,
            'end_audio': None
        }
        
        bot.send_message(
            message.chat.id,
            f"Урок {lesson_num}. Введите время начала (ЧЧ:ММ):"
        )
        bot.register_next_step_handler(message, process_start_time)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)


def is_valid_audio_file(file_info):
    """Проверяет, что файл является аудио"""
    audio_extensions = ['.mp3', '.wav', '.ogg', '.m4a']
    file_ext = os.path.splitext(file_info.file_path)[1].lower()
    return file_ext in audio_extensions

def calculate_end_time(start_time, duration):
    """Вычисляет время окончания урока"""
    h, m = map(int, start_time.split(':'))
    total_minutes = h * 60 + m + duration
    end_h = total_minutes // 60
    end_m = total_minutes % 60
    return f"{end_h:02d}:{end_m:02d}"

def normalize_time(time_str):
    """Нормализует время в формат HH:MM"""
    parts = time_str.split(':')
    if len(parts) != 2:
        raise ValueError("Неверный формат времени")
    
    h, m = parts
    try:
        hour = int(h)
        minute = int(m)
    except ValueError:
        raise ValueError("Часы и минуты должны быть числами")
    
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Некорректное время (должно быть 00:00-23:59)")
    
    return f"{hour:02d}:{minute:02d}"

def process_start_time(message):
    try:
        lesson_num = current_lessons[message.chat.id]['lesson_num']
        time_str = message.text.strip()
        
        # Нормализуем время
        start_time = normalize_time(time_str)
        
        # Вычисляем время окончания
        settings = load_settings()
        duration = settings['lesson_duration']
        end_time = calculate_end_time(start_time, duration)
        
        # Проверяем пересечение с другими уроками
        existing_events = load_events()
        is_valid, error_msg = validate_lesson_times(lesson_num, start_time, end_time, existing_events)
        if not is_valid:
            raise ValueError(error_msg)
            
        # Сохраняем время
        current_lessons[message.chat.id]['start_time'] = start_time
        current_lessons[message.chat.id]['end_time'] = end_time
        
        msg = bot.send_message(message.chat.id, "Отправьте аудиофайл для начала урока:")
        bot.register_next_step_handler(msg, process_start_audio)
        
    except Exception as e:
        if message.chat.id in current_lessons:
            del current_lessons[message.chat.id]
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)


#--------------------AUDIO------------------------------------>
def process_start_audio(message):
    try:
        # Проверяем, что отправили аудиофайл
        if not message.audio and not message.document:
            raise ValueError("Отправьте аудиофайл в формате MP3, WAV или OGG")
        
        # Получаем файл
        file_info = bot.get_file(message.audio.file_id if message.audio else message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Сохраняем файл
        file_ext = os.path.splitext(file_info.file_path)[1].lower() or '.mp3'
        filename = f"start_{current_lessons[message.chat.id]['lesson_num']}{file_ext}"
        with open(os.path.join(AUDIO_DIR, filename), 'wb') as f:
            f.write(downloaded_file)
        
        # Сохраняем информацию о файле
        current_lessons[message.chat.id]['start_audio'] = filename
        
        # Запрашиваем аудио для конца урока
        bot.send_message(
            message.chat.id, 
            "Аудио для начала урока сохранено. Отправьте аудио для конца урока:"
        )
        bot.register_next_step_handler(message, process_end_audio)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        if message.chat.id in current_lessons:
            del current_lessons[message.chat.id]
        start(message)
def process_end_audio(message):
    try:
        # Проверка наличия данных урока
        if message.chat.id not in current_lessons:
            raise ValueError("Сессия добавления урока не найдена. Начните заново.")
            
        lesson_data = current_lessons[message.chat.id]
        
        # Проверка обязательных полей
        required_fields = {
            'lesson_num': "Номер урока",
            'start_time': "Время начала",
            'end_time': "Время окончания",
            'start_audio': "Аудио начала урока"
        }
        
        for field, name in required_fields.items():
            if field not in lesson_data or not lesson_data[field]:
                raise ValueError(f"Отсутствует обязательное поле: {name}")

        # Загрузка существующих событий
        existing_events = load_events()
        
        # Фильтрация событий
        filtered_events = [e for e in existing_events if e.lesson_num != lesson_data['lesson_num']]
        
        # Валидация времени урока
        is_valid, error_msg = validate_lesson_times(
            lesson_data['lesson_num'],
            lesson_data['start_time'],
            lesson_data['end_time'],
            existing_events
            #filtered_events
        )
        
        if not is_valid:
            cleanup_lesson_files(lesson_data)
            raise ValueError(error_msg)

        # Проверка и загрузка аудиофайла
        if not message.audio and not message.document:
            cleanup_lesson_files(lesson_data)
            raise ValueError("Пожалуйста, отправьте аудиофайл для звонка на конец урока")

        file_info = bot.get_file(message.audio.file_id if message.audio else message.document.file_id)
        if not file_info:
            cleanup_lesson_files(lesson_data)
            raise ValueError("Не удалось получить информацию о файле")

        # Обработка расширения файла
        file_ext = os.path.splitext(file_info.file_path)[1].lower()
        if not file_ext or file_ext not in ['.mp3', '.wav', '.ogg', '.m4a']:
            file_ext = '.mp3'

        # Создание имени файла и пути
        filename = f"end_{lesson_data['lesson_num']}{file_ext}"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        # Скачивание и сохранение файла
        try:
            downloaded_file = bot.download_file(file_info.file_path)
            os.makedirs(AUDIO_DIR, exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(downloaded_file)
        except Exception as e:
            cleanup_lesson_files(lesson_data)
            raise ValueError(f"Ошибка сохранения файла: {str(e)}")

        # Обновление данных урока
        lesson_data['end_audio'] = filename

        # Подготовка и сохранение расписания
        events = [e for e in existing_events if e.lesson_num != lesson_data['lesson_num']]
        events.extend([
            LessonEvent(
                lesson_num=lesson_data['lesson_num'],
                event_type='start',
                time=lesson_data['start_time'],
                audio_file=lesson_data['start_audio']
            ),
            LessonEvent(
                lesson_num=lesson_data['lesson_num'],
                event_type='end',
                time=lesson_data['end_time'],
                audio_file=filename
            )
        ])

        # Проверка прав доступа
        schedule_dir = os.path.dirname(os.path.abspath(SCHEDULE_FILE))
        os.makedirs(schedule_dir, exist_ok=True)
        
        if not os.access(schedule_dir, os.W_OK):
            cleanup_lesson_files(lesson_data)
            raise Exception(f"Нет прав на запись в директорию {schedule_dir}")

        if not save_events(events):
            cleanup_lesson_files(lesson_data)
            raise Exception("Не удалось сохранить файл расписания")

        # Обновление cron
        success, cron_msg = install_cron_jobs()
        if not success:
            raise Exception(f"Расписание сохранено, но не удалось обновить cron: {cron_msg}")

        # Отправка подтверждения
        bot.send_message(
            message.chat.id,
            f"✅ Урок {lesson_data['lesson_num']} успешно добавлен!\n"
            f"⏰ Начало: {lesson_data['start_time']} ({lesson_data['start_audio']})\n"
            f"⏰ Конец: {lesson_data['end_time']} ({filename})"
        )

    except Exception as e:
        logging.error(f"Ошибка в process_end_audio: {str(e)}", exc_info=True)
        if message.chat.id in current_lessons:
            cleanup_lesson_files(current_lessons[message.chat.id])
            del current_lessons[message.chat.id]
        
        error_message = f"❌ Ошибка: {str(e)}"
        if "Нет прав на запись" in str(e):
            error_message += "\n\nПроверьте права доступа к файлам и директориям."
        bot.send_message(message.chat.id, error_message)
    
    finally:
        start(message)

def cleanup_lesson_files(lesson_data):
    """Очистка файлов урока при ошибках"""
    for file_type in ['start_audio', 'end_audio']:
        if file_type in lesson_data and lesson_data[file_type]:
            try:
                filepath = os.path.join(AUDIO_DIR, lesson_data[file_type])
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                logging.error(f"Ошибка удаления файла {filepath}: {str(e)}")
        
#-----------------Ручная проверка------------------->
@bot.message_handler(commands=['check_permissions'])
def check_permissions(message):
    try:
        schedule_path = os.path.abspath(SCHEDULE_FILE)
        dir_path = os.path.dirname(schedule_path)
        
        checks = [
            ("Директория существует", os.path.exists(dir_path)),
            ("Есть права на запись", os.access(dir_path, os.W_OK)),
            ("Файл расписания существует", os.path.exists(schedule_path)),
            ("Можно создать файл", os.access(dir_path, os.W_OK))
        ]
        
        report = "\n".join([f"{name}: {'✅' if result else '❌'}" for name, result in checks])
        bot.reply_to(message, f"Проверка прав:\n{report}")
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка проверки: {str(e)}")        
        
if __name__ == "__main__":
    init_password()
    # Проверка и создание необходимых директорий
    os.makedirs(CRON_BACKUPS_DIR, exist_ok=True)
    os.makedirs(AUDIO_BACKUPS_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    
    print("Бот запущен...")
    bot.infinity_polling()