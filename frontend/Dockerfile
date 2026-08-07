FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt constraints-docker.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints-docker.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
