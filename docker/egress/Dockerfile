FROM python:3.12.14-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

LABEL com.harnesslab.egress.version="1.0.0" \
      com.harnesslab.egress.base="sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134" \
      com.harnesslab.egress.source="sha256:6197201fdf9529cef8963c6c0de3b764608f057ab5507d2326afabb3d9d94592"

RUN useradd --create-home --uid 10001 harnesslab
COPY --chown=harnesslab:harnesslab proxy.py /opt/harnesslab/proxy.py
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "/opt/harnesslab/proxy.py"]
