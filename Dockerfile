FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY src ./src
COPY .env.example ./.env.example

ENV PYTHONPATH=/app/src
ENV ENV=prod

EXPOSE 8000
CMD ["uvicorn", "acgn_assistant.main:app", "--host", "0.0.0.0", "--port", "8000"]
