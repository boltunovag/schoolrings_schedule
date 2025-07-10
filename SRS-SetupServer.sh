#!/bin/bash

# Проверка, что скрипт запущен не от root
if [ "$(id -u)" -eq 0 ]; then
    echo "Ошибка: Запустите скрипт БЕЗ sudo!" >&2
    exit 1
fi

CURRENT_USER=$(whoami)
WORK_DIR="/opt/schoolrings"
SERVICE_NAME="schoolrings"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция проверки ошибок
check_error() {
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка: $1${NC}" >&2
        exit 1
    fi
}

# Проверка sudo пароля
check_sudo() {
    echo -e "${YELLOW}Проверка прав sudo...${NC}"
    if ! sudo -v; then
        echo -e "${RED}Ошибка: Неверный пароль или нет прав sudo${NC}" >&2
        exit 1
    fi
}

# Проверка доступа к репозиториям
check_repo_access() {
    echo -e "${YELLOW}Проверка доступа к репозиториям...${NC}"
    if ! curl -s --connect-timeout 5 http://repo.os.mos.ru >/dev/null; then
        echo -e "${YELLOW}Внимание: Нет доступа к репозиториям ROSA Linux${NC}"
        return 1
    fi
    return 0
}

# Установка зависимостей
install_dependencies() {
    echo -e "${YELLOW}Установка зависимостей...${NC}"
    
    if check_repo_access; then
        echo "Обновление системных пакетов..."
        sudo dnf update -y
        check_error "Не удалось обновить пакеты"
    fi
    
    sudo dnf install -y \
        python3 \
        python3-pip \
        mpg123 \
        cronie \
        git \
        openssl
    check_error "Не удалось установить пакеты"

    # Настройка безопасного каталога для Git
    sudo git config --global --add safe.directory "$WORK_DIR"
}

# Настройка окружения
setup_environment() {
    echo -e "${YELLOW}Настройка окружения...${NC}"
    
    # Создание директорий
    sudo mkdir -p "$WORK_DIR/data/schedule_files"
    sudo mkdir -p "$WORK_DIR/audio_files"
    sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$WORK_DIR"
    sudo chmod -R 755 "$WORK_DIR"

    # Создание .env файла
    if [ ! -f "$WORK_DIR/.env" ]; then
        echo -e "${YELLOW}Создание файла настроек...${NC}"
        read -p "Введите Telegram токен бота: " TToken
        [ -z "$TToken" ] && TToken="your_token_here"
        
        cat <<EOF | sudo tee "$WORK_DIR/.env" > /dev/null
TELEGRAM_BOT_TOKEN=$TToken
BOT_PASSWORD=$(openssl rand -hex 16)
AUDIO_DIR=$WORK_DIR/audio_files
SCHEDULE_FILE=$WORK_DIR/data/schedule_files/schedule.txt
EOF
        
        sudo chown "$CURRENT_USER:$CURRENT_USER" "$WORK_DIR/.env"
        echo -e "${GREEN}Файл .env создан. Вы можете изменить его вручную: $WORK_DIR/.env${NC}"
    fi
}

# Установка сервиса
setup_service() {
    echo -e "${YELLOW}Настройка systemd сервиса...${NC}"
    
    cat <<EOF | sudo tee "/etc/systemd/system/$SERVICE_NAME.service" > /dev/null
[Unit]
Description=SchoolRings Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$WORK_DIR
EnvironmentFile=$WORK_DIR/.env
ExecStart=/usr/bin/python3 $WORK_DIR/SRS.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable --now "$SERVICE_NAME.service"
    check_error "Не удалось запустить сервис"
}

# Основной процесс установки
main() {
    check_sudo
    
    # Установка зависимостей
    install_dependencies
    
    # Клонирование репозитория
    echo -e "${YELLOW}Установка приложения...${NC}"
    if [ ! -d "$WORK_DIR" ]; then
        sudo git clone https://github.com/boltunovag/schoolrings_schedule "$WORK_DIR"
        check_error "Не удалось клонировать репозиторий"
    else
        echo "Директория $WORK_DIR уже существует. Обновляю..."
        cd "$WORK_DIR" && sudo git pull
        check_error "Не удалось обновить репозиторий"
    fi
    
    # Настройка прав
    sudo chown -R "$CURRENT_USER:$CURRENT_USER" "$WORK_DIR"
    sudo chmod -R 755 "$WORK_DIR"
    
    # Установка Python-зависимостей
    echo -e "${YELLOW}Установка Python зависимостей...${NC}"
    sudo pip3 install -r "$WORK_DIR/requirements.txt"
    check_error "Не удалось установить Python зависимости"
    
    # Настройка окружения
    setup_environment
    
    # Настройка сервиса
    setup_service
    
    echo -e "\n${GREEN}Установка завершена успешно!${NC}"
    echo -e "\nКоманды для управления:"
    echo -e "  Проверить статус: ${YELLOW}systemctl status $SERVICE_NAME${NC}"
    echo -e "  Просмотреть логи: ${YELLOW}journalctl -u $SERVICE_NAME -f${NC}"
    echo -e "  Перезапустить сервис: ${YELLOW}sudo systemctl restart $SERVICE_NAME${NC}"
    echo -e "\nНе забудьте настроить файл .env: ${YELLOW}$WORK_DIR/.env${NC}"
}

main