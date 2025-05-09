FROM pdal/pdal:latest

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 python3-pip python3-dev build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Python libraries: PDAL, FastAPI, and others
RUN pip3 install --no-cache-dir \
    pdal \
    fastapi \
    uvicorn[standard]

WORKDIR /app

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]