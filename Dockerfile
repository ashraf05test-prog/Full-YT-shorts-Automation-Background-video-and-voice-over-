FROM node:20-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3 \
    python3-pip \
    python3-pil \
    curl \
    wget \
    ca-certificates \
    fonts-beng \
    fonts-beng-extra \
    fonts-noto \
    fonts-noto-cjk \
    fontconfig \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

# Download Kalpurush â€” best Bengali font
RUN mkdir -p /usr/share/fonts/truetype/kalpurush \
    && wget -q "https://github.com/pothi/kalpurush/raw/main/Kalpurush.ttf" \
       -O /usr/share/fonts/truetype/kalpurush/Kalpurush.ttf \
    && fc-cache -fv

# Latest yt-dlp with impersonation support
RUN pip3 install -U yt-dlp[default] --break-system-packages

# Install curl-cffi for TikTok impersonation
RUN pip3 install curl-cffi --break-system-packages

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN mkdir -p temp

EXPOSE 3000
CMD ["node", "server.js"]
