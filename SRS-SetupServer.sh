#!/bin/bash

# Проверка на root-права
if [ "$(id -u)" -ne 0 ]; then
  echo "Запустите скрипт с sudo!" >&2
  exit 1
fi

# Установка зависимостей
apt-get update
apt-get install -y \
  python3 \
  python3-pip \
  mpg123 \
  cron \
  git

# Клонирование репозитория (или копирование файлов)
if [ ! -d "/opt/schoolrings" ]; then
  git clone https://github.com/ваш-репозиторий /opt/schoolrings
else
  echo "Директория /opt/schoolrings уже существует. Обновляю..."
  cd /opt/schoolrings && git pull
fi

# Установка Python-зависимостей
pip3 install -r /opt/schoolrings/requirements.txt

# Настройка cron
echo "*/1 * * * * root /usr/bin/python3 /opt/schoolrings/SRS.py" > /etc/cron.d/schoolrings
chmod 644 /etc/cron.d/schoolrings

# Создание .env файла (если его нет)
if [ ! -f "/opt/schoolrings/.env" ]; then
  cat > /opt/schoolrings/.env <<EOF
TELEGRAM_BOT_TOKEN=your_token_here
BOT_PASSWORD=your_password_here
EOF
  echo "Настройте /opt/schoolrings/.env перед запуском!"
fi

# Создание папок для данных
mkdir -p /var/lib/schoolrings/{audio_files,backups}
chown -R nobody:nogroup /var/lib/schoolrings

# Сервис для systemd (опционально)
cat > /etc/systemd/system/schoolrings.service <<EOF
[Unit]
Description=SchoolRings Bot
After=network.target

[Service]
Type=simple
User=nobody
WorkingDirectory=/opt/schoolrings
ExecStart=/usr/bin/python3 /opt/schoolrings/SRS.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now schoolrings.service

echo "Установка завершена!"
echo "Команды:"
echo "  Статус: systemctl status schoolrings"
echo "  Логи: journalctl -u schoolrings -f"