FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.19
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --locked --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
RUN useradd --create-home --uid 10001 crm
RUN install -d -o crm -g crm /app/var/imports
USER crm
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
