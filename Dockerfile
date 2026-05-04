# Usamos una imagen slim pero con dependencias para compilar pandas si es necesario
FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y gcc

# Copiar requerimientos e instalar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el bot
COPY bot.py .

# Ejecutar
CMD ["python", "-u", "bot.py"]
