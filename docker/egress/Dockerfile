FROM python:3.12.14-slim-bookworm

RUN useradd --create-home --uid 10001 harnesslab
COPY --chown=harnesslab:harnesslab proxy.py /opt/harnesslab/proxy.py
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "/opt/harnesslab/proxy.py"]
