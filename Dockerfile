FROM python:3.12-slim
LABEL description='https://github.com/svalgaard/fskintra'

ENV LC_ALL=da_DK.UTF-8
ENV LANG=da_DK.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

# fskintra needs a Danish locale to parse/format Danish dates
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales && \
    sed -i '/da_DK.UTF-8/s/^# //' /etc/locale.gen && \
    locale-gen && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /fskintra

# Install dependencies first so they are cached independently of the source
COPY requirements.txt /fskintra/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /fskintra

VOLUME /root/.skoleintra

ENTRYPOINT ["python", "fskintra.py"]
