FROM docker:cli
RUN apk add --no-cache python3 git
WORKDIR /app
COPY updater.py .
CMD ["python3", "updater.py"]
