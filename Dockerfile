FROM python:3.12-slim
LABEL description='https://github.com/svalgaard/fskintra'

ENV LC_ALL=da_DK.utf-8 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8

RUN apt-get update && \
    apt-get install -y --no-install-recommends locales && \
    localedef -i da_DK -c -f UTF-8 -A /usr/share/locale/locale.alias da_DK && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /fskintra

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /fskintra

VOLUME /root/.skoleintra

ENTRYPOINT ["python", "fskintra.py"]
