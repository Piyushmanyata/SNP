# syntax=docker/dockerfile:1
FROM alpine:3.22 AS restic
ADD --checksum=sha256:f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c \
    https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_amd64.bz2 /restic.bz2
RUN bunzip2 /restic.bz2 && chmod 755 /restic

FROM mongo:7
COPY --from=restic /restic /usr/local/bin/restic
COPY backup.sh restore-drill.sh /usr/local/bin/
CMD ["backup.sh"]
