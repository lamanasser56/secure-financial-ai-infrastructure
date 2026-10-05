FROM postgres:17.11-alpine3.24@sha256:aa90e97ee862e558111d34cfb8b2c4bec768c2b039fb791341686928560263b3
# This service always starts as PostgreSQL's existing nonroot user. The inherited
# entrypoint invokes gosu only in its UID 0 branch. Remove that unused executable,
# whose embedded Go runtime failed the unchanged vulnerability policy. No server,
# client, package version, scanner rule or exception changes.
RUN test -f /usr/local/bin/gosu && test ! -L /usr/local/bin/gosu \
    && rm /usr/local/bin/gosu
USER 70:70
