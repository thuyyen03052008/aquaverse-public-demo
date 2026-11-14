# AQUAVERSE public DEMO: single-host Vite SPA + FastAPI.
FROM node:22-bookworm-slim AS webbuild
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN VITE_PUBLIC_DEMO=1 npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend/ /app/backend/
COPY --from=webbuild /build/frontend/dist/ /app/frontend/dist/
WORKDIR /app/backend
ENV AQUAVERSE_PUBLIC_DEMO=1 AQUAVERSE_SECURE_COOKIES=1 AQUAVERSE_ALLOW_SELF_SIGNUP=0 AQUAVERSE_DATABASE_URL=sqlite:////tmp/aquaverse_public_demo.sqlite3
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --proxy-headers"]
