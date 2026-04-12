# Website Ingress

This is the ingress for the GHW web.

- Sets up trusted TLS PKI using ACME and Let's Encrypt
- Forwards to multiple back-end projects using port mapping config
    - Ex: forwards `/project1/test` to `localhost:1234/test`
