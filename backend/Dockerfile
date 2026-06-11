# Dockerfile for the AnalyzeFunction Lambda (container image)
# This is needed because librosa + numpy + scipy exceeds the 250MB Lambda layer limit.

FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies for librosa (libsndfile) and tools to fetch ffmpeg
RUN dnf install -y libsndfile tar xz && dnf clean all

# Install static ffmpeg binary so librosa/audioread can decode webm (Opus) audio
RUN curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ffmpeg.tar.xz && \
    cd /tmp && tar xf ffmpeg.tar.xz && \
    cp /tmp/ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ffmpeg && \
    chmod +x /usr/local/bin/ffmpeg && \
    rm -rf /tmp/ffmpeg*

# Copy requirements and install Python deps
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application code
COPY app/ ${LAMBDA_TASK_ROOT}/app/

# The handler is the analyze orchestrator function
CMD ["app.main.handler"]
