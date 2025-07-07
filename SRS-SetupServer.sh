#!/bin/bash

# Проверка, что скрипт запущен не от root
if [ "$(id -u)" -eq 0 ]; then
  echo "Запустите скрипт БЕЗ sudo!" >&2
  exit 1
fi

CURRENT_USER=$(whoami)

# Функция для проверки sudo пароля
check_sudo() {
    if ! sudo -n true 2>/dev/null; then
        echo "Теперь требуются права sudo. Введите пароль:"
        if ! sudo -v; then
            echo "Ошибка: Неверный пароль или нет прав sudo"
            exit 1
        fi
    fi
}

# Функция для определения пакетного менеджера
detect_pkg_manager() {
  if command -v dnf &> /dev/null; then
    echo "dnf"
  elif command -v apt &> /dev/null && ! apt --help 2>&1 | grep -q "dnf"; then
    echo "apt"
  else
    echo "unsupported"
  fi
}

# Проверяем sudo перед началом
check_sudo

# Установка зависимостей
PKG_MANAGER=$(detect_pkg_manager)

case $PKG_MANAGER in
  apt)
    echo "Использую apt..."
    sudo apt-get update
    sudo apt-get install -y \
      python3 \
      python3-pip \
      mpg123 \
      cron \
      git
    ;;
  dnf)
    echo "Использую dnf..."
    sudo dnf install -y \
      python3 \
      python3-pip \
      mpg123 \
      cronie \
      git
    ;;
  *)
    echo "Не удалось определить пакетный менеджер. Установите зависимости вручную."
    exit 1
    ;;
esac

# Клонирование репозитория
if [ ! -d "/opt/schoolrings" ]; then
  sudo git clone https://github.com/boltunovag/schoolrings_schedule /opt/schoolrings
else
  echo "Директория /opt/schoolrings уже существует. Обновляю..."
  cd /opt/schoolrings && sudo git pull
fi

# Создаем необходимые директории с правильными правами
sudo mkdir -p /opt/schoolrings/audio_files
sudo mkdir -p /opt/schoolrings/data/{cron_backups,audio_backups,schedule_files}
sudo chown -R $CURRENT_USER:$CURRENT_USER /opt/schoolrings
sudo chmod -R 755 /opt/schoolrings

# Установка Python-зависимостей
pip3 install -r /opt/schoolrings/requirements.txt

# Создание .env файла
if [ ! -f "/opt/schoolrings/.env" ]; then
  cat | sudo tee /opt/schoolrings/.env <<EOF
TELEGRAM_BOT_TOKEN=your_token_here
BOT_PASSWORD=$(openssl rand -hex 16)
AUDIO_DIR=/opt/schoolrings/audio_files
SCHEDULE_FILE=/opt/schoolrings/data/schedule_files/schedule.txt
EOF
  echo "Настройте /opt/schoolrings/.env перед запуском!"
  sudo chown $CURRENT_USER:$CURRENT_USER /opt/schoolrings/.env
fi

# Настройка systemd-сервиса
cat | sudo tee /etc/systemd/system/schoolrings.service <<EOF
[Unit]
Description=SchoolRings Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=/opt/schoolrings
EnvironmentFile=/opt/schoolrings/.env
ExecStart=/usr/bin/python3 /opt/schoolrings/SRS.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now schoolrings.service

echo "Установка завершена успешно!"
echo "Команды для управления:"
echo "  Проверить статус: systemctl status schoolrings"
echo "  Просмотреть логи: journalctl -u schoolrings -f"
echo "  Перезапустить: sudo systemctl restart schoolrings"
echo ""
echo "Директории:"
echo "  Аудиофайлы: /opt/schoolrings/audio_files"
echo "  Данные: /opt/schoolrings/data"
echo "  Логи: journalctl -u schoolrings"