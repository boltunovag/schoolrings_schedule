#!/bin/bash

# Проверка, что скрипт запущен не от root
if [ "$(id -u)" -eq 0 ]; then
    echo "Запустите скрипт БЕЗ sudo!" >&2
    exit 1
fi

CURRENT_USER=$(whoami)

# Проверка доступа к репозиториям
check_repo_access() {
    if ! curl -s --connect-timeout 5 http://repo.os.mos.ru >/dev/null; then
        echo "Внимание: Нет доступа к репозиториям ROSA Linux"
        return 1
    fi
    return 0
}

# Функция для проверки sudo пароля
check_sudo() {
    if ! sudo -n true 2>/dev/null; then
        echo "Требуются права sudo. Введите пароль:"
        if ! sudo -v; then
            echo "Ошибка: Неверный пароль или нет прав sudo"
            exit 1
        fi
    fi
}

# Установка зависимостей
install_dependencies() {
    if check_repo_access; then
        echo "Обновление системных пакетов..."
        sudo dnf update -y
    fi
    
    echo "Установка необходимых пакетов..."
    sudo dnf dnf makecache -y \
        python3 \
        python3-pip \
        mpg123 \
        cronie \
        git
    
    # Настройка безопасного каталога для Git
    sudo git config --global --add safe.directory /opt/schoolrings
}

# Проверяем sudo перед началом
check_sudo

# Установка зависимостей
install_dependencies

# Клонирование репозитория
if [ ! -d "/opt/schoolrings" ]; then
    sudo git clone https://github.com/boltunovag/schoolrings_schedule /opt/schoolrings
else
    echo "Директория /opt/schoolrings уже существует. Обновляю..."
    cd /opt/schoolrings && sudo git pull
fi

# Установка прав
sudo chown -R $CURRENT_USER:$CURRENT_USER /opt/schoolrings
sudo chmod -R 755 /opt/schoolrings

# Установка Python-зависимостей
sudo pip3 install -r /opt/schoolrings/requirements.txt

# Создание .env файла
if [ ! -f "/opt/schoolrings/.env" ]; then
  read -p "Enter Telegram token:" TToken
  if [ -z "$TToken" ]; then
    TToken="your_token_here"
  fi
  cat | sudo tee /opt/schoolrings/.env <<EOF
TELEGRAM_BOT_TOKEN=$TToken
BOT_PASSWORD=$(openssl rand -hex 16)
AUDIO_DIR=/opt/schoolrings/audio_files
SCHEDULE_FILE=/opt/schoolrings/data/schedule_files/schedule.txt
EOF
    sudo chown $CURRENT_USER:$CURRENT_USER /opt/schoolrings/.env
    echo "Настройте /opt/schoolrings/.env перед запуском!"
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