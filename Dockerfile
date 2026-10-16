FROM python:3.12-slim-bookworm

# 工具全部走 apt，镜像里不带 tools/ 的 Windows 二进制（见 .dockerignore）：
#   ffmpeg   合并、转码、嵌封面字幕
#   aria2    磁力 / 种子的下载引擎，代码会自己拉起 127.0.0.1 的 RPC
#   libchromaprint-tools  提供 fpcalc，声学指纹识别用
# 这三样都能在 PATH 上找到，find_ffmpeg / find_binary 会经 shutil.which 命中，不会误报「未安装」。
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg aria2 libchromaprint-tools curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/plugins /data/Downloads /data/cookies

# LANG/PYTHONUTF8：容器里默认是 POSIX _locale_，日志和文件名里的中文会变成问号
ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=Asia/Shanghai \
    MEDIADOWNLOADER_HOST=0.0.0.0 \
    MEDIADOWNLOADER_PORT=8765 \
    MEDIADOWNLOADER_STATE_DIR=/data

VOLUME ["/data"]
EXPOSE 8765

# 探针打 /api/health：只读内存计数。/api/status 会真的跑 ffmpeg --version、导入 yt_dlp，别拿它探活。
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${MEDIADOWNLOADER_PORT}/api/health" || exit 1

CMD ["python", "server.py"]
