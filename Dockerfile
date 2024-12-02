#THIS DOCKERFILE RUNS THE WEB API

# Use the official Python base image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set the working directory in the container
WORKDIR /app

# Install the Python dependencies
RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y git

COPY ./chap_core ./chap_core
COPY ./scripts/seed.py ./scripts/seed.py
COPY ./pyproject.toml .
COPY ./README.md .

RUN uv sync
