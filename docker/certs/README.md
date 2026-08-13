# Local CA certificates

Place local HTTPS inspection or corporate root certificates in this directory
with a `.crt` extension before building the image. Certificates are copied into
the container trust store, while `*.crt` files in this directory are ignored by
Git because they are specific to the local network.
