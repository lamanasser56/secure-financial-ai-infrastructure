# PostgreSQL is an exact upstream material. Rebuild its gosu entrypoint helper from
# pinned upstream source with patched Go and modules, retaining the full root-start path.
FROM golang:1.27.3-alpine@sha256:b8c9b82affbbb82a020bbcf998dad2ba9516944ac7e883524642a481a9505e9c AS gosu-builder
WORKDIR /src
COPY tools/database-gosu/go.mod tools/database-gosu/go.sum ./
RUN go mod download
RUN CGO_ENABLED=0 go build -mod=readonly -trimpath -ldflags='-s -w' -o /out/gosu github.com/tianon/gosu

FROM postgres:17-alpine@sha256:266d3c257594e195b309ae9d1805e54c788f1d7b375f56bf6c367aac6c917e7b AS runtime
COPY --from=gosu-builder /out/gosu /usr/local/bin/gosu
USER 70:70
