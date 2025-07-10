#!/bin/bash

# ... (остальная часть шапки скрипта без изменений)

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
        
        # Запрос токена с проверкой
        while true; do
            read -p "Введите Telegram токен бота (обязательно): " TToken
            if [ -n "$TToken" ]; then
                break
            else
                echo -e "${RED}Ошибка: Токен не может быть пустым!${NC}"
            fi
        done
        
        # Запрос пароля администратора
        read -p "Введите пароль администратора (оставьте пустым для автоматической генерации): " AdminPass
        if [ -z "$AdminPass" ]; then
            AdminPass=$(openssl rand -hex 16)
            echo -e "${YELLOW}Сгенерирован случайный пароль: $AdminPass${NC}"
        fi

        cat <<EOF | sudo tee "$WORK_DIR/.env" > /dev/null
TELEGRAM_BOT_TOKEN=$TToken
BOT_PASSWORD=$AdminPass
AUDIO_DIR=$WORK_DIR/audio_files
SCHEDULE_FILE=$WORK_DIR/data/schedule_files/schedule.txt
EOF
        
        sudo chown "$CURRENT_USER:$CURRENT_USER" "$WORK_DIR/.env"
        echo -e "${GREEN}Файл .env успешно создан.${NC}"
        echo -e "${YELLOW}Сохраните этот пароль для доступа к боту: $AdminPass${NC}"
    else
        echo -e "${YELLOW}Файл .env уже существует, пропускаем создание.${NC}"
        echo -e "Проверьте его содержимое: ${YELLOW}$WORK_DIR/.env${NC}"
    fi
}

# ... (остальная часть скрипта без изменений)