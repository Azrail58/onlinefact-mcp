FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY onlinefact_server.py .

ENV MCP_TRANSPORT=sse
ENV PORT=10000

EXPOSE 10000
CMD ["python", "onlinefact_server.py"]
