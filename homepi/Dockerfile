# Build the SvelteKit interface with Bun, then run it from the Python backend.
FROM oven/bun:1 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/homepi ./homepi
COPY --from=frontend /app/build ./static
ENV HOMEPI_STATIC=/app/static HOMEPI_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8090
CMD ["python", "-m", "homepi"]
