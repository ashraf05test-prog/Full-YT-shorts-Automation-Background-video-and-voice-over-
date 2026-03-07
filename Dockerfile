FROM node:20-slim

# Install ffmpeg and python
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip3 install yt-dlp --break-system-packages

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

RUN mkdir -p temp

EXPOSE 3000

CMD ["node", "server.js"]
