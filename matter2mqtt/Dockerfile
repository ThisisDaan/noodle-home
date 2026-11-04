FROM python:3.12-alpine
RUN pip install --no-cache-dir aiomqtt==2.3.0 websockets==13.1
COPY bridge.py /app/bridge.py
CMD ["python", "-u", "/app/bridge.py"]
