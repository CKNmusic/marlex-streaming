FROM bluenviron/mediamtx:latest AS mediamtx

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

COPY --from=mediamtx /mediamtx /usr/local/bin/mediamtx
COPY deploy/ingest/entrypoint.sh /usr/local/bin/ingest-entrypoint.sh
COPY deploy/ingest/ingest_log_normalizer.awk /usr/local/bin/ingest_log_normalizer.awk

RUN chmod +x /usr/local/bin/mediamtx /usr/local/bin/ingest-entrypoint.sh

EXPOSE 8554 9000/udp 9997

ENTRYPOINT ["/usr/local/bin/ingest-entrypoint.sh"]

