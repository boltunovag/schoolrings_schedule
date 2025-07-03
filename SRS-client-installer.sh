#!/bin/bash

# Проверяем, запущен ли скрипт от root (чтобы записать SSH-ключ)
if [ "$(id -u)" -ne 0 ]; then
    echo "Этот скрипт нужно запускать с sudo (для настройки SSH)."
    exit 1
fi

# Запрашиваем данные у пользователя
read -p "Введите IP сервера: " SERVER_IP
read -p "Введите имя пользователя на сервере: " SERVER_USER
read -p "Введите путь к боту на сервере (например, /home/user/bot): " BOT_PATH
read -s -p "Введите пароль для SSH: " SSH_PASSWORD
echo

# Генерируем SSH-ключ (если его нет)
if [ ! -f ~/.ssh/id_rsa ]; then
    echo "Генерация SSH-ключа..."
    ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N "" -q
fi

# Копируем ключ на сервер (используем sshpass для автоматического ввода пароля)
echo "Копируем SSH-ключ на сервер..."
if ! command -v sshpass &> /dev/null; then
    echo "Установка sshpass..."
    apt-get install -y sshpass || yum install -y sshpass || { echo "Не удалось установить sshpass. Установите его вручную."; exit 1; }
fi

sshpass -p "$SSH_PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP"

# Создаем .desktop-файл
DESKTOP_FILE="$HOME/.local/share/applications/start_bot.desktop"

mkdir -p "$(dirname "$DESKTOP_FILE")"

cat > "$DESKTOP_FILE" <<EOL
[Desktop Entry]
Name=Запустить школьного бота
Exec=gnome-terminal -- bash -c "ssh $SERVER_USER@$SERVER_IP 'cd $BOT_PATH && python3 bot.py'; bash"
Icon=telegram
Type=Application
Terminal=true
EOL

# Делаем файл исполняемым
chmod +x "$DESKTOP_FILE"

echo "✅ Готово! Ярлык создан: $DESKTOP_FILE"
echo "Теперь можно запускать бота прямо из меню приложений."
