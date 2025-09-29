FROM lmsysorg/sglang:latest

# Install hf-xet for faster model downloads (avoid runtime pip install latency)
RUN pip install --no-cache-dir hf_xet

# Set environment variables for hf-xet high performance mode
ENV HF_XET_HIGH_PERFORMANCE=1 \
    HF_XET_MAX_CONCURRENT_DOWNLOADS=8 \
    HF_XET_NUM_CONCURRENT_RANGE_GETS=50 \
    HF_XET_CHUNK_CACHE_SIZE_BYTES=21474836480 \
    HF_HOME=/workspace/huggingface \
    HF_XET_CACHE=/workspace/hf-xet-cache \
    HF_HUB_ENABLE_HF_TRANSFER=""

# Create necessary cache directories
RUN mkdir -p /workspace/huggingface /workspace/hf-xet-cache

# Create optimized startup script
RUN cat <<'EOF' > /usr/local/bin/start-sglang.sh
#!/bin/bash
set -e
echo "[$(date '+%H:%M:%S.%3N')] Starting SGLang with hf-xet optimizations"
exec python3 -m sglang.launch_server \
    --model-path Qwen/Qwen3-8B \
    --host 0.0.0.0 \
    --port 8000 \
    --context-length 4096 \
    --mem-fraction-static 0.95 \
    --disable-radix-cache
EOF
RUN chmod +x /usr/local/bin/start-sglang.sh

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/start-sglang.sh"]

