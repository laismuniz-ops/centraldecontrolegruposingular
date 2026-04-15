FROM python:3.12-slim
WORKDIR /app
COPY index.html .
COPY server.py .
RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 8080
CMD ["python3", "server.py"]
