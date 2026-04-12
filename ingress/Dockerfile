FROM traefik:v3.6.10 AS traefik

FROM alpine:3.21

RUN apk add --no-cache bash coreutils

COPY --from=traefik /usr/local/bin/traefik /usr/local/bin/traefik
COPY ingress/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
