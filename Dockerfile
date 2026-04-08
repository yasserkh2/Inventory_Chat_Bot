FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY inventory_chatbot ./inventory_chatbot
COPY README.md .

EXPOSE 8000

CMD ["python", "-m", "inventory_chatbot.main"]

