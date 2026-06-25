# =============================================================================
# OTel Collector image — environment workaround.
# The official otel/opentelemetry-collector-contrib:0.116.0 image ships a
# dynamically-linked binary (interpreter /lib64/ld-linux-x86-64.so.2) on a
# distroless base that does NOT provide that interpreter on this Docker Desktop
# host, so `exec /otelcol-contrib` fails with "no such file or directory".
# Fix: re-base the SAME pinned official binary onto a minimal glibc image.
# No tooling change — identical collector, just runnable here.
# =============================================================================
FROM otel/opentelemetry-collector-contrib:0.116.0 AS src

FROM debian:bookworm-slim
COPY --from=src /otelcol-contrib /otelcol-contrib
ENTRYPOINT ["/otelcol-contrib"]
CMD ["--config=/etc/otelcol/collector.yaml"]
